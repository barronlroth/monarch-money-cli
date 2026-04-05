# Monarch Money CLI Bootstrap Plan

Date: 2026-04-05
Plan: 01
Status: In progress

## Goal

Build a pragmatic CLI around the existing `hammem/monarchmoney` Python client so the first version is immediately useful for personal use, scriptable, and small enough to maintain.

## Product Decisions

- V1 is read-heavy, not write-heavy.
- The tool is optimized for personal use first, not public release polish.
- Commands print human-readable tables by default and support `--json` for scripting.
- Auth starts with interactive login and saved session reuse.
- Packaging targets local installation first, with a clean path to `pipx` later.
- Command name is `monarch`.

## Scope

### V1 Commands

- `monarch auth login`
- `monarch auth logout`
- `monarch auth status`
- `monarch accounts list`
- `monarch transactions list`
- `monarch transactions show`
- `monarch budgets list`
- `monarch cashflow summary`
- `monarch refresh accounts`

### Deferred

- Transaction mutation commands
- Budget mutation commands
- CSV import/export helpers
- Rich filtering aliases and shell completions
- Public-release packaging polish

## Architecture

### CLI Layer

- Use `Typer` for command groups and help text.
- Keep commands thin and route all API interaction through shared helpers.
- Support a consistent `--json` output mode.

### Client Layer

- Wrap the upstream async `MonarchMoney` client in a small session/bootstrap helper.
- Reuse upstream session save/load support instead of inventing a second auth system.
- Keep upstream-specific response parsing isolated from command definitions.

### Local State

- Store CLI config and session data under a dedicated app directory.
- Keep secrets and saved session material out of the repo and out of stdout.
- Add a `.gitignore` immediately to avoid accidental credential commits.

### Rendering

- Start with JSON output and lightweight table rendering for the main list commands.
- Favor stable column choices over dumping every raw field by default.

## Milestones

### Milestone 1 - Project Scaffold

- Create package structure, entrypoint, and dependency metadata.
- Add base config/session path handling.
- Add shared async runner utilities.

### Milestone 2 - Auth Flow

- Implement `auth login`, `auth logout`, and `auth status`.
- Verify saved session reuse is the default path after first login.
- Keep the UX minimal and explicit around MFA/session reuse.

### Milestone 3 - Read Commands

- Implement accounts, transactions, budgets, cashflow, and refresh commands.
- Add common output handling for table and JSON modes.
- Normalize the most useful fields for terminal output.

### Milestone 4 - Tests and Hardening

- Add unit tests around command parsing and wrapper behavior.
- Mock the upstream client instead of relying on live network calls.
- Tighten error messages for auth failures and expired sessions.

## Risks

- Upstream API changes can break the CLI unexpectedly.
- Session and MFA flows are the most likely source of friction.
- Response payloads are large and inconsistent, so output shaping needs discipline.
- The local GitHub auth state may block pushing commits until re-authenticated.

## Validation

- Basic smoke test of command help and import paths.
- Unit tests for auth/session path resolution and output formatting.
- Mocked command tests for each V1 command group.

## Immediate Next Steps

1. Scaffold the Python package and CLI entrypoint.
2. Implement config/session path handling and auth commands.
3. Add the first read-only commands with JSON output first.
