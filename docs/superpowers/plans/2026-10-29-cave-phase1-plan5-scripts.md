# CAVE Phase 1 · Plan 5: Scripts — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PowerShell, Python and Bash scripts under `config/scripts/` run in a separate sandbox container, under one input/output contract. They can be started from automations, routines, dashboard buttons (through a routine) or the console. They are access-controlled like every other item, keep their secrets out of every log and trace, and give the Test Center sample output to work with.

**Architecture:**
- **Two processes.**
  - The **core** owns scripts as files plus items: it parses each script's `cave:` header, checks parameters and access, and keeps the run log.
  - The **`cave-script-runner`** sidecar only runs a named script from its read-only `/scripts` mount and reports back. It's a separate container with pwsh 7, python3 and bash, no Docker socket, and memory and CPU limits.
- **They talk** over the internal Compose network with plain HTTP and a shared bearer token. The runner is its own small FastAPI app in the same `cave` package (`python -m cave.runner`). The core calls it with the standard library (`urllib` in a thread), so there's no new runtime dependency.
- **Wiring.** `LiveEffects.run_script` stops raising "scripts arrive in plan 5" and calls a `ScriptService`. The config store's save guard learns about script items. The Test Center uses each script's `sample:` block.

**Tech Stack:** Python 3.13, FastAPI and uvicorn (already dependencies; the runner reuses them), asyncio subprocesses, PyYAML (headers), the existing `ConfigError`/`yamlfile` loader, Pydantic v2. Runner image: Debian slim, PowerShell 7 from Microsoft's Debian repository, python3, bash. No new Python dependencies.

**Spec:** `docs/superpowers/specs/2026-10-25-cave-phase1-design.md`, section "Scripts (Phase 1 subset)" and the scope row "Scripts". It defers to `docs/CAVE-Design-Framework.md` § "Scripts" for the header and the contract, and adds the `sample:` block. This builds on Plans 1–4, all on `main`.

## Global Constraints

- Everything in Plans 1–4's Global Constraints still holds.
- **Sandbox target only.** A header with `target: ssh:<host>` or `target: cave-host` is a `ConfigError`, with a message saying those come later.
- **File names:** `config/scripts/<name>.(ps1|py|sh)`, where `<name>` matches `^[A-Za-z0-9_.-]{1,64}$` and has no `..`. Automations refer to them as `ref: scripts/<file>`. The item ID is `script:<file>`, `kind="action"`.
- **The contract**, from the framework, exactly:
  1. Params arrive as environment variables `CAVE_PARAM_<NAME>`, with the name uppercased, **and** as one JSON object on stdin. PowerShell also gets them as named parameters, passed as `-Name:value`, so a value starting with `-` stays data.
  2. Listed secrets arrive as environment variables, are masked as `•••` in all output, and never appear in traces, run logs, the audit log or API responses.
  3. The last non-empty line of stdout must be one JSON object. It becomes the step's result.
  4. Exit code 0 means success. Anything else fails the step and shows the last 20 log lines.
  5. The timeout comes from the header: 60 s by default, 1 h at most. When it's reached, the whole process tree is killed.
  6. The run log records who or what started it, the target, the parameters (secrets masked), the duration, the exit code and the output.
- **Values are never pasted into a command line.** The runner builds an argv list, and no shell is ever invoked on a value.
- **Who may do what:**
  - The `Scripts` section allows reading, saving, deleting and test-running scripts. That's the Phase 1 rule that a section grants everything in it.
  - **Only an Admin may save a script whose header lists `secrets`.** Otherwise anyone who can edit scripts could read every secret by echoing it.
  - Running a script needs `use` of its `script:<file>` item, or the Scripts section.
  - Automations and routines that run a script need `use` of its item. The save guard checks this.
