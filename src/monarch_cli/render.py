from __future__ import annotations

import json
import sys
from typing import Iterable, Sequence


def emit_json(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=True, default=str))


def format_money(value: object) -> str:
    if value is None or value == "":
        return ""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    return f"{number:,.2f}"


def format_percent(value: object) -> str:
    if value is None or value == "":
        return ""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)

    if abs(number) <= 1:
        number *= 100

    return f"{number:,.2f}%"


def stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def build_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    rendered_rows = [[stringify(cell) for cell in row] for row in rows]
    if not rendered_rows:
        return "No results."

    widths = [len(header) for header in headers]
    for row in rendered_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def render_row(row: Sequence[str]) -> str:
        return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row))

    lines = [
        render_row(headers),
        render_row(["-" * width for width in widths]),
    ]
    lines.extend(render_row(row) for row in rendered_rows)
    return "\n".join(lines)


def print_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    print(build_table(headers, rows))


def print_key_values(mapping: dict[str, object]) -> None:
    width = max((len(key) for key in mapping), default=0)
    for key, value in mapping.items():
        print(f"{key.ljust(width)}  {stringify(value)}", file=sys.stdout)

