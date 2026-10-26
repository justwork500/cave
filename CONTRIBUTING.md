# Contributing to CAVE

Thanks for helping. A few rules keep the project healthy.

## Sign your commits (DCO)

CAVE uses the [Developer Certificate of Origin](https://developercertificate.org/) instead of a CLA. Sign off every commit:

```bash
git commit -s -m "feat(core): ..."
```

## Before you open a pull request

From `core/`:

```bash
ruff check .
mypy --strict cave
pytest
```

All three must pass. CI runs the same commands.

## Rules

1. Tests never touch real devices, clouds or the network. Use fixtures.
2. Never log secrets, passwords, tokens or keys.
3. Every access decision goes through `cave.access.evaluate`. Never check permissions only in the UI.
4. Architecture changes need an ADR in `docs/adr/` before code.
5. Commit messages follow Conventional Commits (`feat:`, `fix:`, `docs:`, …).
6. No Home Assistant code, branding or trade dress. Open protocols are fine.