- Secret values come from the core's environment, `CAVE_SECRET_<NAME>`, set in Compose's `.env`. They're never stored in `/config` or the database. `shortcut: secrets live in the core's environment; an Admin-managed, encrypted secret store comes with the console`.
- Output caps: the runner keeps at most **1 MiB** of combined stdout and stderr per run, and the run log stores the last **200** lines. Run logs keep the last **100** runs per script.
- Runner security:
  - every request needs `Authorization: Bearer <CAVE_RUNNER_TOKEN>`, compared in constant time
  - only files directly inside `/scripts` can run, so paths with `/`, `\` or `..`, and symlinks pointing outside, are refused
  - scripts run as an unprivileged user, in a fresh per-run temporary working directory that's deleted afterwards
  - the environment is limited to `PATH`, `HOME`, `LANG`, `TMPDIR`, `CAVE_PARAM_*` and the listed secrets

## Review Focus

1. **Path tricks in a script reference or runner request** (`../x.sh`, `/etc/passwd`, `scripts/../../x`, a symlink inside `/scripts` pointing outside, a backslash path) → refused by the core and, again, by the runner. Pinned in Tasks 3 and 4.
2. **A parameter value that looks like code or an option** (`"; rm -rf ~"`, `$(id)`, `-Command evil`, `-EncodedCommand …`) → reaches the script as data in every language. Pinned in Task 2.
3. **A script that prints its secret**, directly or in an error → masked in the run log, the trace, the audit log and the API response. The plain value never leaves the runner. Pinned in Tasks 2 and 5.
4. **A runaway script** (an infinite loop, a child process that keeps running, or 50 MB of output) → killed at the timeout, child included, with output capped. The runner keeps serving the next request. Pinned in Task 2.
5. **The runner is down, slow or has the wrong token** → the step fails within the script's timeout plus 10 s, with a clear message, and the automation's trace says so. Nothing hangs. Pinned in Task 5.

---

## File structure

```text
core/cave/scripts/__init__.py
core/cave/scripts/header.py        # parse the cave: header; check params
core/cave/scripts/store.py         # config/scripts files -> items; save/delete; errors
core/cave/scripts/service.py       # RunnerClient + ScriptService: run, mask, record, audit
core/cave/runner/__init__.py
core/cave/runner/execute.py        # build env/argv, run with timeout, kill tree, parse result
core/cave/runner/app.py            # the runner's HTTP API
core/cave/runner/__main__.py       # python -m cave.runner
core/cave/api/scripts.py           # scripts CRUD, run, run log
core/cave/migrations/0005_scripts.sql
core/cave/automation/effects.py    # run_script(…, source) → ScriptService
core/cave/automation/engine.py     # pass source to run_script
core/cave/automation/whatif.py     # header samples
core/cave/config/store.py          # guard + deep_refs know scripts
deploy/script-runner/Dockerfile
docs/scripts.md
```

---

### Task 1: The script header

**Files:**
- Create: `core/cave/scripts/__init__.py`, `core/cave/scripts/header.py`
- Test: `core/tests/test_script_header.py`

**Interfaces:**
- Produces:
  - `Language = Literal["powershell", "python", "bash"]`, from the extension `.ps1`, `.py` or `.sh`
  - `FILE_NAME = re.compile(r"^(?!.*\.\.)[A-Za-z0-9_.-]{1,64}\.(ps1|py|sh)$")`
  - `class Param(BaseModel, extra="forbid")`: `type: Literal["int", "float", "str", "bool"]`, `default: Any = None`, `min: float | None`, `max: float | None`, `choices: list[str] | None`
  - `class ScriptHeader(BaseModel, extra="forbid")`:
    - `name: str` (1–100 characters)
    - `target: Literal["sandbox"] = "sandbox"`
    - `timeout: Duration`, from `cave.config.models`, defaulting to 60 s and capped at **1 h**
    - `params: dict[Ident, Param] = {}`
    - `secrets: list[Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]] = []`
    - `sample: dict[str, Any] | None = None`
  - `parse_header(file: str, text: str) -> ScriptHeader`. It raises `ConfigError` with `file:line` when the header is missing or invalid. The header YAML is located like this:
    - **PowerShell:** the first `<# … #>` block whose first non-blank line is `cave:`
    - **Python and Bash:** the first run of `#` comment lines starting with `# cave:` (a shebang line may come first). Each line's leading `#` and one following space are stripped.

    Line numbers in errors are offset to the real file line. `target: ssh:…` and `target: cave-host` get the reason `"only target: sandbox is available in this version"`.
  - `check_args(header: ScriptHeader, args: Mapping[str, Any]) -> dict[str, Any]` — the trust-boundary check. Unknown names raise `ValueError("unknown parameter: X")`. Missing names take the default, or raise if there's no default. Values are converted to the declared type, so `"120"` becomes `120` for an `int`. `min`, `max` and `choices` are enforced, and `str` values are capped at 4,096 characters. It returns the final typed values.

