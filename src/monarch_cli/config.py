from __future__ import annotations

import os
from pathlib import Path


APP_DIRNAME = "monarch-cli"
SESSION_FILENAME = "session.pickle"


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


def ensure_parent_dir(path: Path) -> Path:
    expanded = path.expanduser()
    expanded.parent.mkdir(parents=True, exist_ok=True)
    return expanded

