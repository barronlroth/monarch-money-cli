# monarch-money-cli

Small CLI wrapper around the unofficial `monarchmoney` Python client.

## Status

This repo currently targets a practical V1:

- `auth login`
- `auth logout`
- `auth status`
- `accounts list`
- `transactions list`
- `transactions show`
- `budgets list`
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

Legacy password/session login still exists as `monarch auth login`, but Monarch's old REST login flow is brittle and should not be the default path.

## Examples

```bash
monarch accounts list
monarch transactions list --limit 20
monarch transactions show <transaction-id>
monarch budgets list --month 2026-04
monarch cashflow summary --start-date 2026-04-01 --end-date 2026-04-30
monarch refresh accounts --wait
```

## JSON Output

Most read commands support `--json` for scripting.

```bash
monarch transactions list --limit 50 --json
```