- [ ] **Step 1: Write failing tests:**
  - `test_powershell_header` (the framework's `Stop-LabHosts.ps1` example)
  - `test_python_header_with_shebang`
  - `test_bash_header` (the framework's `disk-report.sh` example with `target: sandbox`)
  - `test_missing_header_error_has_line`
  - `test_unknown_key_error_line_is_file_line` (an error on header line 3 in a `.ps1` whose header starts on file line 2 → `:4:`)
  - `test_ssh_and_cave_host_targets_refused`
  - `test_timeout_capped_at_one_hour`
  - `test_sample_block`
  - `test_check_args_types_defaults_bounds_choices` (parametrized)
  - `test_check_args_unknown_and_missing`
- [ ] **Step 2:** Run `cd core && ../.venv/Scripts/python -m pytest -q tests/test_script_header.py`. Expected: FAIL.
- [ ] **Step 3:** Implement. Reuse `load_text` and `validate` from `cave.config.yamlfile` on the extracted YAML, then add the header's starting line to `ConfigError.line`.
- [ ] **Step 4:** Rerun, then the full suite with `-W error`, `ruff check .` and `mypy --strict cave`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(scripts): cave header parsing and parameter checks"`

---

### Task 2: Running a script (the runner's engine)

**Files:**
- Create: `core/cave/runner/__init__.py`, `core/cave/runner/execute.py`
- Test: `core/tests/test_runner_execute.py`, with small test scripts written to `tmp_path`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class RunResult: exit_code: int | None; timed_out: bool; duration_ms: int; result: dict[str, Any] | None; log: list[str]; error: str | None`
  - `MAX_OUTPUT = 1024 * 1024`, `LOG_LINES = 200`, `MASK = "•••"`
  - `async def execute(path: Path, language: Language, params: dict[str, Any], secrets: dict[str, str], timeout: float, workdir_parent: Path | None = None) -> RunResult`:
    - **argv**, never through a shell:
      - PowerShell: `["pwsh", "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(path), *[f"-{k}:{v}" for k, v in params]]`, where booleans become `$true`/`$false`
      - Python: `[sys.executable or "python3", "-I", str(path)]`
      - Bash: `["bash", str(path)]`
    - **env**: only `PATH`, `HOME` (the temp workdir), `LANG=C.UTF-8`, `TMPDIR`, `CAVE_PARAM_<NAME>` for each param (stringified, with JSON for non-scalars) and each secret by its own name. On Windows, add `SYSTEMROOT`, which Python needs to start there.
    - **stdin**: `json.dumps(params)`, then close it.
    - **cwd**: a fresh `tempfile.mkdtemp()`, removed afterwards whatever happens.
    - **timeout**: on POSIX the process starts in its own session (`start_new_session=True`) and is killed with `os.killpg(SIGKILL)`. On Windows it uses `CREATE_NEW_PROCESS_GROUP` plus `taskkill /T /F /PID`. `shortcut: Windows kill uses taskkill; Debian is the target`.
    - **output**: stdout and stderr are read concurrently into one line list, and reading stops at `MAX_OUTPUT` (`"[output truncated]"` is appended). Every secret value of 4 or more characters is replaced by `MASK` in every line **before** it's stored.
    - **result**: the last non-empty **stdout** line, parsed as JSON. With exit code 0, anything other than a JSON object gives `error="The script must end by printing one JSON object."`. A non-zero exit gives `error=f"The script exited with code {n}."`, and a timeout gives `error=f"The script took longer than {timeout:.0f} s and was stopped."`.
    - **log**: the last `LOG_LINES` lines.

- [ ] **Step 1: Write failing tests**, where each test writes its script into `tmp_path`:
  - `test_python_params_env_stdin_and_result`
  - `test_bash_params_and_result`
  - `test_powershell_named_params_and_result`, skipped when `pwsh` isn't on PATH
  - `test_parameter_injection_is_data` (Review Focus 2: `"; rm -rf ~"`, `$(id)`, `-Command evil` and `-EncodedCommand ZQBjAGgAbwA=` each come back unchanged in the JSON result, in all three languages)
  - `test_secret_masked_in_log_and_error` (Review Focus 3: the script prints the secret and raises with it in the message → no line contains it, but `•••` appears)
  - `test_non_json_last_line_fails`
  - `test_nonzero_exit_fails_with_tail`
  - `test_timeout_kills_child_too` (Review Focus 4: the script starts a child that sleeps 30 s and writes a marker file after 2 s. With `timeout=1` the run ends in under 3 s, `timed_out` is set, and the marker never appears)
  - `test_huge_output_capped` (50 MB printed → under 1.1 MiB kept, truncation noted, finishes quickly)
  - `test_env_is_minimal` (the parent's `PATH` is passed, but a `CAVE_TEST_LEAK` variable set in the parent is not)
  - `test_workdir_removed`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun three times for timing flakiness, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(runner): sandboxed script execution under the cave contract"`

---

### Task 3: The runner service and its image

**Files:**
- Create: `core/cave/runner/app.py`, `core/cave/runner/__main__.py`, `deploy/script-runner/Dockerfile`
- Test: `core/tests/test_runner_app.py`

**Interfaces:**
- Produces in `app.py`: `create_runner_app(scripts_dir: Path, token: str) -> FastAPI`, with:
  - `POST /run` taking `{"script": str, "params": dict, "secrets": dict[str, str], "timeout": float}`. It returns `RunResult` as JSON (`200`), even when the script itself failed. It returns `401` for a bad or missing token, `404` for an unknown script, `400` for a refused path, and `422` for a bad body or a timeout over 3,600.
    - Path checks: `script` must match `FILE_NAME`, and `(scripts_dir / script).resolve()` must sit directly in `scripts_dir.resolve()`, which refuses symlinks pointing outside (Review Focus 1).
    - Language comes from the extension.
  - `GET /health` → `{"status": "ok", "interpreters": {"pwsh": bool, "python3": bool, "bash": bool}}`. It needs the token as well.
- Produces in `__main__.py`: `python -m cave.runner [--host 0.0.0.0] [--port 8099] [--scripts /scripts]`. The token comes from `CAVE_RUNNER_TOKEN`. It refuses to start when that's missing or shorter than 32 characters.
- Produces `deploy/script-runner/Dockerfile`:
  - It starts `FROM python:3.13-slim-trixie` (pin the digest when Plan 7 builds it) and installs `bash`, plus PowerShell 7 from Microsoft's Debian 13 repository. **Check the current install steps on Microsoft Learn ("Install PowerShell on Debian") before writing them.**
  - It copies and installs the `cave` package, creates user `runner` (uid 10001), and sets `USER runner`, `WORKDIR /work`, `EXPOSE 8099` and `ENTRYPOINT ["python", "-m", "cave.runner", "--scripts", "/scripts"]`.
  - Read-only, tmpfs, mem and cpu limits belong to Compose (Plan 7). They're noted in a comment.

- [ ] **Step 1: Write failing tests** with `TestClient(create_runner_app(tmp_scripts, "t" * 40))`:
  - `test_runs_script_and_returns_result`
  - `test_token_required_and_constant_time` (wrong token → 401; check `hmac.compare_digest` is used by asserting on behaviour only)
  - `test_path_tricks_refused` (Review Focus 1, parametrized: `../x.py`, `/etc/passwd`, `sub/x.py`, `x\\y.py`, `..`, plus a symlink `link.py` inside the folder pointing outside, skipped where symlinks can't be made)
  - `test_unknown_script_404`
  - `test_timeout_over_an_hour_422`
  - `test_health_lists_interpreters`
  - `test_main_refuses_short_token`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the app, the entry point and the Dockerfile. The image isn't built here, because Docker isn't available on the dev machine, so Plan 7 builds and smoke-tests it. Record that in the ledger.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(runner): runner http service and container image"`

---

### Task 4: Script files, items and the editing API

**Files:**
- Create: `core/cave/scripts/store.py`, `core/cave/api/scripts.py`, `core/cave/migrations/0005_scripts.sql`
- Modify: `core/cave/api/app.py`, `core/cave/api/config.py` (`GET /config/errors` also lists script errors)
- Test: `core/tests/test_script_store.py`

**Interfaces:**
- Table in `0005`: `script_runs(id INTEGER PRIMARY KEY, script TEXT, started_by TEXT, target TEXT, params TEXT, started_at TEXT, duration_ms INTEGER, exit_code INTEGER, outcome TEXT, log TEXT, result TEXT)`, with an index on `(script, id)`. It's used by Task 5.
- Produces in `store.py`: `@dataclass(frozen=True) class LoadedScript: file: str; language: Language; header: ScriptHeader; text: str`, and `class ScriptStore(config_dir, db, bus)`:
  - `load_all(actor="system")` reads `config/scripts/*` (only names matching `FILE_NAME`). It calls `ensure_item(..., f"script:{file}", "action", header.name)` for each valid file, audits `config.file_changed`/`config.file_added` like `ConfigStore` (reuse its `_note_file`, made a module-level function), and records invalid files in `errors`, keyed by `"scripts/<file>"`.
  - `get(file)` and `list()`.
  - `save(file, text, p: Principal) -> LoadedScript`:
    - It refuses a bad name with `ConfigError` and parses the header (`ConfigError` with a line).
    - It refuses a header with `secrets` from a non-Admin with `AccessDenied("Only an Admin can save a script that uses secrets.")`. The same applies when the **existing** file uses secrets.
    - It writes atomically with `newline=""` (keeping CRLF/LF as sent), audits `config.save` with the old and new text, and reloads.
  - `delete(file, p)` applies the same secrets rule, audits `config.delete`, and keeps the item.
- Produces in `api/scripts.py`, where everything except `run` needs `section:scripts`:
  - `GET /api/v1/scripts` → `[{file, name, language, allowed}]`, listed per access
  - `GET /api/v1/scripts/{file}` → `{file, name, language, header, text}`
  - `PUT /api/v1/scripts/{file}` `{text}` (422 with `file:line` for a bad header, 403 for the secrets rule)
  - `DELETE /api/v1/scripts/{file}`

  The path parameter is checked against `FILE_NAME` before any file access, and refused with 404 (Review Focus 1).
- App wiring: `app.state.scripts = ScriptStore(...)`, loaded at startup next to the config store. The scripts router is included before the config router.

- [ ] **Step 1: Write failing tests:**
  - `test_load_creates_items`
  - `test_bad_header_listed_in_config_errors_with_line`
  - `test_operator_with_scripts_section_can_save_plain_script`
  - `test_secrets_need_admin_new_and_existing`
  - `test_household_cannot_edit`
  - `test_path_tricks_404` (Review Focus 1, via the API: `..%2Fx.sh`, `x.exe`, `a/b.py`)
  - `test_save_keeps_bytes_and_audits_old_and_new`
  - `test_delete_keeps_item`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(scripts): script files, items and editing api"`

---

### Task 5: Running scripts from CAVE

**Files:**
- Create: `core/cave/scripts/service.py`
- Modify: `core/cave/automation/effects.py` (`Effects.run_script` gains `source: str`; `LiveEffects` takes a `ScriptService`), `core/cave/automation/engine.py` (pass `self._source`), `core/cave/automation/whatif.py`, `core/tests/engine_helpers.py` (`FakeEffects` signature), `core/cave/api/scripts.py`, `core/cave/api/app.py`
- Test: `core/tests/test_script_service.py`

**Interfaces:**
- Produces in `service.py`:
  - `RunnerPost = Callable[[str, dict[str, Any], float], Awaitable[dict[str, Any]]]` — `(path, body, timeout_s)` → the decoded JSON. It raises `RunnerError(message)` for a connection failure, a non-200 response or bad JSON.
  - `class RunnerClient(url: str, token: str)`, with `post: RunnerPost`. It uses `urllib.request` in `asyncio.to_thread`, a `timeout` equal to the script timeout plus 10 s (Review Focus 5), and `Authorization: Bearer`.
  - `class ScriptService(store: ScriptStore, db, runner: RunnerPost | None, environ: Mapping[str, str] = os.environ)`, with `async run(file: str, args: Mapping[str, Any], started_by: str) -> dict[str, Any]`:
    1. Look up the script. An unknown one raises `ValueError(f"There's no script called {file!r}.")`.
    2. Run `check_args`. A `ValueError` is re-raised with the script name.
    3. Collect secrets from `CAVE_SECRET_<NAME>`. A missing one raises `ValueError("Secret X isn't set on this CAVE.")`.
    4. With no `runner`, raise `ValueError("The script runner isn't set up.")`.
    5. Post `/run`, then mask secrets in **everything** returned (log, error, result values) again, in case of a runner bug.
    6. Record a `script_runs` row with params minus secrets, `log` as JSON (last 200 lines), the outcome (`finished`, `failed` or `timed_out`) and the result. Keep the newest 100 per script.
    7. Audit `script.run` (actor `started_by`, target `script:<file>`, `new={"outcome", "exit_code", "result"}`, masked).
    8. On failure, raise `ValueError(f"{error}\n" + last 20 log lines)`. Otherwise return `result`.
  - `ScriptService.sample(file: str) -> dict[str, Any] | None` — the header's `sample:` block.
- `LiveEffects.run_script(ref, target, args, source)`: strip the `scripts/` prefix from `ref` (anything else is a `ValueError`) and call `service.run(file, args, source)`. `target` must be `None` or `"sandbox"`.
- Engine: `await self.effects.run_script(a.ref, a.target, args, self._source)`.
- API:
  - `POST /api/v1/scripts/{file}/run` `{params}` needs `use` of `script:<file>` or `section:scripts`. It returns `{"result": …}`, or `409 {"detail": <message>}` for a script failure, or 503 when there's no runner.
  - `GET /api/v1/scripts/{file}/runs` (`section:scripts` or `section:run_history`) returns the run log rows, already masked.
- App: the runner is configured from `CAVE_RUNNER_URL` and `CAVE_RUNNER_TOKEN`. When either is missing, `runner=None`, and every run says so clearly.

- [ ] **Step 1: Write failing tests:**
  - **End to end, in process:** a fake `RunnerPost` that forwards to `TestClient(create_runner_app(...))`, running real Python scripts:
    - `test_run_records_log_and_audit`
    - `test_bad_params_refused_before_runner` (the runner is never called)
    - `test_missing_secret_refused`
    - `test_secret_never_leaves` (Review Focus 3: the secret's value doesn't appear in the API response, the `script_runs` row, the audit table dump or an automation trace that ran it)
  - **Failures:**
    - `test_runner_down_fails_fast` (Review Focus 5: a `RunnerPost` that raises `RunnerError` → `ValueError` with the message; an automation using it ends `failed` with that error)
    - `test_runner_client_timeout` (a local `http.server` that never answers, with a 1 s script timeout → `RunnerError` in under 12 s; mark it `slow`, but keep it in the default run)
  - **Access and limits:**
    - `test_run_api_access` (sam without the item → 403; with the item → 200)
    - `test_runs_kept_100`
    - `test_engine_passes_source`
    - `test_script_failure_is_409_with_tail`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS, with Plan 4's `test_script_not_available_yet` replaced by `test_no_runner_configured`.
- [ ] **Step 5: Commit** `git commit -s -m "feat(scripts): run scripts from automations, the console and buttons"`

---

### Task 6: The guard and the Test Center learn about scripts

This closes Plan 4's deferred minor.

**Files:**
- Modify: `core/cave/config/store.py` (`guard`, `deep_refs`), `core/cave/api/automations.py` (Test Center samples), `core/cave/automation/whatif.py`
- Test: `core/tests/test_script_guard.py`

**Interfaces:**
- `ConfigStore.guard`: for every `ref` in `r.scripts`, a non-Admin needs `use` of `script:<file>`. A `ref` that isn't `scripts/<valid file>` is refused with `AccessDenied("Scripts are referenced as scripts/<file>.")`.
- `ConfigStore.deep_refs` also collects `scripts` from called routines. Plan 4's version passes only the top level's.
- Test Center: for each script in `deep_refs(doc).scripts` with no entry in the request's `script_samples`, the header's `sample:` is used. `WhatIfEffects.run_script` gains the `source` parameter.
- `models.Script.ref` is tightened to `pattern=r"^scripts/(?!.*\.\.)[A-Za-z0-9_.-]{1,64}\.(ps1|py|sh)$"`. Regenerate `schemas/`.

- [ ] **Step 1: Write failing tests:**
  - `test_operator_needs_script_item_to_save_automation`
  - `test_routine_scripts_count_in_deep_refs`
  - `test_bad_script_ref_is_config_error`
  - `test_test_center_uses_header_sample` (the UPS example with no `script_samples` → `lab.status` comes from `Stop-LabHosts.ps1`'s `sample:`)
  - `test_body_sample_overrides_header`
  - `test_schemas_still_match`
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "feat(scripts): save guard and test center know scripts"`

---

### Task 7: The exit-gate path, and docs

**Files:**
- Create: `docs/scripts.md`, `core/tests/fixtures/config/scripts/Stop-LabHosts.ps1` (the framework example, with a `sample:` block)
- Modify: `README.md` (one link)
- Test: `core/tests/test_script_exit_gate.py`

**Interfaces:**
- The test runs the spec's exit-gate item 4 as far as it can go without Docker. The dashboard has a button for the routine `lab_safe_shutdown`, which runs `Stop-LabHosts.ps1` through the real runner app in process. The test passes the button's `POST /api/v1/sequences/lab_safe_shutdown/run` as sam, assigned only the routine. The script's JSON result then appears in the audit log's `script.run` entry, and the switch call goes through the state machine. `skipif` no `pwsh`.
- `docs/scripts.md` covers:
  - where scripts live
  - the header, with the three examples
  - the contract, in plain words
  - parameters, and why they're never pasted into a command line
  - secrets: `CAVE_SECRET_<NAME>`, Admin-only, and masked
  - `sample:` and the Test Center
  - who can edit and run
  - the run log
  - "SSH and CAVE-host targets come later"

- [ ] **Step 1: Write the failing test.**
- [ ] **Step 2:** Run. Expected: FAIL (the fixture script is missing, or the wiring gap).
- [ ] **Step 3:** Add the fixture and fix whatever the test exposes, then write the docs.
- [ ] **Step 4:** Rerun, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -s -m "docs(scripts): scripts guide and exit-gate path test"`

---

## Plan 5 done when

- CI is green: ruff, mypy --strict, pytest. Tests needing `pwsh` skip cleanly where it's absent. CI should install PowerShell so they run: add the steps from Microsoft Learn to `.github/workflows/core.yml` in Task 7.
- Exit-gate item 4 holds in process: a PowerShell script runs from a dashboard button through the runner, and its result is in the audit log. The containerised version is checked in Plan 7.
- Secrets never leave the runner unmasked, path tricks are refused twice, runaway scripts are killed, and an unreachable runner fails fast.
- `LiveEffects.run_script` no longer raises "arrives in plan 5". Plan 4's deferred "scripts aren't guarded" minor is closed.
