from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gql import GraphQLRequest


class CLIError(RuntimeError):
    """User-facing CLI error."""


@dataclass(frozen=True)
class MonarchSDK:
    MonarchMoney: Any
    LoginFailedException: type[BaseException]
    RequireMFAException: type[BaseException]
    RequestFailedException: type[BaseException]


def load_sdk() -> MonarchSDK:
    try:
        from monarchmoney import (
            LoginFailedException,
            MonarchMoney,
            RequestFailedException,
            RequireMFAException,
        )
        from monarchmoney.monarchmoney import MonarchMoneyEndpoints
    except ImportError as exc:
        raise CLIError(
            "The `monarchmoney` package is not installed. Run `pip install -e .` first."
        ) from exc

    MonarchMoneyEndpoints.BASE_URL = "https://api.monarch.com"

    async def gql_call_v4(self: Any, operation: str, graphql_query: Any, variables: dict[str, Any] = {}) -> dict[str, Any]:
        request = GraphQLRequest(
            graphql_query,
            operation_name=operation,
            variable_values=variables,
        )
        return await self._get_graphql_client().execute_async(request)

    MonarchMoney.gql_call = gql_call_v4

    return MonarchSDK(
        MonarchMoney=MonarchMoney,
        LoginFailedException=LoginFailedException,
        RequireMFAException=RequireMFAException,
        RequestFailedException=RequestFailedException,
    )


def create_client(
    session_file: Path,
    timeout: int,
    token: str | None = None,
) -> tuple[MonarchSDK, Any]:
    sdk = load_sdk()
    client = sdk.MonarchMoney(
        session_file=str(session_file),
        timeout=timeout,
        token=token,
    )
    return sdk, client


def require_saved_session(client: Any, session_file: Path) -> None:
    if not session_file.exists():
        raise CLIError(
            f"No saved session found at `{session_file}`. Run `monarch auth login` first."
        )

    client.load_session(str(session_file))

