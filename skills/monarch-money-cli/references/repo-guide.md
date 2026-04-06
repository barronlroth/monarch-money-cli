# Monarch Money CLI Repo Guide

## Core Files

- `README.md`: public command surface and examples
- `pyproject.toml`: package metadata and `monarch` console entrypoint
- `src/monarch_cli/cli.py`: parser, handlers, auth wrapper, rendering glue
- `src/monarch_cli/client.py`: SDK loading and client creation
- `src/monarch_cli/config.py`: default config dir, auth file, and session file paths
- `tests/test_cli.py`: parser and mocked command behavior tests

## Useful Searches

```bash
rg -n "add_parser|set_defaults|^async def handle_" src/monarch_cli/cli.py
rg -n "run_authenticated_operation|emit_json|print_table|print_key_values|format_money|format_percent" src/monarch_cli/cli.py
rg -n "auth login-web|accounts history|balances recent|refresh accounts" README.md tests/test_cli.py src/monarch_cli/cli.py
```

## Install And Run

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e .
./.venv/bin/monarch --help
```

Use `./.venv/bin/monarch` for local validation so the installed entrypoint matches the current checkout.

## Test Loop

```bash
python3 -m unittest discover -s tests -q
```

The suite is designed to run from the repo root. `tests/_path.py` injects `src/` for imports.

## Auth Model

- Default config dir: `~/.config/monarch-cli`
- Saved token file: `auth.json`
- Saved session file: `session.pickle`
- Env overrides:
  - `MONARCH_CONFIG_DIR`
  - `MONARCH_AUTH_FILE`
  - `MONARCH_SESSION_FILE`
  - `MONARCH_TOKEN`
- Browser login default: `monarch auth login-web` uses the normal system browser
- Optional alternate browser flow: `monarch auth login-web --browser openclaw`

Preserve token-plus-session behavior. The CLI should keep using a valid saved session when a stored token is stale or unauthorized.

## Current Command Surface

- `auth login`
- `auth login-web`
- `auth import-token`
- `auth logout`
- `auth status`
- `accounts list`
- `accounts history`
- `holdings list`
- `transactions list`
- `transactions show`
- `transactions summary`
- `transactions categories`
- `transactions tags`
- `recurring list`
- `budgets list`
- `institutions list`
- `credit history`
- `balances recent`
- `cashflow summary`
- `refresh accounts`

## Current UX Details

- `accounts history` defaults to the last 90 days
- `accounts history` supports `--all`, `--start-date`, `--end-date`, `--days`, `--limit`, and `--summary`
- `balances recent` supports repeated `--account-id`
- Most read commands support `--json`
- `refresh accounts` is the main side-effecting command; treat it more cautiously than read-only commands

## Good Live Smoke Checks

```bash
./.venv/bin/monarch auth status --check --json
./.venv/bin/monarch accounts list
./.venv/bin/monarch accounts history <account-id> --summary
./.venv/bin/monarch transactions list --limit 5
./.venv/bin/monarch balances recent --account-id <account-id>
```

Use live checks after unit tests when auth is already configured and the command does not create surprising external side effects.
