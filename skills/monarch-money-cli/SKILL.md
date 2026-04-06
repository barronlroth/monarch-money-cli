---
name: monarch-money-cli
description: "Work in the monarch-money-cli repository: add or polish CLI commands, fix auth or rendering behavior, update tests and README examples, and live-validate the installed `monarch` command against saved Monarch credentials. Use when Codex is modifying files under `src/monarch_cli`, diagnosing command output, extending parser or handler behavior, or reviewing how this repo authenticates, validates, and ships the Monarch Money CLI."
---

# Monarch Money CLI

## Overview

Use this skill to work inside this repository's Monarch CLI. Keep changes centered on the existing parser and handler pattern, preserve the dual auth model, and finish with repo-root tests plus targeted installed-CLI checks when relevant.

## Start Here

- Read `README.md`, `pyproject.toml`, `src/monarch_cli/cli.py`, `src/monarch_cli/client.py`, `src/monarch_cli/config.py`, and `tests/test_cli.py`.
- Read [references/repo-guide.md](references/repo-guide.md) for the current command surface, auth paths, and validation commands.
- Search the parser and handlers with:

```bash
rg -n "add_parser|set_defaults|^async def handle_|run_authenticated_operation" src/monarch_cli/cli.py
```

## Change Commands

- Register subcommands in `build_parser()`.
- Keep the existing shape: parser arguments, `set_defaults(handler=...)`, async `handle_*` function, human-readable output, and `--json` output for machine use where it already fits the command family.
- Prefer shared helpers such as `run_authenticated_operation()`, `emit_json()`, `print_table()`, `print_key_values()`, `format_money()`, and `format_percent()` over one-off logic.
- Normalize Monarch payloads before rendering. Expect list-vs-dict differences, sparse objects that need ID-to-name joins, and numeric zero values that must not be dropped by truthy checks.
- Keep default terminal output concise. Large dumps should require an explicit flag such as `--json`, `--all`, or a wider filter.

## Change Auth Carefully

- Preserve both auth paths: token auth from `auth.json` and saved-session auth from `session.pickle`.
- Do not reintroduce the stale-token trap. Read commands should still fall back to a valid saved session when token auth fails for auth reasons.
- Keep `auth login-web` defaulted to the system browser unless the user explicitly wants `--browser openclaw`.
- Treat anything under `~/.config/monarch-cli` as real user auth state unless env overrides are present.

## Update Tests And Docs

- Add parser coverage plus at least one mocked behavior test in `tests/test_cli.py` for each shipped handler change.
- Keep repo-root unittest discovery working. The suite relies on `tests/_path.py` for the `src/` layout.
- Update `README.md` examples whenever the public command surface changes.

## Validate

- Run the repo test suite:

```bash
python3 -m unittest discover -s tests -q
```

- Reinstall the local CLI when package metadata or console behavior changes:

```bash
./.venv/bin/python -m pip install -e .
```

- Sanity-check help and targeted commands with `./.venv/bin/monarch ...`.
- Use live validation only when saved auth exists and the command is safe. Prefer read-only checks before side-effecting commands.

## Live Checks

- Start with:
  - `./.venv/bin/monarch auth status --check --json`
  - `./.venv/bin/monarch accounts list`
  - `./.venv/bin/monarch transactions list --limit 5`
- Call out explicitly when running `refresh accounts`; it changes external state.

## References

- Use [references/repo-guide.md](references/repo-guide.md) for repo-specific paths, command inventory, and validation shortcuts.
