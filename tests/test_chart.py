"""The two charts, rendered by the real plotext and read back cell by cell."""

import unittest

import plotext

import chart
from helpers import HEADER, LedgerCase, RegressionCase

TWO_MONTHS = (HEADER
              + "2026-01-01,Income,Salary,,100\r\n"
              + "2026-01-02,Expense,Rent,,250\r\n"
              + "2026-02-01,Income,Salary,,300\r\n"
              + "2026-02-02,Expense,Rent,,50\r\n")


class Regression(RegressionCase):

    def test_the_income_bar_is_not_hidden_behind_the_expense_bar(self):
        # The README and the code both call this a grouped bar chart, but the
        # original drew two bar series on the same x positions, so in any
        # month that spent more than it earned the income bar was entirely
        # behind the expense bar and the chart showed no income at all.
        def scenario(s):
            s.write_ledger(TWO_MONTHS)
            [drawn] = chart.capture(s, "show_chart")
            return chart.runs(chart.bottom_row(drawn))

        orig, cur = self.both(scenario)
        self.assertEqual(orig, "RR", "January and February both show only red at the base")
        self.assertEqual(cur, "GRGR")


class IncomeVsExpenses(LedgerCase):

    def test_each_month_has_its_income_and_its_expense_side_by_side(self):
        s = self.session()
        s.write_ledger(TWO_MONTHS)
        [drawn] = chart.capture(s, "show_chart")
        text = "\n".join(drawn)
        self.assertIn("Monthly Income vs Expenses", text)
        self.assertIn("2026-01", text)
        self.assertIn("2026-02", text)
        self.assertIn("Income", text)
        self.assertIn("Expenses", text)

    def test_the_taller_bar_in_each_month_is_the_larger_amount(self):
        # January spent 250 of 100 earned; February earned 300 and spent 50.
        # The top bar row of each month's pair must be the larger series.
        s = self.session()
        s.write_ledger(TWO_MONTHS)
        [drawn] = chart.capture(s, "show_chart")
        rows = [area for area in map(chart._plot_area, drawn) if area]
        body = [r for r in rows if "Income" not in r and "Expenses" not in r]
        half = len(body[-1]) // 2
        first_red = next(i for i, r in enumerate(body) if "R" in r[:half])
        first_green = next(i for i, r in enumerate(body) if "G" in r[:half])
        self.assertLess(first_red, first_green, "January: expense is the taller bar")
        first_red = next(i for i, r in enumerate(body) if "R" in r[half:])
        first_green = next(i for i, r in enumerate(body) if "G" in r[half:])
        self.assertLess(first_green, first_red, "February: income is the taller bar")


class SpendingByCategory(LedgerCase):

    def test_the_chart_lists_every_category(self):
        s = self.session()
        s.write_ledger(HEADER + "2026-01-01,Expense,Rent,,800\r\n"
                                "2026-01-02,Expense,Food,,50\r\n"
                                "2026-01-03,Income,Salary,,2000\r\n")
        [drawn] = chart.capture(s, "category_breakdown")
        text = "\n".join(drawn)
        self.assertIn("Spending by Category", text)
        self.assertIn("Rent", text)
        self.assertIn("Food", text)
        self.assertNotIn("Salary", text)


class InstalledPlotext(unittest.TestCase):

    def test_the_installed_plotext_has_the_api_the_charts_use(self):
        # plotext 6 removed all of these; requirements.txt pins below it.
        for name in ("clf", "theme", "bar", "multiple_bar", "title", "xlabel", "ylabel", "show"):
            with self.subTest(name=name):
                self.assertTrue(hasattr(plotext, name),
                                f"plotext has no {name}(); install from requirements.txt")


if __name__ == "__main__":
    unittest.main()
