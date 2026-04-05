from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


APP_DIRNAME = "monarch-cli"
SESSION_FILENAME = "session.pickle"
AUTH_FILENAME = "auth.json"


def default_config_dir(home: Path | None = None) -> Path:
    override = os.environ.get("MONARCH_CONFIG_DIR")
    if override:
        return Path(override).expanduser()

    if home is None:
        home = Path.home()

    return home / ".config" / APP_DIRNAME


def default_session_file(home: Path | None = None) -> Path:
    override = os.environ.get("MONARCH_SESSION_FILE")
    if override:
        return Path(override).expanduser()

    return default_config_dir(home=home) / SESSION_FILENAME


def default_auth_file(home: Path | None = None) -> Path:
    override = os.environ.get("MONARCH_AUTH_FILE")
    if override:
        return Path(override).expanduser()

    return default_config_dir(home=home) / AUTH_FILENAME


def ensure_parent_dir(path: Path) -> Path:
    expanded = path.expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    return expanded


def set_private_permissions(path: Path) -> Path:
    expanded = path.expanduser()
    try:
        expanded.chmod(0o600)
    except FileNotFoundError:
        pass
    return expanded


def utcnow_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def load_auth_payload(path: Path) -> dict[str, Any] | None:
    expanded = path.expanduser()
    if not expanded.exists():
        return None

    return json.loads(expanded.read_text())


def load_auth_token(path: Path) -> str | None:
    payload = load_auth_payload(path)
    if not payload:
        return None

    token = payload.get("token")
    return token if isinstance(token, str) and token else None


def save_auth_payload(path: Path, payload: dict[str, Any]) -> Path:
    expanded = ensure_parent_dir(path)
    expanded.write_text(json.dumps(payload, indent=2) + "\n")
    return set_private_permissions(expanded)

