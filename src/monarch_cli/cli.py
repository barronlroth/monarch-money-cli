from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from .client import CLIError, create_client, require_saved_session
from .config import (
    default_auth_file,
    default_session_file,
    ensure_parent_dir,
    load_auth_payload,
    load_auth_token,
    save_auth_payload,
    utcnow_iso,
)
from .dates import current_month_bounds, month_bounds, validate_date_pair
from .render import emit_json, format_money, format_percent, print_key_values, print_table


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="monarch",
        description="CLI wrapper around the unofficial Monarch Money Python client.",
    )
    parser.add_argument(
        "--session-file",
        default=str(default_session_file()),
        help="Path to the saved session file.",
    )
    parser.add_argument(
        "--auth-file",
        default=str(default_auth_file()),
        help="Path to the saved token auth file.",
    )
    parser.add_argument(
        "--timeout",
        default=int(os.environ.get("MONARCH_TIMEOUT", "20")),
        type=int,
        help="API timeout in seconds.",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("MONARCH_TOKEN"),
        help=argparse.SUPPRESS,
    )

    subparsers = parser.add_subparsers(dest="group", required=True)

    json_parent = argparse.ArgumentParser(add_help=False)
    json_parent.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print raw JSON.",
    )

    auth_parser = subparsers.add_parser("auth", help="Manage login state.")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command", required=True)

    login_parser = auth_subparsers.add_parser("login", help="Create or refresh a legacy session.")
    login_parser.add_argument("--email", help="Monarch account email.")
    login_parser.add_argument("--password", help="Monarch account password.")
    login_parser.add_argument(
        "--mfa-secret-key",
        help="Use a TOTP secret for non-interactive MFA.",
    )
    login_parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore any existing saved session and force a fresh login.",
    )
    login_parser.add_argument(
        "--no-save-session",
        action="store_true",
        help="Authenticate without saving the session token to disk.",
    )
    login_parser.set_defaults(handler=handle_auth_login)

    login_web_parser = auth_subparsers.add_parser(
        "login-web",
        parents=[json_parent],
        help="Open Monarch in the OpenClaw browser and save a token.",
    )
    login_web_parser.add_argument(
        "--browser-profile",
        default=os.environ.get("MONARCH_BROWSER_PROFILE", "openclaw"),
        help="OpenClaw browser profile to use.",
    )
    login_web_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.environ.get("MONARCH_LOGIN_TIMEOUT_SECONDS", "300")),
        help="Seconds to wait for web login to complete.",
    )
    login_web_parser.set_defaults(handler=handle_auth_login_web)

    import_token_parser = auth_subparsers.add_parser(
        "import-token",
        parents=[json_parent],
        help="Save a Monarch API token for CLI use.",
    )
    import_token_parser.add_argument(
        "import_token",
        nargs="?",
        help="Token to save. Defaults to MONARCH_TOKEN if omitted.",
    )
    import_token_parser.set_defaults(handler=handle_auth_import_token)

    logout_parser = auth_subparsers.add_parser(
        "logout",
        parents=[json_parent],
        help="Delete saved auth/session state.",
    )
    logout_parser.set_defaults(handler=handle_auth_logout)

    status_parser = auth_subparsers.add_parser(
        "status",
        parents=[json_parent],
        help="Show saved-session status.",
    )
    status_parser.add_argument(
        "--check",
        action="store_true",
        help="Use the saved session to verify API access.",
    )
    status_parser.set_defaults(handler=handle_auth_status)

    accounts_parser = subparsers.add_parser("accounts", help="Inspect accounts.")
    accounts_subparsers = accounts_parser.add_subparsers(
        dest="accounts_command",
        required=True,
    )

    accounts_list_parser = accounts_subparsers.add_parser(
        "list",
        parents=[json_parent],
        help="List connected accounts.",
    )
    accounts_list_parser.set_defaults(handler=handle_accounts_list)

    holdings_parser = subparsers.add_parser("holdings", help="Inspect investment holdings.")
    holdings_subparsers = holdings_parser.add_subparsers(
        dest="holdings_command",
        required=True,
    )

    holdings_list_parser = holdings_subparsers.add_parser(
        "list",
        parents=[json_parent],
        help="List holdings for an investment account.",
    )
    holdings_list_parser.add_argument("account_id", help="Account ID to inspect.")
    holdings_list_parser.set_defaults(handler=handle_holdings_list)

    transactions_parser = subparsers.add_parser(
        "transactions",
        help="Inspect transactions.",
    )
    transactions_subparsers = transactions_parser.add_subparsers(
        dest="transactions_command",
        required=True,
    )

    transactions_list_parser = transactions_subparsers.add_parser(
        "list",
        parents=[json_parent],
        help="List transactions.",
    )
    transactions_list_parser.add_argument("--start-date", help="Filter start date (YYYY-MM-DD).")
    transactions_list_parser.add_argument("--end-date", help="Filter end date (YYYY-MM-DD).")
    transactions_list_parser.add_argument("--search", default="", help="Search text.")
    transactions_list_parser.add_argument("--limit", type=int, default=100, help="Result limit.")
    transactions_list_parser.add_argument("--offset", type=int, default=0, help="Result offset.")
    transactions_list_parser.add_argument(
        "--account-id",
        action="append",
        default=[],
        help="Repeat to filter by account ID.",
    )
    transactions_list_parser.add_argument(
        "--category-id",
        action="append",
        default=[],
        help="Repeat to filter by category ID.",
    )
    transactions_list_parser.add_argument(
        "--tag-id",
        action="append",
        default=[],
        help="Repeat to filter by tag ID.",
    )
    transactions_list_parser.set_defaults(handler=handle_transactions_list)

    transactions_show_parser = transactions_subparsers.add_parser(
        "show",
        parents=[json_parent],
        help="Show transaction details.",
    )
    transactions_show_parser.add_argument("transaction_id", help="Transaction ID to inspect.")
    transactions_show_parser.set_defaults(handler=handle_transaction_show)

    recurring_parser = subparsers.add_parser("recurring", help="Inspect recurring transactions.")
    recurring_subparsers = recurring_parser.add_subparsers(
        dest="recurring_command",
        required=True,
    )

    recurring_list_parser = recurring_subparsers.add_parser(
        "list",
        parents=[json_parent],
        help="List recurring transactions.",
    )
    recurring_list_parser.add_argument("--start-date", help="Filter start date (YYYY-MM-DD).")
    recurring_list_parser.add_argument("--end-date", help="Filter end date (YYYY-MM-DD).")
    recurring_list_parser.set_defaults(handler=handle_recurring_list)

    budgets_parser = subparsers.add_parser("budgets", help="Inspect budgets.")
    budgets_subparsers = budgets_parser.add_subparsers(
        dest="budgets_command",
        required=True,
    )

    budgets_list_parser = budgets_subparsers.add_parser(
        "list",
        parents=[json_parent],
        help="List budget totals for a month.",
    )
    budgets_list_parser.add_argument(
        "--month",
        help="Budget month in YYYY-MM format. Defaults to the current month.",
    )
    budgets_list_parser.set_defaults(handler=handle_budgets_list)

    credit_parser = subparsers.add_parser("credit", help="Inspect credit history.")
    credit_subparsers = credit_parser.add_subparsers(
        dest="credit_command",
        required=True,
    )

    credit_history_parser = credit_subparsers.add_parser(
        "history",
        parents=[json_parent],
        help="Show credit history.",
    )
    credit_history_parser.set_defaults(handler=handle_credit_history)

    balances_parser = subparsers.add_parser("balances", help="Inspect balance history and snapshots.")
    balances_subparsers = balances_parser.add_subparsers(
        dest="balances_command",
        required=True,
    )

    balances_recent_parser = balances_subparsers.add_parser(
        "recent",
        parents=[json_parent],
        help="Show recent account balances.",
    )
    balances_recent_parser.add_argument("--start-date", help="Filter start date (YYYY-MM-DD).")
    balances_recent_parser.set_defaults(handler=handle_balances_recent)

    cashflow_parser = subparsers.add_parser("cashflow", help="Inspect cashflow.")
    cashflow_subparsers = cashflow_parser.add_subparsers(
        dest="cashflow_command",
        required=True,
    )

    cashflow_summary_parser = cashflow_subparsers.add_parser(
        "summary",
        parents=[json_parent],
        help="Show cashflow summary.",
    )
    cashflow_summary_parser.add_argument(
        "--start-date",
        help="Filter start date (YYYY-MM-DD).",
    )
    cashflow_summary_parser.add_argument(
        "--end-date",
        help="Filter end date (YYYY-MM-DD).",
    )
    cashflow_summary_parser.set_defaults(handler=handle_cashflow_summary)

    refresh_parser = subparsers.add_parser("refresh", help="Refresh account data.")
    refresh_subparsers = refresh_parser.add_subparsers(
        dest="refresh_command",
        required=True,
    )

    refresh_accounts_parser = refresh_subparsers.add_parser(
        "accounts",
        parents=[json_parent],
        help="Request an account refresh.",
    )
    refresh_accounts_parser.add_argument(
        "--account-id",
        action="append",
        default=[],
        help="Repeat to refresh specific account IDs. Defaults to all accounts.",
    )
    refresh_accounts_parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for the refresh to complete.",
    )
    refresh_accounts_parser.add_argument(
        "--wait-timeout",
        type=int,
        default=300,
        help="Seconds to wait before giving up when --wait is set.",
    )
    refresh_accounts_parser.add_argument(
        "--wait-delay",
        type=int,
        default=10,
        help="Seconds between status checks when --wait is set.",
    )
    refresh_accounts_parser.set_defaults(handler=handle_refresh_accounts)

    return parser


