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

```bash
monarch auth login
```

The CLI stores the saved session at `~/.config/monarch-cli/session.pickle` by default.

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

