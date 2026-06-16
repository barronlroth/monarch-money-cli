#!/usr/bin/env python3
"""Redacted parity harness: Monarch MCP vs local monarch-money-cli.

Runs read-only comparison cases through both surfaces, normalizes response shapes,
and writes only redacted status/schema/count metadata. Raw Monarch payloads remain
in process memory and are never written by default.

Run with Hermes' venv so the internal MCP client and OAuth stack are available:

    /Users/barron/.hermes/hermes-agent/venv/bin/python evals/monarch_parity.py \
      --mode standard --report-dir evals/reports
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable

DEFAULT_HERMES_AGENT_DIR = Path(os.environ.get("HERMES_AGENT_DIR", "/Users/barron/.hermes/hermes-agent"))
DEFAULT_CLI = Path(os.environ.get("MONARCH_PARITY_CLI", "/Users/barron/Developer/monarch-money-cli/.venv/bin/monarch"))
DEFAULT_CLI_REPO = DEFAULT_CLI.parents[2] if DEFAULT_CLI.name == "monarch" and len(DEFAULT_CLI.parents) >= 3 else Path.cwd()

FORBIDDEN_REPORT_PATTERNS = [
    re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),  # card-ish
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # ssn-ish
    re.compile(r"(?i)bearer\s+[a-z0-9._-]+"),
    re.compile(r"(?i)(token|secret|password|authorization)['\"\s:=]+[a-z0-9._~+/=-]{12,}"),
]

WRITE_TOOL_RE = re.compile(r"^(Create|Update|Delete|Bulk|Merge|Report)")


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def bucket_count(n: int | None) -> str:
    if n is None:
        return "unknown"
    if n == 0:
        return "0"
    if n < 10:
        return "1-9"
    if n < 100:
        return "10-99"
    if n < 1000:
        return "100-999"
    return "1000+"


def sha12(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def type_name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, int):
        return "int"
    if isinstance(v, float):
        return "float"
    if isinstance(v, str):
        return "str"
    if isinstance(v, list):
        return "list"
    if isinstance(v, dict):
        return "dict"
    return type(v).__name__


def flatten_first_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        preferred = [
            "transactions", "categories", "category_groups", "groups", "tags", "accounts",
            "recurring", "items", "data", "results", "budget", "holdings", "investments",
            "readings", "merchants", "rules", "snapshots",
        ]
        for key in preferred:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        for value in payload.values():
            if isinstance(value, list):
                return value
    return []


def record_keys(records: list[Any], max_records: int = 50) -> list[str]:
    keys: Counter[str] = Counter()
    for row in records[:max_records]:
        if isinstance(row, dict):
            keys.update(row.keys())
    return sorted(keys)


def schema_summary(payload: Any, *, domain: str | None = None) -> dict[str, Any]:
    """Return redacted count/schema metadata for a payload."""
    if domain == "count_object" and isinstance(payload, dict):
        for key in ("transaction_count", "total_count", "count"):
            if isinstance(payload.get(key), int):
                count = payload[key]
                return {
                    "record_count": count,
                    "count_bucket": bucket_count(count),
                    "keys": sorted(payload.keys()),
                    "first_types": {k: type_name(v) for k, v in list(payload.items())[:30]},
                }

    if domain == "categories" and isinstance(payload, dict):
        groups = payload.get("category_groups") or payload.get("groups") or []
        if groups and all(isinstance(g, dict) and isinstance(g.get("categories"), list) for g in groups):
            records = [c for g in groups for c in g.get("categories", []) if isinstance(c, dict)]
            first = next((r for r in records if isinstance(r, dict)), {})
            return {
                "record_count": len(records),
                "count_bucket": bucket_count(len(records)),
                "keys": record_keys(records),
                "first_types": {k: type_name(v) for k, v in list(first.items())[:30]},
                "container_count_bucket": bucket_count(len(groups)),
                "container_keys": record_keys(groups),
            }

    if domain == "recurring" and isinstance(payload, dict):
        records: list[Any] = []
        for key, value in payload.items():
            if "recurring" in key.lower() and isinstance(value, list):
                records.extend(value)
        if records:
            first = next((r for r in records if isinstance(r, dict)), {})
            return {
                "record_count": len(records),
                "count_bucket": bucket_count(len(records)),
                "keys": record_keys(records),
                "first_types": {k: type_name(v) for k, v in list(first.items())[:30]},
                "container_keys": sorted(payload.keys()),
            }

    if domain == "credit" and isinstance(payload, dict):
        for key in ("snapshots", "creditScoreSnapshots"):
            value = payload.get(key)
            if isinstance(value, list):
                first = next((r for r in value if isinstance(r, dict)), {})
                return {
                    "record_count": len(value),
                    "count_bucket": bucket_count(len(value)),
                    "keys": record_keys(value),
                    "first_types": {k: type_name(v) for k, v in list(first.items())[:30]},
                    "container_keys": sorted(payload.keys()),
                }

    records = flatten_first_list(payload)
    if records:
        first = next((r for r in records if isinstance(r, dict)), {})
        return {
            "record_count": len(records),
            "count_bucket": bucket_count(len(records)),
            "keys": record_keys(records),
            "first_types": {k: type_name(v) for k, v in list(first.items())[:30]},
        }

    if isinstance(payload, dict):
        return {
            "record_count": None,
            "count_bucket": "object",
            "keys": sorted(payload.keys()),
            "first_types": {k: type_name(v) for k, v in list(payload.items())[:30]},
        }

    return {"record_count": None, "count_bucket": type_name(payload), "keys": [], "first_types": {}}


def compare_schema(mcp_summary: dict[str, Any], cli_summary: dict[str, Any]) -> dict[str, Any]:
    mcp_keys = set(mcp_summary.get("keys", []))
    cli_keys = set(cli_summary.get("keys", []))
    return {
        "shared_keys": sorted(mcp_keys & cli_keys),
        "mcp_only_keys": sorted(mcp_keys - cli_keys),
        "cli_only_keys": sorted(cli_keys - mcp_keys),
        "mcp_keys_hash": sha12(sorted(mcp_keys)),
        "cli_keys_hash": sha12(sorted(cli_keys)),
    }


class MCPAdapter:
    def __init__(self, hermes_agent_dir: Path):
        self.hermes_agent_dir = hermes_agent_dir
        sys.path.insert(0, str(hermes_agent_dir))
        os.chdir(hermes_agent_dir)
        from tools import mcp_tool  # type: ignore

        self.mcp_tool = mcp_tool
        self.tool_names = self.mcp_tool.discover_mcp_tools()

    def call(self, tool: str, args: dict[str, Any]) -> tuple[Any, int]:
        if WRITE_TOOL_RE.match(tool):
            raise RuntimeError(f"blocked_write_tool:{tool}")
        started = time.monotonic()
        handler = self.mcp_tool._make_tool_handler("monarch", tool, 180)
        raw = handler(args)
        elapsed = int((time.monotonic() - started) * 1000)
        outer = json.loads(raw)
        if "error" in outer:
            raise RuntimeError("mcp_error:" + str(outer["error"])[:180])
        result = outer.get("result")
        if isinstance(result, str):
            text = result.strip()
            if text.startswith("{") or text.startswith("["):
                try:
                    return json.loads(text), elapsed
                except json.JSONDecodeError:
                    return {"text_result": text}, elapsed
            return {"text_result": text}, elapsed
        return result, elapsed


class CLIAdapter:
    def __init__(self, executable: Path, repo: Path, timeout: int = 120):
        self.executable = executable
        self.repo = repo
        self.timeout = timeout

    def call(self, args: list[str]) -> tuple[Any, int]:
        if args[:2] == ["refresh", "accounts"]:
            raise RuntimeError("blocked_side_effect:refresh_accounts")
        started = time.monotonic()
        cp = subprocess.run(
            [str(self.executable), *args],
            cwd=str(self.repo),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.timeout,
        )
        elapsed = int((time.monotonic() - started) * 1000)
        if cp.returncode != 0:
            raise RuntimeError(f"cli_exit_{cp.returncode}")
        stdout = cp.stdout.strip()
        return (json.loads(stdout) if stdout else None), elapsed

    def transactions_paged(
        self,
        *,
        start_date: str,
        end_date: str,
        page_size: int = 100,
        max_pages: int = 50,
    ) -> tuple[list[Any], int, dict[str, Any]]:
        records: list[Any] = []
        total_ms = 0
        pages = 0
        for page in range(max_pages):
            offset = page * page_size
            payload, ms = self.call([
                "transactions", "list",
                "--start-date", start_date,
                "--end-date", end_date,
                "--limit", str(page_size),
                "--offset", str(offset),
                "--json",
            ])
            total_ms += ms
            page_records = payload if isinstance(payload, list) else flatten_first_list(payload)
            records.extend(page_records)
            pages += 1
            if len(page_records) < page_size:
                break
        return records, total_ms, {"pages": pages, "page_size": page_size, "hit_max_pages": pages >= max_pages}


def make_case(
    case_id: str,
    *,
    mcp: MCPAdapter | None = None,
    cli: CLIAdapter | None = None,
    mcp_tool_name: str | None = None,
    mcp_args: dict[str, Any] | None = None,
    cli_args: list[str] | None = None,
    cli_payload_factory: Callable[[], tuple[Any, int, dict[str, Any]]] | None = None,
    domain: str | None = None,
    compare_counts: bool = True,
    note: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "case_id": case_id,
        "status": "ERROR",
        "note": note,
        "mcp_ms": None,
        "cli_ms": None,
        "comparison": {},
    }
    try:
        if mcp and mcp_tool_name:
            mcp_payload, mcp_ms = mcp.call(mcp_tool_name, mcp_args or {})
            mcp_summary = schema_summary(mcp_payload, domain=domain)
            result["mcp_ms"] = mcp_ms
        else:
            mcp_summary = {"record_count": None, "count_bucket": "unsupported", "keys": []}

        extra: dict[str, Any] = {}
        if cli_payload_factory:
            cli_payload, cli_ms, extra = cli_payload_factory()
            cli_summary = schema_summary(cli_payload, domain=domain)
            result["cli_ms"] = cli_ms
        elif cli and cli_args:
            cli_payload, cli_ms = cli.call(cli_args)
            cli_summary = schema_summary(cli_payload, domain=domain)
            result["cli_ms"] = cli_ms
        else:
            cli_summary = {"record_count": None, "count_bucket": "unsupported", "keys": []}

        exact_count_match = None
        if mcp_summary.get("record_count") is not None and cli_summary.get("record_count") is not None:
            exact_count_match = mcp_summary["record_count"] == cli_summary["record_count"]

        result["comparison"] = {
            "exact_count_match": exact_count_match,
            "mcp_count_bucket": mcp_summary.get("count_bucket"),
            "cli_count_bucket": cli_summary.get("count_bucket"),
            "schema": compare_schema(mcp_summary, cli_summary),
            "cli_pagination": extra or None,
        }

        if compare_counts and exact_count_match is False:
            result["status"] = "FAIL"
        elif compare_counts and exact_count_match is True:
            result["status"] = "PASS"
        elif result["comparison"]["schema"]["shared_keys"]:
            result["status"] = "WARN"
        else:
            result["status"] = "WARN"
        return result
    except Exception as exc:
        result["status"] = "ERROR"
        clean_error = re.sub(r"\s+", " ", str(exc))[:180]
        result["note"] = f"{note} {clean_error}".strip()
        return result


def status_rollup(cases: list[dict[str, Any]]) -> str:
    statuses = {c["status"] for c in cases}
    if "ERROR" in statuses:
        return "ERROR"
    if "FAIL" in statuses:
        return "FAIL"
    if "WARN" in statuses:
        return "WARN"
    return "PASS"


def redaction_scan(text: str) -> tuple[str, list[str]]:
    failures = []
    for pattern in FORBIDDEN_REPORT_PATTERNS:
        if pattern.search(text):
            failures.append(pattern.pattern)
    return ("FAIL" if failures else "PASS"), failures


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Monarch MCP vs CLI parity run — `{report['run_id']}`",
        "",
        f"- Date: `{report['started_at']}`",
        f"- Mode: `{report['mode']}`",
        f"- Overall status: **{report['overall_status']}**",
        f"- Redaction status: **{report['redaction_status']}**",
        f"- Scope: {report['scope']}",
        "",
        "| Case | Status | Count match | MCP bucket | CLI bucket | MCP ms | CLI ms | Note |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for case in report["cases"]:
        comparison = case.get("comparison") or {}
        note = (case.get("note") or "").replace("|", "/")
        lines.append(
            f"| `{case['case_id']}` | {case['status']} | {comparison.get('exact_count_match', 'n/a')} | "
            f"`{comparison.get('mcp_count_bucket', '—')}` | `{comparison.get('cli_count_bucket', '—')}` | "
            f"{case.get('mcp_ms') or '—'} | {case.get('cli_ms') or '—'} | {note} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Redacted Monarch MCP ↔ CLI parity harness")
    parser.add_argument("--mode", choices=["smoke", "standard"], default="standard")
    parser.add_argument("--report-dir", type=Path, default=Path("evals/reports"))
    parser.add_argument("--hermes-agent-dir", type=Path, default=DEFAULT_HERMES_AGENT_DIR)
    parser.add_argument("--cli", type=Path, default=DEFAULT_CLI)
    parser.add_argument("--cli-repo", type=Path, default=DEFAULT_CLI_REPO)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=50)
    args = parser.parse_args()
    initial_cwd = Path.cwd()
    if not args.report_dir.is_absolute():
        args.report_dir = (initial_cwd / args.report_dir).resolve()
    args.cli = args.cli.resolve()
    args.cli_repo = args.cli_repo.resolve()
    args.hermes_agent_dir = args.hermes_agent_dir.resolve()

    now = utc_now()
    today = dt.date.today()
    first_this_month = today.replace(day=1)
    last_month_end = first_this_month - dt.timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    d30_start = today - dt.timedelta(days=30)

    run_id = "parity_" + now.strftime("%Y%m%dT%H%M%SZ")
    mcp = MCPAdapter(args.hermes_agent_dir)
    cli = CLIAdapter(args.cli, args.cli_repo)

    cases: list[dict[str, Any]] = []
    cases.append(make_case(
        "categories_all", mcp=mcp, cli=cli, mcp_tool_name="GetCategories", mcp_args={},
        cli_args=["transactions", "categories", "--json"], domain="categories",
        note="MCP category groups flattened to category rows.",
    ))
    cases.append(make_case(
        "tags_all", mcp=mcp, cli=cli, mcp_tool_name="GetTags", mcp_args={},
        cli_args=["transactions", "tags", "--json"], note="Metadata parity.",
    ))
    cases.append(make_case(
        "accounts_all", mcp=mcp, cli=cli, mcp_tool_name="GetAccounts", mcp_args={},
        cli_args=["accounts", "list", "--json"],
        note="Sensitive; redacted count/schema only. Count mismatch usually means visibility/default filter differences.",
    ))

    if args.mode == "standard":
        cases.append(make_case(
            "transactions_last_month_paged_count", mcp=mcp, cli=cli,
            mcp_tool_name="GetTransactions",
            mcp_args={
                "start_date": last_month_start.isoformat(),
                "end_date": last_month_end.isoformat(),
                "total_count_only": True,
                "filters": '{"transaction_type":"All"}',
            },
            cli_payload_factory=lambda: cli.transactions_paged(
                start_date=last_month_start.isoformat(),
                end_date=last_month_end.isoformat(),
                page_size=args.page_size,
                max_pages=args.max_pages,
            ),
            domain="count_object",
            note="CLI paged by offset until exhausted; values redacted.",
        ))
        cases.append(make_case(
            "transactions_recent_30d_page", mcp=mcp, cli=cli,
            mcp_tool_name="GetTransactions",
            mcp_args={
                "start_date": d30_start.isoformat(),
                "end_date": today.isoformat(),
                "limit": 20,
                "filters": '{"transaction_type":"All"}',
            },
            cli_args=[
                "transactions", "list", "--start-date", d30_start.isoformat(),
                "--end-date", today.isoformat(), "--limit", "20", "--json",
            ],
            compare_counts=False,
            note="Page-shape smoke only; exact rows may differ by sort semantics.",
        ))
        cases.append(make_case(
            "recurring_confirmed", mcp=mcp, cli=cli, mcp_tool_name="GetRecurring",
            mcp_args={"include_liabilities": True, "include_pending": False},
            cli_args=["recurring", "list", "--json"], domain="recurring", compare_counts=False,
            note="MCP bucketed streams vs CLI flat rows; values redacted.",
        ))
        cases.append(make_case(
            "budgets_current_month", mcp=mcp, cli=cli, mcp_tool_name="GetBudget",
            mcp_args={"start_date": first_this_month.isoformat(), "end_date": first_this_month.isoformat(), "include_actuals": True},
            cli_args=["budgets", "list", "--month", first_this_month.strftime("%Y-%m"), "--json"],
            compare_counts=False,
            note="Budget values redacted; schema-shape comparison only.",
        ))
        cases.append(make_case(
            "cashflow_last_month", mcp=mcp, cli=cli, mcp_tool_name="GetCashFlow",
            mcp_args={"start_date": last_month_start.isoformat(), "end_date": last_month_end.isoformat()},
            cli_args=["cashflow", "summary", "--start-date", last_month_start.isoformat(), "--end-date", last_month_end.isoformat(), "--json"],
            compare_counts=False,
            note="Aggregate values redacted; schema-shape comparison only.",
        ))
        cases.append(make_case(
            "networth_history_30d", mcp=mcp, cli=cli, mcp_tool_name="GetNetWorthHistory",
            mcp_args={"start_date": d30_start.isoformat(), "end_date": today.isoformat()},
            cli_args=["networth", "history", "--start-date", d30_start.isoformat(), "--end-date", today.isoformat(), "--json"],
            note="Sensitive; date-bucket/read-count parity only.",
        ))
        cases.append(make_case(
            "credit_history_12m", mcp=mcp, cli=cli, mcp_tool_name="GetCreditScoreHistory",
            mcp_args={"start_date": (today - dt.timedelta(days=365)).isoformat(), "end_date": today.isoformat()},
            cli_args=["credit", "history", "--json"], domain="credit", compare_counts=False,
            note="Raw scores redacted; schema/count bucket only.",
        ))

    cases.extend([
        {"case_id": "institutions_list", "status": "SKIP_UNSUPPORTED", "note": "CLI has institution/sync-status read; MCP has no direct equivalent found.", "mcp_ms": None, "cli_ms": None, "comparison": {}},
        {"case_id": "refresh_accounts", "status": "SKIP_UNSUPPORTED", "note": "CLI refresh is a side effect and excluded; MCP has no equivalent found.", "mcp_ms": None, "cli_ms": None, "comparison": {}},
        {"case_id": "mcp_write_surface", "status": "SKIP_UNSUPPORTED", "note": "MCP exposes write tools not present in read-first CLI; inventoried but not run.", "mcp_ms": None, "cli_ms": None, "comparison": {}},
    ])

    report: dict[str, Any] = {
        "run_id": run_id,
        "started_at": now.isoformat().replace("+00:00", "Z"),
        "mode": args.mode,
        "scope": "read-only parity with sensitive values redacted",
        "overall_status": status_rollup(cases),
        "redaction_status": "PASS",
        "date_windows": {
            "today": today.isoformat(),
            "last_month_start": last_month_start.isoformat(),
            "last_month_end": last_month_end.isoformat(),
            "d30_start": d30_start.isoformat(),
        },
        "mcp_tools_discovered_count": len([name for name in mcp.tool_names if name.startswith("mcp_monarch_")]),
        "cli_executable": str(args.cli),
        "cases": cases,
    }

    args.report_dir.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
    md_text = markdown_report(report)
    redaction_status, failures = redaction_scan(json_text + "\n" + md_text)
    report["redaction_status"] = redaction_status
    report["redaction_failures"] = failures
    if redaction_status == "FAIL":
        report["overall_status"] = "ERROR"
        json_text = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False)
        md_text = markdown_report(report)

    json_path = args.report_dir / f"{run_id}.redacted.json"
    md_path = args.report_dir / f"{run_id}.redacted.md"
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(md_text, encoding="utf-8")

    print(json.dumps({
        "run_id": run_id,
        "overall_status": report["overall_status"],
        "redaction_status": report["redaction_status"],
        "json_report": str(json_path),
        "markdown_report": str(md_path),
        "cases": [{"case_id": c["case_id"], "status": c["status"]} for c in cases],
    }, indent=2, sort_keys=True))
    return 0 if report["redaction_status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
