"""Config files under /config: load them into items, and save them through the guard.

Files hold the content (what a dashboard shows, what an automation does). The database holds access.
Loading a file never changes an item's access settings.
"""

import hashlib
import os
import re
import tempfile
from collections.abc import Sequence as Seq
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from cave import audit
from cave.access.evaluate import AccessDenied, assert_can_save, evaluate
from cave.access.items import ensure_item, get_item, set_item_entities
from cave.access.model import Principal
from cave.access.network import IPAddress
from cave.config.models import (
    Automation,
    AutomationFile,
    Dashboard,
    DashboardFile,
    Sequence,
    SequenceFile,
    check_nesting,
)
from cave.config.refs import Refs, refs
from cave.config.yamlfile import ConfigError, YamlDoc, load_text, path_text, validate
from cave.db import Database
from cave.state import EventBus
from cave.templates import STATE_CALLS, TemplateError
from cave.templates import check as check_template

Kind = Literal["automation", "sequence", "dashboard"]
Doc = Automation | Sequence | Dashboard
FOLDERS: dict[Kind, str] = {"automation": "automations", "sequence": "sequences", "dashboard": "dashboards"}
FILE_ID = re.compile(r"^[a-z0-9_-]{1,64}$")
DYNAMIC_REFUSED = "Templates must name devices directly, like states('sensor.x')."


def note_file(db: Database, rel: str, text: str, actor: str) -> None:
    """Audit a config file that's new or changed since it was last loaded."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    row = db.execute("SELECT sha256 FROM config_files WHERE path=?", (rel,)).fetchone()
    if row is not None and row["sha256"] == digest:
        return
    db.execute(
        "INSERT INTO config_files (path, sha256, loaded_at) VALUES (?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET sha256=excluded.sha256, loaded_at=excluded.loaded_at",
        (rel, digest, datetime.now(UTC).isoformat()),
    )
    action = "config.file_added" if row is None else "config.file_changed"
    audit.record(db, actor, action, f"config:{rel}", row["sha256"] if row else None, digest)


def write_atomic(path: Path, text: str) -> None:
    """Write the text exactly as given (line endings too), replacing the file in one step."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    # mkstemp makes it 0600; scripts are read by the runner's script user, a different uid
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def item_id(kind: Kind, ident: str) -> str:
    return f"{kind}:{ident}"


class AlreadyExists(Exception):
    pass


@dataclass(frozen=True)
class Loaded:
    doc: Doc
    text: str
    refs: Refs

    @property
    def name(self) -> str:
        return _name(self.doc)


def _check_templates(data: Any, loc: tuple[str | int, ...], yaml_doc: YamlDoc, file: str) -> None:
    """Every string that looks like a template must pass the automation allow-list now, not fail at run time."""
    if isinstance(data, dict):
        for k, v in data.items():
            _check_templates(v, (*loc, k), yaml_doc, file)
    elif isinstance(data, list):
        for i, v in enumerate(data):
            _check_templates(v, (*loc, i), yaml_doc, file)
    elif isinstance(data, str) and ("{{" in data or "{%" in data):
        try:
            check_template(data, STATE_CALLS)
        except TemplateError as e:
            raise ConfigError(file, path_text(loc), f"template: {e}", yaml_doc.lines.get(loc)) from e


def parse(kind: Kind, ident: str, text: str) -> Doc:
    """Validate one document. Raises ConfigError naming file and line."""
    file = f"{ident}.yaml"
    if not FILE_ID.fullmatch(ident):
        raise ConfigError(file, "", "file names may only use a-z, 0-9, - and _ (64 characters at most)")
    yaml_doc = load_text(text, file)
    _check_templates(yaml_doc.data, (), yaml_doc, file)
    doc: Doc
    if kind == "dashboard":
        doc = validate(DashboardFile, yaml_doc, file).dashboard
        return doc
    inner = validate(AutomationFile, yaml_doc, file).automation if kind == "automation" else validate(
        SequenceFile, yaml_doc, file).sequence
    if inner.id != ident:
        raise ConfigError(file, f"{kind}.id", f"must be {ident!r}, the file name", yaml_doc.lines.get((kind, "id")))
    check_nesting(inner, yaml_doc, file)
    return inner