def session_file_from_args(args: argparse.Namespace) -> Path:
    return Path(args.session_file).expanduser()


def auth_file_from_args(args: argparse.Namespace) -> Path:
    return Path(args.auth_file).expanduser()


def parse_json_from_output(raw: str) -> Any:
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw):
        if char not in "[{":
            continue
        try:
            payload, _ = decoder.raw_decode(raw[index:])
            return payload
        except json.JSONDecodeError:
            continue
    raise CLIError("Failed to parse JSON from OpenClaw browser output.")


def run_openclaw(*args: str) -> str:
    binary = shutil.which("openclaw")
    if not binary:
        raise CLIError("`openclaw` CLI not found. Install OpenClaw or use `monarch auth import-token`.")

    proc = subprocess.run(
        [binary, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()
        detail = stderr or stdout or f"exit code {proc.returncode}"
        raise CLIError(detail)
    return proc.stdout


def extract_browser_token(browser_profile: str) -> dict[str, Any] | None:
    js = (
        '() => { try { '
        'const raw = localStorage.getItem("persist:root"); '
        'if (!raw) return {ok:false}; '
        'const root = JSON.parse(raw); '
        'if (!root.user) return {ok:false}; '
        'const user = JSON.parse(root.user); '
        'return {ok:Boolean(user.token), token:user.token || null, email:user.email || null, name:user.name || null}; '
        '} catch (err) { return {ok:false, error:String(err)}; } }'
    )
    output = run_openclaw(
        "browser",
        "--browser-profile",
        browser_profile,
        "evaluate",
        "--fn",
        js,
    )
    payload = parse_json_from_output(output)
    if isinstance(payload, dict) and payload.get("ok") and payload.get("token"):
        return payload
    return None


def save_token_auth(args: argparse.Namespace, token: str, source: str, metadata: dict[str, Any] | None = None) -> Path:
    auth_file = auth_file_from_args(args)
    now = utcnow_iso()
    payload: dict[str, Any] = {
        "token": token,
        "created_at": now,
        "last_verified_at": now,
        "source": source,
    }
    if metadata:
        payload.update({key: value for key, value in metadata.items() if value is not None})
    return save_auth_payload(auth_file, payload)


def build_verified_payload(details: dict[str, Any]) -> dict[str, Any]:
    subscription = details.get("subscription", {})
    return {
        "authenticated": True,
        "premium": subscription.get("hasPremiumEntitlement"),
        "free_trial": subscription.get("isOnFreeTrial"),
    }


def active_token_from_args(args: argparse.Namespace) -> str | None:
    return args.token or load_auth_token(auth_file_from_args(args))


def nested_value(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return current if current is not None else ""


async def get_authenticated_client(
    args: argparse.Namespace,
) -> tuple[Any, Any]:
    session_file = session_file_from_args(args)
    token = active_token_from_args(args)
    sdk, client = create_client(
        session_file=session_file,
        timeout=args.timeout,
        token=token,
    )

    if token:
        return sdk, client

    require_saved_session(client, session_file)
    return sdk, client


async def handle_auth_login(args: argparse.Namespace) -> int:
    session_file = ensure_parent_dir(session_file_from_args(args))
    sdk, client = create_client(
        session_file=session_file,
        timeout=args.timeout,
        token=args.token,
    )

    email = args.email or os.environ.get("MONARCH_EMAIL")
    password = args.password or os.environ.get("MONARCH_PASSWORD")
    mfa_secret_key = args.mfa_secret_key or os.environ.get("MONARCH_MFA_SECRET_KEY")
    use_saved_session = not args.force
    save_session = not args.no_save_session

    if (email or password) and not (email and password):
        raise CLIError("Provide both --email and --password, or neither for interactive login.")

    if mfa_secret_key and not (email and password):
        raise CLIError(
            "--mfa-secret-key requires --email and --password, or MONARCH_EMAIL and MONARCH_PASSWORD."
        )

    if session_file.exists() and not args.force and not (email and password):
        print_key_values(
            {
                "status": "using existing session",
                "session_file": session_file,
                "saved": True,
            }
        )
        return 0

    try:
        if email and password:
            await client.login(
                email=email,
                password=password,
                use_saved_session=use_saved_session,
                save_session=save_session,
                mfa_secret_key=mfa_secret_key,
            )
        else:
            await client.interactive_login(
                use_saved_session=use_saved_session,
                save_session=save_session,
            )
    except sdk.RequireMFAException as exc:
        raise CLIError(
            "MFA is required. Re-run interactively or provide --mfa-secret-key."
        ) from exc
    except sdk.LoginFailedException as exc:
        raise CLIError(str(exc)) from exc
    except sdk.RequestFailedException as exc:
        raise CLIError(str(exc)) from exc

    print_key_values(
        {
            "status": "logged in",
            "session_file": session_file,
            "saved": session_file.exists(),
        }
    )
    return 0


async def handle_auth_login_web(args: argparse.Namespace) -> int:
    run_openclaw("browser", "--browser-profile", args.browser_profile, "start")
    run_openclaw(
        "browser",
        "--browser-profile",
        args.browser_profile,
        "open",
        "https://app.monarch.com/login?route=%2F",
    )

    deadline = time.time() + args.timeout_seconds
    token_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        token_payload = extract_browser_token(args.browser_profile)
        if token_payload:
            break
        time.sleep(2)

    if not token_payload:
        raise CLIError(
            "Timed out waiting for Monarch web login. Finish the login in the OpenClaw browser, then retry."
        )

    sdk, client = create_client(
        session_file=session_file_from_args(args),
        timeout=args.timeout,
        token=token_payload["token"],
    )
    try:
        details = await client.get_subscription_details()
    except sdk.LoginFailedException as exc:
        raise CLIError(str(exc)) from exc
    except sdk.RequestFailedException as exc:
        raise CLIError(str(exc)) from exc

    auth_file = save_token_auth(
        args,
        token_payload["token"],
        source="login-web",
        metadata={
            "email": token_payload.get("email"),
            "name": token_payload.get("name"),
        },
    )

    payload = {
        "status": "logged in",
        "auth_file": auth_file,
        "source": "login-web",
        **build_verified_payload(details),
    }
    if args.as_json:
        emit_json(payload)
    else:
        print_key_values(payload)
    return 0


async def handle_auth_import_token(args: argparse.Namespace) -> int:
    token = args.import_token or args.token or os.environ.get("MONARCH_TOKEN")
    if not token:
        raise CLIError("Provide a token argument or set MONARCH_TOKEN.")

    sdk, client = create_client(
        session_file=session_file_from_args(args),
        timeout=args.timeout,
        token=token,
    )
    try:
        details = await client.get_subscription_details()
    except sdk.LoginFailedException as exc:
        raise CLIError(str(exc)) from exc
    except sdk.RequestFailedException as exc:
        raise CLIError(str(exc)) from exc

    auth_file = save_token_auth(args, token, source="import-token")
    payload = {
        "status": "token imported",
        "auth_file": auth_file,
        **build_verified_payload(details),
    }
    if args.as_json:
        emit_json(payload)
    else:
        print_key_values(payload)
    return 0


async def handle_auth_logout(args: argparse.Namespace) -> int:
    session_file = session_file_from_args(args)
    auth_file = auth_file_from_args(args)
    session_removed = session_file.exists()
    auth_removed = auth_file.exists()
    if session_removed:
        session_file.unlink()
    if auth_removed:
        auth_file.unlink()

    payload = {
        "status": "logged out",
        "session_file": session_file,
        "session_removed": session_removed,
        "auth_file": auth_file,
        "auth_removed": auth_removed,
    }
    if args.as_json:
        emit_json(payload)
    else:
        print_key_values(payload)
    return 0


async def handle_auth_status(args: argparse.Namespace) -> int:
    session_file = session_file_from_args(args)
    auth_file = auth_file_from_args(args)
    auth_payload = load_auth_payload(auth_file)
    token = active_token_from_args(args)
    payload: dict[str, Any] = {
        "session_file": session_file,
        "session_exists": session_file.exists(),
        "auth_file": auth_file,
        "auth_exists": auth_file.exists(),
        "source": auth_payload.get("source") if auth_payload else None,
        "email": auth_payload.get("email") if auth_payload else None,
    }

    if args.check:
        if not token and not session_file.exists():
            raise CLIError(
                f"No saved auth found at `{auth_file}` and no saved session at `{session_file}`. Run `monarch auth login-web` or `monarch auth import-token` first."
            )

        sdk, client = create_client(
            session_file=session_file,
            timeout=args.timeout,
            token=token,
        )
        if not token:
            client.load_session(str(session_file))

        try:
            details = await client.get_subscription_details()
        except sdk.LoginFailedException as exc:
            raise CLIError(str(exc)) from exc
        except sdk.RequestFailedException as exc:
            raise CLIError(str(exc)) from exc

        payload.update(build_verified_payload(details))
        if auth_payload:
            auth_payload["last_verified_at"] = utcnow_iso()
            save_auth_payload(auth_file, auth_payload)
            payload["last_verified_at"] = auth_payload["last_verified_at"]

    if args.as_json:
        emit_json(payload)
    else:
        print_key_values(payload)
    return 0


async def handle_accounts_list(args: argparse.Namespace) -> int:
    sdk, client = await get_authenticated_client(args)
    try:
        response = await client.get_accounts()
    except sdk.RequestFailedException as exc:
        raise CLIError(str(exc)) from exc

    if args.as_json:
        emit_json(response)
        return 0

    rows = []
    for account in response.get("accounts", []):
        rows.append(
            [
                account.get("id", ""),
                account.get("displayName", ""),
                format_money(account.get("displayBalance") or account.get("currentBalance")),
                nested_value(account, "type", "display"),
                nested_value(account, "institution", "name"),
                account.get("displayLastUpdatedAt", ""),
            ]
        )

    print_table(
        ["id", "name", "balance", "type", "institution", "last_updated"],
        rows,
    )
    return 0


async def handle_holdings_list(args: argparse.Namespace) -> int:
    sdk, client = await get_authenticated_client(args)
    try:
        response = await client.get_account_holdings(int(args.account_id))
    except (sdk.RequestFailedException, ValueError) as exc:
        raise CLIError(str(exc)) from exc

    if args.as_json:
        emit_json(response)
        return 0

    edges = nested_value(response, "portfolio", "aggregateHoldings", "edges") or []
    rows = []
    for edge in edges:
        holding = edge.get("node", {})
        rows.append(
            [
                nested_value(holding, "security", "ticker") or nested_value(holding, "security", "name"),
                format_money(holding.get("quantity")),
                format_money(holding.get("totalValue") or holding.get("value") or holding.get("marketValue")),
                format_money(holding.get("basis") or holding.get("costBasis")),
                nested_value(holding, "security", "typeDisplay"),
            ]
        )

    print_table(["security", "quantity", "value", "basis", "type"], rows)
    return 0


async def handle_transactions_list(args: argparse.Namespace) -> int:
    validate_date_pair(args.start_date, args.end_date)
    sdk, client = await get_authenticated_client(args)
    try:
        response = await client.get_transactions(
            limit=args.limit,
            offset=args.offset,
            start_date=args.start_date,
            end_date=args.end_date,
            search=args.search,
            account_ids=args.account_id,
            category_ids=args.category_id,
            tag_ids=args.tag_id,
        )
    except sdk.RequestFailedException as exc:
        raise CLIError(str(exc)) from exc

    if args.as_json:
        emit_json(response)
        return 0

    transactions = response.get("allTransactions", {})
    rows = []
    for transaction in transactions.get("results", []):
        merchant_name = nested_value(transaction, "merchant", "name") or transaction.get("plaidName", "")
        rows.append(
            [
                transaction.get("date", ""),
                merchant_name,
                nested_value(transaction, "account", "displayName"),
                nested_value(transaction, "category", "name"),
                format_money(transaction.get("amount")),
                transaction.get("pending", False),
                transaction.get("id", ""),
            ]
        )

    print_table(
        ["date", "merchant", "account", "category", "amount", "pending", "id"],
        rows,
    )
    total_count = transactions.get("totalCount")
    if total_count is not None:
        print(f"\nShown {len(rows)} of {total_count} transactions.")
    return 0


async def handle_transaction_show(args: argparse.Namespace) -> int:
    sdk, client = await get_authenticated_client(args)
    try:
        response = await client.get_transaction_details(args.transaction_id)
    except sdk.RequestFailedException as exc:
        raise CLIError(str(exc)) from exc

    if args.as_json:
        emit_json(response)
        return 0

    transaction = response.get("getTransaction", {})
    payload = {
        "id": transaction.get("id", ""),
        "date": transaction.get("date", ""),
        "amount": format_money(transaction.get("amount")),
        "merchant": nested_value(transaction, "merchant", "name"),
        "account": nested_value(transaction, "account", "displayName"),
        "category_id": nested_value(transaction, "category", "id"),
        "pending": transaction.get("pending", False),
        "recurring": transaction.get("isRecurring", False),
        "hidden": transaction.get("hideFromReports", False),
        "notes": transaction.get("notes", ""),
        "attachments": len(transaction.get("attachments", [])),
        "tags": ", ".join(tag.get("name", "") for tag in transaction.get("tags", [])),
    }
    print_key_values(payload)
    return 0


async def handle_recurring_list(args: argparse.Namespace) -> int:
    validate_date_pair(args.start_date, args.end_date)
    sdk, client = await get_authenticated_client(args)
    try:
        response = await client.get_recurring_transactions(
            start_date=args.start_date,
            end_date=args.end_date,
        )
    except sdk.RequestFailedException as exc:
        raise CLIError(str(exc)) from exc

    if args.as_json:
        emit_json(response)
        return 0

    rows = []
    items = response.get("recurringTransactionItems") or response.get("recurringTransactionStreamGroups") or []
    for item in items:
        stream = item.get("stream", {})
        merchant = nested_value(stream, "merchant", "name") or nested_value(item, "merchant", "name")
        rows.append(
            [
                item.get("date", "") or item.get("nextOccurrenceDate", ""),
                merchant,
                stream.get("frequency", item.get("frequency", "")),
                format_money(item.get("amount") or stream.get("amount")),
                nested_value(item, "category", "name"),
            ]
        )

    print_table(["date", "merchant", "frequency", "amount", "category"], rows)
    return 0


async def handle_budgets_list(args: argparse.Namespace) -> int:
    sdk, client = await get_authenticated_client(args)

    if args.month:
        start_date, end_date = month_bounds(args.month)
    else:
        start_date, end_date = current_month_bounds()

    try:
        response = await client.get_budgets(start_date=start_date, end_date=end_date)
    except sdk.RequestFailedException as exc:
        raise CLIError(str(exc)) from exc

    if args.as_json:
        emit_json(response)
        return 0

    totals = nested_value(response, "budgetData", "totalsByMonth")
    rows = []
    for total in totals or []:
        rows.append(
            [
                total.get("month", ""),
                format_money(nested_value(total, "totalIncome", "plannedAmount")),
                format_money(nested_value(total, "totalIncome", "actualAmount")),
                format_money(nested_value(total, "totalExpenses", "plannedAmount")),
                format_money(nested_value(total, "totalExpenses", "actualAmount")),
            ]
        )

    print_table(
        [
            "month",
            "income_planned",
            "income_actual",
            "expense_planned",
            "expense_actual",
        ],
        rows,
    )
    return 0


async def handle_credit_history(args: argparse.Namespace) -> int:
    sdk, client = await get_authenticated_client(args)
    try:
        response = await client.get_credit_history()
    except sdk.RequestFailedException as exc:
        raise CLIError(str(exc)) from exc

    if args.as_json:
        emit_json(response)
        return 0

    items = response.get("creditScoreSnapshots") or response.get("creditScoreHistory") or []
    rows = []
    for item in items:
        rows.append([
            item.get("date", ""),
            item.get("score", ""),
            item.get("rating", ""),
        ])

    if rows:
        print_table(["date", "score", "rating"], rows)
    else:
        print_key_values(
            {
                "status": nested_value(response, "spinwheelUser", "creditScoreTrackingStatus") or "unknown",
                "snapshots": len(items),
            }
        )
    return 0


async def handle_balances_recent(args: argparse.Namespace) -> int:
    sdk, client = await get_authenticated_client(args)
    try:
        response = await client.get_recent_account_balances(start_date=args.start_date)
    except sdk.RequestFailedException as exc:
        raise CLIError(str(exc)) from exc

    if args.as_json:
        emit_json(response)
        return 0

    rows = []
    balances = response.get("accounts") or response.get("recentAccountBalances") or []
    for item in balances:
        series = item.get("recentBalances") or []
        latest = series[-1] if series else item.get("currentBalance") or item.get("balance")
        rows.append([
            item.get("id", ""),
            item.get("displayName") or item.get("name", ""),
            format_money(latest),
            len(series),
        ])
    print_table(["id", "account", "latest_balance", "points"], rows)
    return 0


async def handle_cashflow_summary(args: argparse.Namespace) -> int:
    validate_date_pair(args.start_date, args.end_date)
    sdk, client = await get_authenticated_client(args)
    try:
        response = await client.get_cashflow_summary(
            start_date=args.start_date,
            end_date=args.end_date,
        )
    except sdk.RequestFailedException as exc:
        raise CLIError(str(exc)) from exc

    if args.as_json:
        emit_json(response)
        return 0

    summary_root = response.get("summary")
    if isinstance(summary_root, list):
        summary = nested_value(summary_root[0] if summary_root else {}, "summary")
    else:
        summary = nested_value(response, "summary", "summary")
    payload = {
        "income": format_money(nested_value(summary, "sumIncome")),
        "expense": format_money(nested_value(summary, "sumExpense")),
        "savings": format_money(nested_value(summary, "savings")),
        "savings_rate": format_percent(nested_value(summary, "savingsRate")),
    }
    print_key_values(payload)
    return 0


async def handle_refresh_accounts(args: argparse.Namespace) -> int:
    sdk, client = await get_authenticated_client(args)
    account_ids = list(args.account_id)

    if not account_ids:
        try:
            response = await client.get_accounts()
        except sdk.RequestFailedException as exc:
            raise CLIError(str(exc)) from exc
        account_ids = [account.get("id", "") for account in response.get("accounts", [])]
        account_ids = [account_id for account_id in account_ids if account_id]

    if not account_ids:
        raise CLIError("No accounts found to refresh.")

    try:
        if args.wait:
            completed = await client.request_accounts_refresh_and_wait(
                account_ids=account_ids,
                timeout=args.wait_timeout,
                delay=args.wait_delay,
            )
        else:
            await client.request_accounts_refresh(account_ids)
            completed = True
    except sdk.RequestFailedException as exc:
        raise CLIError(str(exc)) from exc

    payload = {
        "requested": len(account_ids),
        "waited": args.wait,
        "completed": completed,
    }

    if args.as_json:
        emit_json(payload)
    else:
        print_key_values(payload)

    if args.wait and not completed:
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = args.handler(args)
        if inspect.isawaitable(result):
            return asyncio.run(result)
        return int(result or 0)
    except (CLIError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
