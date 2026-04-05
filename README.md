# monarch-money-cli

Read-first CLI for Monarch Money built on the maintained `monarchmoneycommunity` backend.

## Status

Current focus is read-heavy CLI access with simple auth:

- `auth login`
- `auth login-web`
- `auth import-token`
- `auth logout`
- `auth status`
- `accounts list`
- `holdings list`
- `transactions list`
- `transactions show`
- `recurring list`
- `budgets list`
- `credit history`
- `balances recent`
- `cashflow summary`
- `refresh accounts`

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Login

Preferred flow:

```bash
monarch auth login-web
```

This uses the OpenClaw browser, extracts a Monarch API token after web login, and saves it to `~/.config/monarch-cli/auth.json` by default.

Fallback:

```bash
monarch auth import-token <token>
```

`monarch auth login` still works for password/session-based login through the maintained community backend, but `login-web` and `import-token` are often simpler.

## Examples

```bash
monarch accounts list
monarch holdings list <account-id>
monarch transactions list --limit 20
monarch transactions show <transaction-id>
monarch recurring list
monarch budgets list --month 2026-04
monarch credit history
monarch balances recent
monarch cashflow summary --start-date 2026-04-01 --end-date 2026-04-30
monarch refresh accounts --wait
```

## JSON Output

Most read commands support `--json` for scripting.

```bash
monarch transactions list --limit 50 --json
```

