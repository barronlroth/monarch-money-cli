import tomllib
import unittest
from pathlib import Path

import _path

from monarch_cli import __version__


class PackageTests(unittest.TestCase):
    def test_dunder_version_matches_pyproject(self) -> None:
        pyproject = tomllib.loads(Path("pyproject.toml").read_text())
        self.assertEqual(__version__, pyproject["project"]["version"])


if __name__ == "__main__":
    unittest.main()