def _name(doc: Doc) -> str:
    return doc.title if isinstance(doc, Dashboard) else doc.name


class ConfigStore:
    def __init__(self, config_dir: Path, db: Database, bus: EventBus) -> None:
        self.config_dir = config_dir
        self.db = db
        self.bus = bus
        self.errors: dict[str, str] = {}
        self._loaded: dict[tuple[Kind, str], Loaded] = {}

    # ---- reading ----

    def get(self, kind: Kind, ident: str) -> Loaded | None:
        return self._loaded.get((kind, ident))

    def list(self, kind: Kind) -> list[tuple[str, Loaded]]:
        return sorted((i, d) for (k, i), d in self._loaded.items() if k == kind)

    def deep_refs(self, doc: Doc) -> Refs:
        """refs() plus everything the routines it calls reference, all the way down. For anything that shows
        what a run read (traces, the Test Center): running a routine is allowed by assignment, seeing inside isn't."""
        r = refs(doc)
        entities, scripts, dynamic = set(r.entities), set(r.scripts), r.dynamic_template
        seen: set[str] = set()
        todo = list(r.sequences)
        while todo:
            ident = todo.pop()
            if ident in seen:
                continue
            seen.add(ident)
            loaded = self._loaded.get(("sequence", ident))
            if loaded is None:
                continue
            entities |= loaded.refs.entities
            scripts |= loaded.refs.scripts
            dynamic = dynamic or loaded.refs.dynamic_template
            todo.extend(loaded.refs.sequences)
        return Refs(frozenset(entities), frozenset(seen | r.sequences), r.automations, frozenset(scripts), dynamic)

    def sequence(self, ident: str) -> Sequence | None:
        loaded = self._loaded.get(("sequence", ident))
        return loaded.doc if loaded and isinstance(loaded.doc, Sequence) else None

    # ---- loading ----

    def load_all(self, actor: str = "system") -> None:
        seen: set[tuple[Kind, str]] = set()
        self.errors = {}
        for kind, folder in FOLDERS.items():
            directory = self.config_dir / folder
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.yaml")):
                seen.add((kind, path.stem))
                self._load_one(kind, path.stem, actor)
        for key in set(self._loaded) - seen:
            del self._loaded[key]  # the file is gone; its item and access settings stay

    def _load_one(self, kind: Kind, ident: str, actor: str) -> None:
        rel = f"{FOLDERS[kind]}/{ident}.yaml"
        self.errors.pop(rel, None)
        path = self.config_dir / rel
        try:
            text = path.read_text(encoding="utf-8")
            doc = parse(kind, ident, text)
        except (ConfigError, OSError, UnicodeDecodeError) as e:
            self.errors[rel] = str(e)
            self._loaded.pop((kind, ident), None)  # stops running; the item and its access stay
            return
        note_file(self.db, rel, text, actor)
        r = refs(doc)
        iid = item_id(kind, ident)
        ensure_item(self.db, actor, iid, "dashboard" if kind == "dashboard" else "action", _name(doc))
        if kind == "dashboard":
            # dashboard cards are what grant control; actions grant it only by being run
            set_item_entities(self.db, iid, sorted(r.entities), bus=self.bus)
        self._loaded[(kind, ident)] = Loaded(doc, text, r)

    # ---- the guard ----

    def guard(self, p: Principal, r: Refs, ip: IPAddress, local_ranges: Seq[str]) -> None:
        """What a non-Admin may save, delete, read or test: only what they could already control or run."""
        if p.is_admin:
            return
        if r.dynamic_template:
            raise AccessDenied(DYNAMIC_REFUSED)
        assert_can_save(self.db, p, r.entities, ip, local_ranges)
        for kind, idents in (("sequence", r.sequences), ("automation", r.automations)):
            for ident in sorted(idents):
                item = get_item(self.db, item_id(kind, ident))  # type: ignore[arg-type]
                if item is None or not evaluate(self.db, p, item, ip, local_ranges).allowed:
                    raise AccessDenied(f"You can't use the {kind} {ident!r}, so you can't save something that runs it.")
        for ref in sorted(r.scripts):
            file = ref.removeprefix("scripts/")
            item = get_item(self.db, f"script:{file}")
            if item is None or not evaluate(self.db, p, item, ip, local_ranges).allowed:
                raise AccessDenied(f"You can't run the script {file!r}, so you can't save something that runs it.")

    # ---- saving ----

    def save(
        self, kind: Kind, ident: str, text: str, p: Principal, ip: IPAddress, local_ranges: Seq[str],
        *, create: bool = False,
    ) -> Loaded:
        """create=True refuses to replace a file that's already there (new automations, recipes)."""
        doc = parse(kind, ident, text)
        new_refs = refs(doc)
        self.guard(p, new_refs, ip, local_ranges)
        old = self._loaded.get((kind, ident))
        path = self.config_dir / FOLDERS[kind] / f"{ident}.yaml"
        old_text = self._existing_text(kind, ident, old)
        if create and old_text is not None:
            raise AlreadyExists(f"{ident} is already taken. Choose another id.")
        if old_text is not None and not p.is_admin:
            self.guard(p, self._old_refs(kind, ident, old, old_text, "overwrite"), ip, local_ranges)
        write_atomic(path, text)
        actor = f"{p.kind}:{p.id}"
        self.db.execute(
            "INSERT INTO config_saves (item_id, user_id, saved_at) VALUES (?, ?, ?) "
            "ON CONFLICT(item_id) DO UPDATE SET user_id=excluded.user_id, saved_at=excluded.saved_at",
            (item_id(kind, ident), p.user_id, datetime.now(UTC).isoformat()),
        )
        self._load_one(kind, ident, actor)
        audit.record(self.db, actor, "config.save", f"config:{FOLDERS[kind]}/{ident}.yaml", old_text, text)
        loaded = self._loaded.get((kind, ident))
        assert loaded is not None
        return loaded

    @staticmethod
    def _old_refs(kind: Kind, ident: str, old: Loaded | None, old_text: str, verb: str) -> Refs:
        try:
            return old.refs if old else refs(parse(kind, ident, old_text))
        except ConfigError as e:
            raise AccessDenied(f"Only an Admin can {verb} a file that doesn't load.") from e

    def _existing_text(self, kind: Kind, ident: str, old: Loaded | None) -> str | None:
        if old is not None:
            return old.text
        path = self.config_dir / FOLDERS[kind] / f"{ident}.yaml"
        return path.read_text(encoding="utf-8") if path.exists() else None

    def delete(self, kind: Kind, ident: str, p: Principal, ip: IPAddress, local_ranges: Seq[str]) -> None:
        if not FILE_ID.fullmatch(ident):
            raise KeyError(ident)
        path = self.config_dir / FOLDERS[kind] / f"{ident}.yaml"
        old = self._loaded.get((kind, ident))
        old_text = self._existing_text(kind, ident, old)
        if old_text is None:
            raise KeyError(ident)
        if not p.is_admin:
            self.guard(p, self._old_refs(kind, ident, old, old_text, "delete"), ip, local_ranges)
        path.unlink()
        audit.record(self.db, f"{p.kind}:{p.id}", "config.delete", f"config:{FOLDERS[kind]}/{ident}.yaml", old_text)
        self._loaded.pop((kind, ident), None)
        self.errors.pop(f"{FOLDERS[kind]}/{ident}.yaml", None)
