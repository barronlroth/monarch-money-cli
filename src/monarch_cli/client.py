from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


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
    except ImportError as exc:
        raise CLIError(
            "The `monarchmoneycommunity` package is not installed. Run `pip install -e .` first."
        ) from exc

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
            f"No saved session found at `{session_file}`. Run `monarch auth login`, `monarch auth login-web`, or `monarch auth import-token` first."
        )

    client.load_session(str(session_file))
