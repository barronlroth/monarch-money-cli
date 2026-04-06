import unittest
from datetime import date

import _path

from monarch_cli.dates import current_month_bounds, month_bounds, validate_date_pair


class DateTests(unittest.TestCase):
    def test_month_bounds(self) -> None:
        self.assertEqual(month_bounds("2026-02"), ("2026-02-01", "2026-02-28"))

    def test_month_bounds_rejects_bad_format(self) -> None:
        with self.assertRaises(ValueError):
            month_bounds("02/2026")

    def test_current_month_bounds(self) -> None:
        self.assertEqual(
            current_month_bounds(today=date(2026, 4, 5)),
            ("2026-04-01", "2026-04-30"),
        )

    def test_validate_date_pair_requires_both(self) -> None:
        with self.assertRaises(ValueError):
            validate_date_pair("2026-04-01", None)


if __name__ == "__main__":
    unittest.main()
