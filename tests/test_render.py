import unittest

import _path

from monarch_cli.render import build_table, format_money, format_percent


class RenderTests(unittest.TestCase):
    def test_format_money(self) -> None:
        self.assertEqual(format_money(1234.5), "1,234.50")

    def test_format_percent(self) -> None:
        self.assertEqual(format_percent(0.25), "25.00%")

    def test_build_table(self) -> None:
        output = build_table(
            ["name", "value"],
            [["checking", "100.00"], ["savings", "200.00"]],
        )
        self.assertIn("checking", output)
        self.assertIn("savings", output)
        self.assertIn("name", output)


if __name__ == "__main__":
    unittest.main()
