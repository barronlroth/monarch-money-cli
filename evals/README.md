# Monarch MCP ↔ CLI parity harness

`monarch_parity.py` compares the official Monarch MCP server configured in Hermes against the local `monarch-money-cli`.

It is deliberately read-only and redacted:

- blocks MCP write tools by name
- blocks CLI `refresh accounts`
- keeps raw Monarch payloads in process memory only
- writes only redacted count/schema/status reports
- ignores generated reports via `.gitignore`

Run from the repo root with Hermes' Python environment:

```bash
/Users/barron/.hermes/hermes-agent/venv/bin/python evals/monarch_parity.py \
  --mode standard \
  --report-dir evals/reports
```

Use `--mode smoke` for categories/tags/accounts plus unsupported-surface inventory.

Generated files:

```text
evals/reports/<run_id>.redacted.json
evals/reports/<run_id>.redacted.md
```

Do not commit generated reports unless you have manually inspected them. The default `.gitignore` keeps them local.
