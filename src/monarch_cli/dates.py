from __future__ import annotations

import calendar
from datetime import date, datetime


def month_bounds(month: str) -> tuple[str, str]:
    try:
        parsed = datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise ValueError("Month must use YYYY-MM format.") from exc

    first_day = date(parsed.year, parsed.month, 1)
    last_day = date(
        parsed.year,
        parsed.month,
        calendar.monthrange(parsed.year, parsed.month)[1],
    )
    return first_day.isoformat(), last_day.isoformat()


def current_month_bounds(today: date | None = None) -> tuple[str, str]:
    if today is None:
        today = date.today()

    first_day = date(today.year, today.month, 1)
    last_day = date(
        today.year,
        today.month,
        calendar.monthrange(today.year, today.month)[1],
    )
    return first_day.isoformat(), last_day.isoformat()


def validate_date_pair(start_date: str | None, end_date: str | None) -> None:
    if bool(start_date) != bool(end_date):
        raise ValueError("You must provide both --start-date and --end-date.")

