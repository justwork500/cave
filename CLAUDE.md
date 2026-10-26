# CAVE — notes for Claude Code and contributors

- Python core lives in `core/` (package `cave`). Run from `core/`: `ruff check .`, `mypy --strict cave`, `pytest`.
- Specs: `docs/superpowers/specs/`. Plans: `docs/superpowers/plans/`. The Phase 1 design wins over `docs/CAVE-Design-Framework.md` where they differ.
- Never call real devices or the network in tests.
- Never log secrets, passwords, tokens or keys.
- Every access check goes through `cave.access.evaluate` (and `can_control` / `assert_can_save` built on it).
- Access settings live in the database, never in `/config` files.
- Every user or access change is written to the audit log with old and new values.
- Commits: Conventional Commits, signed off (`git commit -s`).
