"""Scripts under config/scripts/: files hold the code, items hold who may run them."""

from dataclasses import dataclass
from pathlib import Path

from cave import audit
from cave.access.evaluate import AccessDenied
from cave.access.items import ensure_item
from cave.access.model import Principal
from cave.config.store import note_file, write_atomic
from cave.config.yamlfile import ConfigError
from cave.db import Database
from cave.scripts.header import FILE_NAME, Language, ScriptHeader, language_of, parse_header
from cave.state import EventBus

SECRETS_ADMIN_ONLY = "Only an Admin can save a script that uses secrets."


@dataclass(frozen=True)
class LoadedScript:
    file: str
    language: Language
    header: ScriptHeader
    text: str


def _check_name(file: str) -> None:
    if not FILE_NAME.fullmatch(file):
        raise ConfigError(file, "", "script names may use A-Z, a-z, 0-9, ., - and _, and end .ps1, .py or .sh")


class ScriptStore:
    def __init__(self, config_dir: Path, db: Database, bus: EventBus) -> None:
        self.dir = config_dir / "scripts"
        self.db = db
        self.bus = bus
        self.errors: dict[str, str] = {}
        self._loaded: dict[str, LoadedScript] = {}

    def get(self, file: str) -> LoadedScript | None:
        return self._loaded.get(file)

    def list(self) -> list[LoadedScript]:
        return [self._loaded[f] for f in sorted(self._loaded)]

    def load_all(self, actor: str = "system") -> None:
        self.errors, self._loaded = {}, {}
        if not self.dir.is_dir():
            return
        for path in sorted(self.dir.iterdir()):
            if path.is_file() and FILE_NAME.fullmatch(path.name):
                self._load_one(path.name, actor)

    def _load_one(self, file: str, actor: str) -> None:
        rel = f"scripts/{file}"
        self.errors.pop(rel, None)
        try:
            text = (self.dir / file).read_bytes().decode("utf-8")
            header = parse_header(file, text)
        except (ConfigError, OSError, UnicodeDecodeError) as e:
            self.errors[rel] = str(e)
            self._loaded.pop(file, None)
            return
        note_file(self.db, rel, text, actor)
        ensure_item(self.db, actor, f"script:{file}", "action", header.name)
        self._loaded[file] = LoadedScript(file, language_of(file), header, text)

    def _guard_secrets(self, p: Principal, file: str, header: ScriptHeader | None) -> None:
        """Anyone who can edit a script that names a secret could print it, so secrets are an Admin's business."""
        old = self._loaded.get(file)
        if not p.is_admin and ((header and header.secrets) or (old and old.header.secrets)):
            raise AccessDenied(SECRETS_ADMIN_ONLY)

    def save(self, file: str, text: str, p: Principal) -> LoadedScript:
        _check_name(file)
        header = parse_header(file, text)
        self._guard_secrets(p, file, header)
        path = self.dir / file
        old_text = path.read_bytes().decode("utf-8", errors="replace") if path.exists() else None
        if old_text is not None and file not in self._loaded and not p.is_admin:
            raise AccessDenied("Only an Admin can overwrite a script that doesn't load.")
        write_atomic(path, text)
        actor = f"{p.kind}:{p.id}"
        self._load_one(file, actor)
        audit.record(self.db, actor, "config.save", f"config:scripts/{file}", old_text, text)
        loaded = self._loaded.get(file)
        assert loaded is not None
        return loaded

    def delete(self, file: str, p: Principal) -> None:
        _check_name(file)
        path = self.dir / file
        if not path.exists():
            raise KeyError(file)
        if file not in self._loaded and not p.is_admin:
            raise AccessDenied("Only an Admin can delete a script that doesn't load.")
        self._guard_secrets(p, file, None)
        old_text = path.read_bytes().decode("utf-8", errors="replace")
        path.unlink()
        audit.record(self.db, f"{p.kind}:{p.id}", "config.delete", f"config:scripts/{file}", old_text)
        self._loaded.pop(file, None)
        self.errors.pop(f"scripts/{file}", None)
