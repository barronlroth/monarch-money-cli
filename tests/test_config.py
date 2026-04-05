import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from monarch_cli.config import (
    default_auth_file,
    default_config_dir,
    default_session_file,
    ensure_parent_dir,
    load_auth_token,
    save_auth_payload,
)


class ConfigTests(unittest.TestCase):
    def test_default_config_dir_uses_home(self) -> None:
        home = Path("/tmp/example-home")
        self.assertEqual(
            default_config_dir(home=home),
            home / ".config" / "monarch-cli",
        )

    def test_default_session_file_respects_env_override(self) -> None:
        with mock.patch.dict(os.environ, {"MONARCH_SESSION_FILE": "~/custom/session.pickle"}):
            self.assertEqual(
                default_session_file(),
                Path("~/custom/session.pickle").expanduser(),
            )

    def test_default_auth_file_respects_env_override(self) -> None:
        with mock.patch.dict(os.environ, {"MONARCH_AUTH_FILE": "~/custom/auth.json"}):
            self.assertEqual(
                default_auth_file(),
                Path("~/custom/auth.json").expanduser(),
            )

    def test_ensure_parent_dir_creates_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            target = Path(tempdir) / "nested" / "session.pickle"
            returned = ensure_parent_dir(target)
            self.assertEqual(returned, target)
            self.assertTrue(target.parent.exists())

    def test_save_auth_payload_round_trips_token(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            target = Path(tempdir) / "auth.json"
            save_auth_payload(target, {"token": "abc123", "source": "test"})
            self.assertEqual(load_auth_token(target), "abc123")


if __name__ == "__main__":
    unittest.main()

