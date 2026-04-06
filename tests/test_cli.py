import asyncio
import contextlib
import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import _path

from monarch_cli import cli
from monarch_cli.client import CLIError


class LoginFailed(Exception):
    pass


class RequestFailed(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class FakeSDK:
    LoginFailedException = LoginFailed
    RequestFailedException = RequestFailed


class FakeClient:
    def __init__(self, result: object | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.loaded_session: str | None = None

    def load_session(self, path: str) -> None:
        self.loaded_session = path

    async def fetch(self) -> object:
        if self.error is not None:
            raise self.error
        return self.result

    async def get_subscription_details(self) -> object:
        if self.error is not None:
            raise self.error
        return self.result


class AuthenticatedOperationTests(unittest.TestCase):
    def make_args(self, session_file: Path) -> SimpleNamespace:
        return SimpleNamespace(
            session_file=str(session_file),
            auth_file=str(session_file.with_name("auth.json")),
            timeout=20,
            token=None,
        )

    def test_falls_back_to_saved_session_when_token_login_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = Path(tempdir) / "session.pickle"
            session_file.write_text("saved")
            args = self.make_args(session_file)
            token_client = FakeClient(error=LoginFailed("expired token"))
            session_client = FakeClient(result={"source": "session"})

            def create_client(*, session_file: Path, timeout: int, token: str | None = None):
                if token:
                    return FakeSDK(), token_client
                return FakeSDK(), session_client

            with (
                mock.patch.object(cli, "active_token_from_args", return_value="stale-token"),
                mock.patch.object(cli, "create_client", side_effect=create_client),
            ):
                result = asyncio.run(
                    cli.run_authenticated_operation(args, lambda client: client.fetch())
                )

            self.assertEqual(result, {"source": "session"})
            self.assertEqual(session_client.loaded_session, str(session_file))

    def test_falls_back_to_saved_session_when_token_request_is_unauthorized(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = Path(tempdir) / "session.pickle"
            session_file.write_text("saved")
            args = self.make_args(session_file)
            token_client = FakeClient(error=RequestFailed("401 unauthorized", status_code=401))
            session_client = FakeClient(result={"source": "session"})

            def create_client(*, session_file: Path, timeout: int, token: str | None = None):
                if token:
                    return FakeSDK(), token_client
                return FakeSDK(), session_client

            with (
                mock.patch.object(cli, "active_token_from_args", return_value="stale-token"),
                mock.patch.object(cli, "create_client", side_effect=create_client),
            ):
                result = asyncio.run(
                    cli.run_authenticated_operation(args, lambda client: client.fetch())
                )

            self.assertEqual(result, {"source": "session"})

    def test_does_not_hide_non_auth_request_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            session_file = Path(tempdir) / "session.pickle"
            session_file.write_text("saved")
            args = self.make_args(session_file)
            token_client = FakeClient(error=RequestFailed("upstream timeout", status_code=500))
            session_client = FakeClient(result={"source": "session"})

            def create_client(*, session_file: Path, timeout: int, token: str | None = None):
                if token:
                    return FakeSDK(), token_client
                return FakeSDK(), session_client

            with (
                mock.patch.object(cli, "active_token_from_args", return_value="stale-token"),
                mock.patch.object(cli, "create_client", side_effect=create_client),
            ):
                with self.assertRaises(CLIError) as exc_info:
                    asyncio.run(
                        cli.run_authenticated_operation(args, lambda client: client.fetch())
                    )

            self.assertEqual(str(exc_info.exception), "upstream timeout")


class ParserTests(unittest.TestCase):
    def test_build_parser_supports_new_read_commands(self) -> None:
        parser = cli.build_parser()

        cases = [
            (["accounts", "history", "123"], cli.handle_account_history),
            (["transactions", "summary"], cli.handle_transactions_summary),
            (["transactions", "categories"], cli.handle_transaction_categories),
            (["transactions", "tags"], cli.handle_transaction_tags),
            (["institutions", "list"], cli.handle_institutions_list),
        ]

        for argv, handler in cases:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertIs(args.handler, handler)

    def test_login_web_defaults_to_system_browser(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["auth", "login-web"])
        self.assertEqual(args.browser, "system")

    def test_accounts_history_defaults_to_90_day_window(self) -> None:
        parser = cli.build_parser()
        args = parser.parse_args(["accounts", "history", "123"])
        self.assertFalse(args.all_history)
        self.assertIsNone(args.days)
        self.assertFalse(args.summary)


class HistoryWindowTests(unittest.TestCase):
    def make_snapshot(self, day: str, balance: float) -> dict[str, object]:
        return {"date": day, "signedBalance": balance, "accountName": "Checking"}

    def test_filter_account_history_defaults_to_last_90_days(self) -> None:
        snapshots = [
            self.make_snapshot("2025-12-31", 90),
            self.make_snapshot("2026-01-01", 100),
            self.make_snapshot("2026-01-31", 110),
            self.make_snapshot("2026-02-15", 120),
            self.make_snapshot("2026-03-01", 130),
            self.make_snapshot("2026-03-31", 140),
        ]
        filtered = cli.filter_account_history_snapshots(
            snapshots,
            start_date=None,
            end_date=None,
            days=None,
            include_all=False,
            limit=None,
        )
        self.assertEqual(
            [item["date"] for item in filtered],
            ["2026-01-01", "2026-01-31", "2026-02-15", "2026-03-01", "2026-03-31"],
        )

    def test_filter_account_history_respects_days_and_limit(self) -> None:
        snapshots = [
            self.make_snapshot("2026-03-25", 100),
            self.make_snapshot("2026-03-26", 110),
            self.make_snapshot("2026-03-27", 120),
            self.make_snapshot("2026-03-28", 130),
            self.make_snapshot("2026-03-29", 140),
            self.make_snapshot("2026-03-30", 150),
            self.make_snapshot("2026-03-31", 160),
        ]
        filtered = cli.filter_account_history_snapshots(
            snapshots,
            start_date=None,
            end_date=None,
            days=3,
            include_all=False,
            limit=2,
        )
        self.assertEqual([item["date"] for item in filtered], ["2026-03-30", "2026-03-31"])

    def test_build_account_history_summary_uses_absolute_start_for_pct(self) -> None:
        summary = cli.build_account_history_summary(
            [
                self.make_snapshot("2026-03-01", -100),
                self.make_snapshot("2026-03-31", -50),
            ]
        )
        self.assertEqual(summary["change"], 50.0)
        self.assertEqual(summary["change_pct"], 0.5)

    def test_validate_history_args_rejects_conflicting_flags(self) -> None:
        args = SimpleNamespace(
            all_history=True,
            days=30,
            start_date=None,
            end_date=None,
            limit=None,
        )
        with self.assertRaises(ValueError):
            cli.validate_history_args(args)


class LoginWebTests(unittest.TestCase):
    def test_handle_auth_login_web_uses_system_browser_flow(self) -> None:
        args = SimpleNamespace(
            browser="system",
            browser_profile="openclaw",
            timeout_seconds=300,
            timeout=20,
            session_file="/tmp/session.pickle",
            auth_file="/tmp/auth.json",
            as_json=False,
        )
        client = FakeClient(
            result={
                "subscription": {
                    "hasPremiumEntitlement": True,
                    "isOnFreeTrial": False,
                }
            }
        )

        with (
            mock.patch.object(cli, "open_system_browser") as open_browser,
            mock.patch.object(cli, "prompt_system_browser_token", return_value="copied-token"),
            mock.patch.object(cli, "create_client", return_value=(FakeSDK(), client)),
            mock.patch.object(cli, "save_token_auth", return_value=Path("/tmp/auth.json")) as save_auth,
            mock.patch.object(cli, "print_key_values") as print_key_values,
        ):
            exit_code = asyncio.run(cli.handle_auth_login_web(args))

        self.assertEqual(exit_code, 0)
        open_browser.assert_called_once_with(cli.LOGIN_URL)
        save_auth.assert_called_once()
        self.assertEqual(save_auth.call_args.kwargs["source"], "login-web-system")
        print_key_values.assert_called_once()


class HandlerRenderingTests(unittest.TestCase):
    def capture_handler(self, handler, args: SimpleNamespace, response: object) -> str:
        buffer = io.StringIO()
        with (
            mock.patch.object(cli, "run_authenticated_operation", mock.AsyncMock(return_value=response)),
            contextlib.redirect_stdout(buffer),
        ):
            exit_code = asyncio.run(handler(args))
        self.assertEqual(exit_code, 0)
        return buffer.getvalue()

    def test_handle_account_history_prints_balance_rows(self) -> None:
        output = self.capture_handler(
            cli.handle_account_history,
            SimpleNamespace(
                account_id="101",
                as_json=False,
                start_date=None,
                end_date=None,
                days=None,
                limit=None,
                summary=False,
                all_history=False,
            ),
            [
                {"date": "2026-04-01", "signedBalance": 0, "accountName": "Checking"},
                {"date": "2026-04-02", "signedBalance": 1180, "accountName": "Checking"},
            ],
        )
        self.assertIn("2026-04-01", output)
        self.assertIn("0.00", output)
        self.assertIn("1,180.00", output)
        self.assertIn("Checking", output)

    def test_handle_account_history_summary_prints_compact_metrics(self) -> None:
        output = self.capture_handler(
            cli.handle_account_history,
            SimpleNamespace(
                account_id="101",
                as_json=False,
                start_date=None,
                end_date=None,
                days=None,
                limit=None,
                summary=True,
                all_history=False,
            ),
            [
                {"date": "2026-03-01", "signedBalance": 1000, "accountName": "Checking"},
                {"date": "2026-03-31", "signedBalance": 1250, "accountName": "Checking"},
            ],
        )
        self.assertIn("starting_balance", output)
        self.assertIn("1,000.00", output)
        self.assertIn("250.00", output)
        self.assertIn("25.00%", output)

    def test_handle_transactions_summary_prints_key_metrics(self) -> None:
        output = self.capture_handler(
            cli.handle_transactions_summary,
            SimpleNamespace(as_json=False),
            {
                "aggregates": [
                    {
                        "summary": {
                            "count": 42,
                            "avg": 12.5,
                            "sum": 100.0,
                            "sumIncome": 2500.0,
                            "sumExpense": 2400.0,
                            "max": 500.0,
                            "maxExpense": 275.0,
                            "first": "2026-03-01",
                            "last": "2026-03-31",
                        }
                    }
                ]
            },
        )
        self.assertIn("count", output)
        self.assertIn("42", output)
        self.assertIn("2,500.00", output)
        self.assertIn("2026-03-31", output)

    def test_handle_transaction_categories_prints_group_metadata(self) -> None:
        output = self.capture_handler(
            cli.handle_transaction_categories,
            SimpleNamespace(as_json=False),
            {
                "categories": [
                    {
                        "id": "cat-1",
                        "name": "Groceries",
                        "group": {"name": "Food", "type": "expense"},
                        "isDisabled": False,
                        "isSystemCategory": True,
                    }
                ]
            },
        )
        self.assertIn("Groceries", output)
        self.assertIn("Food", output)
        self.assertIn("expense", output)

    def test_handle_transaction_tags_prints_counts(self) -> None:
        output = self.capture_handler(
            cli.handle_transaction_tags,
            SimpleNamespace(as_json=False),
            {
                "householdTransactionTags": [
                    {"id": "tag-1", "name": "Vacation", "color": "#00AAFF", "transactionCount": 7}
                ]
            },
        )
        self.assertIn("Vacation", output)
        self.assertIn("#00AAFF", output)
        self.assertIn("7", output)

    def test_handle_institutions_list_counts_accounts_by_credential(self) -> None:
        output = self.capture_handler(
            cli.handle_institutions_list,
            SimpleNamespace(as_json=False),
            {
                "credentials": [
                    {
                        "id": "cred-1",
                        "institution": {"name": "Chase"},
                        "dataProvider": "PLAID",
                        "displayLastUpdatedAt": "2026-04-05",
                        "updateRequired": False,
                        "disconnectedFromDataProviderAt": None,
                    }
                ],
                "accounts": [
                    {"credential": {"id": "cred-1"}},
                    {"credential": {"id": "cred-1"}},
                ],
            },
        )
        self.assertIn("Chase", output)
        self.assertIn("PLAID", output)
        self.assertIn("2", output)

    def test_handle_balances_recent_joins_account_names(self) -> None:
        buffer = io.StringIO()
        args = SimpleNamespace(as_json=False, start_date=None, account_id=[])
        responses = [
            {
                "accounts": [
                    {"id": "acct-1", "recentBalances": [10, 0]},
                    {"id": "acct-2", "recentBalances": [25]},
                ]
            },
            {
                "accounts": [
                    {"id": "acct-1", "displayName": "Checking"},
                    {"id": "acct-2", "displayName": "Savings"},
                ]
            },
        ]
        with (
            mock.patch.object(cli, "run_authenticated_operation", mock.AsyncMock(side_effect=responses)),
            contextlib.redirect_stdout(buffer),
        ):
            exit_code = asyncio.run(cli.handle_balances_recent(args))

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertIn("Checking", output)
        self.assertIn("Savings", output)
        self.assertIn("0.00", output)
        self.assertIn("-10.00", output)

    def test_handle_balances_recent_filters_account_ids(self) -> None:
        buffer = io.StringIO()
        args = SimpleNamespace(as_json=False, start_date=None, account_id=["acct-2"])
        responses = [
            {
                "accounts": [
                    {"id": "acct-1", "recentBalances": [10, 15]},
                    {"id": "acct-2", "recentBalances": [25, 30]},
                ]
            },
            {
                "accounts": [
                    {"id": "acct-1", "displayName": "Checking"},
                    {"id": "acct-2", "displayName": "Savings"},
                ]
            },
        ]
        with (
            mock.patch.object(cli, "run_authenticated_operation", mock.AsyncMock(side_effect=responses)),
            contextlib.redirect_stdout(buffer),
        ):
            exit_code = asyncio.run(cli.handle_balances_recent(args))

        self.assertEqual(exit_code, 0)
        output = buffer.getvalue()
        self.assertNotIn("Checking", output)
        self.assertIn("Savings", output)


if __name__ == "__main__":
    unittest.main()
