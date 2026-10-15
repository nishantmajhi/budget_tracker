"""Defects in what is shown: the original misbehaving, then the fix, in one run.

See `RegressionCase` in helpers.py for how each scenario is run twice.
"""

import unittest
from unittest import mock

from rich.errors import MarkupError

from helpers import HEADER, RegressionCase


class Regression(RegressionCase):

    def test_a_description_containing_a_closing_tag_does_not_crash_the_table(self):
        # Descriptions were passed to rich as markup, so "[/]" raised
        # MarkupError every time the transactions were viewed.
        def scenario(s):
            s.write_ledger(HEADER + "2026-03-01,Expense,Shopping,oops [/],10\r\n")
            return self.outcome(lambda: s.call("view_transactions")), s.output

        (orig, _), (cur, out) = self.both(scenario)
        self.assertIsInstance(orig, MarkupError)
        self.assertIsNone(cur)
        self.assertIn("oops [/]", out)

    def test_square_brackets_in_a_description_are_shown(self):
        # ...and "[refund]" was taken for a style tag and silently removed.
        def scenario(s):
            s.write_ledger(HEADER + "2026-03-01,Expense,Shopping,Amazon [refund] item,10\r\n")
            s.call("view_transactions")
            return s.output

        orig, cur = self.both(scenario)
        self.assertNotIn("[refund]", orig)
        self.assertIn("Amazon [refund] item", cur)

    def test_a_category_in_square_brackets_is_shown_in_the_breakdown(self):
        def scenario(s):
            s.write_ledger(HEADER + "2026-03-01,Expense,[misc],,10\r\n")
            with mock.patch.object(s.m.plt, "show"):
                s.call("category_breakdown")
            return s.output

        orig, cur = self.both(scenario)
        self.assertNotIn("[misc]", orig)
        self.assertIn("[misc]", cur)

    def test_a_bad_value_is_quoted_in_the_skip_message_without_crashing(self):
        # The skip message quotes the value it rejected, and the original
        # printed it as markup: an amount of "[/]" crashed the import.
        def scenario(s):
            src = s.write("in.csv", HEADER + "2026-03-01,Expense,Food,,[/]\r\n"
                                             "2026-03-02,Expense,Food,,1\r\n")
            return self.outcome(lambda: s.call("import_csv", answers=[src])), s.output

        (orig, _), (cur, out) = self.both(scenario)
        self.assertIsInstance(orig, MarkupError)
        self.assertIsNone(cur)
        self.assertIn("Row 2 skipped: invalid amount '[/]'.", out)
        self.assertIn("1 row(s) added", out)

    def test_a_path_with_square_brackets_is_shown_as_typed(self):
        # Typed as given, not built with Path: on Windows that would put a
        # backslash before the bracket, which rich reads as an escape.
        def scenario(s):
            missing = "[old] exports/[/]no-such-file.csv"
            return self.outcome(lambda: s.call("import_csv", answers=[missing])), s.output

        (orig, o_out), (cur, out) = self.both(scenario)
        self.assertIsNone(orig)
        self.assertIn("File not found:  exports/no-such-file.csv", o_out,
                      "the original took both bracketed parts for markup")
        self.assertIsNone(cur)
        self.assertIn("File not found: [old] exports/[/]no-such-file.csv", out)

    def test_a_superscript_digit_at_a_number_prompt_asks_again(self):
        # "²".isdigit() is True but int("²") raises, so the original crashed.
        def scenario(s):
            return self.outcome(lambda: s.call("pick_from_list", ["a", "b"], "Pick",
                                               answers=["²", "2"]))

        orig, cur = self.both(scenario)
        self.assertIsInstance(orig, ValueError)
        self.assertEqual(cur, "b")


if __name__ == "__main__":
    unittest.main()
