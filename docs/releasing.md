# Releasing

Use this repo-local flow to cut a release without guessing.

## Prerequisites

- Use the project venv at `./.venv`.
- Install the package in editable mode.
- Install `build` into the same environment:

```bash
./.venv/bin/python -m pip install -e .
./.venv/bin/python -m pip install build
```

## Release Check

Run the scripted check first:

```bash
./scripts/release_check.sh
```

That command:

- runs `python3 -m unittest discover -s tests -q`
- confirms the `build` module is available
- builds fresh `sdist` and wheel artifacts into `dist/`

## Version Bump

Update both version declarations together:

- `pyproject.toml`
- `src/monarch_cli/__init__.py`

The test suite includes a version-consistency check so these should not drift.

## Tagging

After the release check passes:

```bash
git status
git add pyproject.toml src/monarch_cli/__init__.py README.md docs/releasing.md scripts/release_check.sh tests
git commit -m "Release vX.Y.Z"
git tag vX.Y.Z
git push origin main --follow-tags
```

## Install Smoke Test

For a user-style install test from the repo root:

```bash
pipx install --force .
monarch --help
```

For a GitHub install path:

```bash
pipx install --force git+https://github.com/barronlroth/monarch-money-cli.git
monarch --help
```
