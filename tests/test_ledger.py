"""The decisions: parsing, validating, totalling, and the data file itself."""

import os
import unittest
from decimal import Decimal

import budget_tracker as bt

from helpers import HEADER, LedgerCase

D = Decimal


def record(date="2026-03-01", t_type="Expense", category="Food", description="", amount="1.00"):
    """A transaction as the tracker holds one: amounts are always to the penny."""
    return {"date": date, "type": t_type, "category": category,
            "description": description, "amount": D(amount).quantize(D("0.01"))}


class ParseAmount(unittest.TestCase):

    def test_a_plain_number_is_rounded_to_the_penny(self):
        self.assertEqual(bt.parse_amount("12.5"), D("12.50"))
        self.assertEqual(bt.parse_amount("12"), D("12.00"))
        self.assertEqual(bt.parse_amount(" 7.25 "), D("7.25"))
        self.assertEqual(bt.parse_amount("1e3"), D("1000.00"))

    def test_halves_round_up_as_money_does(self):
        # round(2.675, 2) is 2.67 in floats, because 2.675 is stored as
        # 2.67499999...; the Decimal version sees the digits that were typed.
        self.assertEqual(bt.parse_amount("2.675"), D("2.68"))
        self.assertEqual(bt.parse_amount("0.005"), D("0.01"))

    def test_the_result_is_exact_to_two_places(self):
        self.assertEqual(bt.parse_amount("0.1").as_tuple().exponent, -2)

    def test_zero_negative_and_amounts_that_round_to_zero_are_refused(self):
        for text in ("0", "0.00", "-5", "-0.01", "0.004"):
            with self.subTest(text=text):
                self.assertIsNone(bt.parse_amount(text))

    def test_non_numbers_are_refused(self):
        for text in ("", "   ", None, "abc", "1,000", "£5", "5 GBP", "1.2.3"):
            with self.subTest(text=text):
                self.assertIsNone(bt.parse_amount(text))

    def test_nan_and_infinity_in_any_spelling_are_refused(self):
        for text in ("nan", "NaN", "-nan", "sNaN", "inf", "-inf", "Infinity", "INF"):
            with self.subTest(text=text):
                self.assertIsNone(bt.parse_amount(text))

    def test_an_amount_too_large_to_hold_to_the_penny_is_refused(self):
        self.assertIsNone(bt.parse_amount("1e40"))


class ParseDate(unittest.TestCase):

    def test_a_padded_date_is_returned_as_it_is(self):
        self.assertEqual(bt.parse_date("2026-02-05"), "2026-02-05")

    def test_an_unpadded_date_is_padded(self):
        self.assertEqual(bt.parse_date("2026-2-5"), "2026-02-05")
        self.assertEqual(bt.parse_date("2026-12-1"), "2026-12-01")

    def test_surrounding_space_is_ignored(self):
        self.assertEqual(bt.parse_date(" 2026-02-05 "), "2026-02-05")

    def test_dates_that_do_not_exist_are_refused(self):
        for text in ("2026-02-30", "2026-02-29", "2026-13-01", "2026-00-10"):
            with self.subTest(text=text):
                self.assertIsNone(bt.parse_date(text))

    def test_a_leap_day_is_accepted(self):
        self.assertEqual(bt.parse_date("2024-02-29"), "2024-02-29")

    def test_other_formats_are_refused(self):
        for text in ("2026/02/05", "05-02-2026", "05/02/2026", "next tuesday", "", None,
                     "2026-02-05T10:00", "20260205"):
            with self.subTest(text=text):
                self.assertIsNone(bt.parse_date(text))


class ParseType(unittest.TestCase):

    def test_either_type_in_any_case_is_normalised(self):
        for text, expected in (("Income", "Income"), ("income", "Income"), ("INCOME", "Income"),
                               (" Expense ", "Expense"), ("expense", "Expense")):
            with self.subTest(text=text):
                self.assertEqual(bt.parse_type(text), expected)

    def test_anything_else_is_refused(self):
        for text in ("Refund", "Expenses", "In come", "", None):
            with self.subTest(text=text):
                self.assertIsNone(bt.parse_type(text))


class ParseTransaction(unittest.TestCase):

    def row(self, **fields):
        base = {"date": "2026-03-01", "type": "Expense", "category": "Food",
                "description": "Lunch", "amount": "4.5"}
        base.update(fields)
        return base

    def test_a_good_row_becomes_a_clean_record(self):
        rec, reason = bt.parse_transaction(self.row(category=" Food ", description=" Lunch "))
        self.assertIsNone(reason)
        self.assertEqual(rec, record(description="Lunch", amount="4.50"))

    def test_each_required_field_must_be_present_and_not_blank(self):
        for field in ("date", "type", "category"):
            for value in ("", "  ", None):
                with self.subTest(field=field, value=value):
                    rec, reason = bt.parse_transaction(self.row(**{field: value}))
                    self.assertIsNone(rec)
                    self.assertEqual(reason, "missing date, type, or category.")

    def test_the_description_is_optional(self):
        for value in ("", None):
            with self.subTest(value=value):
                rec, _ = bt.parse_transaction(self.row(description=value))
                self.assertEqual(rec["description"], "")

    def test_each_bad_value_is_named_in_the_reason(self):
        cases = {
            "date": ("2026/03/01", "invalid date '2026/03/01'."),
            "type": ("Refund", "invalid type 'Refund'."),
            "amount": ("abc", "invalid amount 'abc'."),
        }
        for field, (value, expected) in cases.items():
            with self.subTest(field=field):
                self.assertEqual(bt.parse_transaction(self.row(**{field: value})), (None, expected))

    def test_a_short_row_with_no_amount_is_refused_not_a_crash(self):
        # csv.DictReader fills missing trailing fields with None.
        self.assertEqual(bt.parse_transaction(self.row(amount=None)),
                         (None, "invalid amount ''."))


class Totals(unittest.TestCase):

    def test_the_balance_is_income_less_expenses_and_exact(self):
        txns = [record(t_type="Income", amount="0.30"),
                record(amount="0.10"), record(amount="0.20")]
        self.assertEqual(bt.get_running_balance(txns), D("0.00"))
        self.assertFalse(bt.get_running_balance(txns) < 0)

    def test_the_balance_of_nothing_is_zero(self):
        self.assertEqual(bt.get_running_balance([]), D("0.00"))

    def test_a_long_run_of_small_amounts_totals_exactly(self):
        txns = [record(t_type="Income", amount="0.10")] * 10_000
        self.assertEqual(bt.get_running_balance(txns), D("1000.00"))

    def test_monthly_totals_are_grouped_and_in_month_order(self):
        txns = [record(date="2026-03-05", t_type="Income", amount="100"),
                record(date="2026-01-10", amount="20"),
                record(date="2026-03-20", amount="30.50"),
                record(date="2025-12-31", t_type="Income", amount="5")]
        self.assertEqual(bt.monthly_totals(txns), {
            "2025-12": {"income": D("5.00"), "expense": D("0.00")},
            "2026-01": {"income": D("0.00"), "expense": D("20.00")},
            "2026-03": {"income": D("100.00"), "expense": D("30.50")},
        })
        self.assertEqual(list(bt.monthly_totals(txns)), ["2025-12", "2026-01", "2026-03"])

    def test_category_totals_count_only_spending_highest_first(self):
        txns = [record(category="Food", amount="10"), record(category="Rent", amount="800"),
                record(category="Food", amount="15.25"),
                record(t_type="Income", category="Salary", amount="2000")]
        self.assertEqual(bt.category_totals(txns), [("Rent", D("800.00")), ("Food", D("25.25"))])

    def test_category_totals_of_income_only_is_empty(self):
        self.assertEqual(bt.category_totals([record(t_type="Income", category="Salary")]), [])


class ReadTransactions(LedgerCase):

    def test_good_rows_come_back_and_bad_rows_are_reported_by_line(self):
        s = self.session()
        path = s.write("in.csv", HEADER
                       + "2026-03-01,Income,Salary,,100\r\n"
                       + "2026-03-02,Expense,Food,,abc\r\n"
                       + "2026-03-03,Expense,,,5\r\n"
                       + "2026-03-04,Expense,Food,,5\r\n")
        records, problems = bt.read_transactions(path)
        self.assertEqual([r["date"] for r in records], ["2026-03-01", "2026-03-04"])
        self.assertEqual(problems, [
            "Row 3 skipped: invalid amount 'abc'.",
            "Row 4 skipped: missing date, type, or category.",
        ])

    def test_a_row_number_counts_lines_not_records(self):
        # A quoted description may span lines; the row number is the line a
        # person would look at in a text editor.
        s = self.session()
        path = s.write("in.csv", HEADER
                       + '2026-03-01,Expense,Food,"two\r\nlines",5\r\n'
                       + "2026-03-02,Expense,Food,,abc\r\n")
        records, problems = bt.read_transactions(path)
        self.assertEqual(records[0]["description"], "two\r\nlines")
        self.assertEqual(problems, ["Row 4 skipped: invalid amount 'abc'."])

    def test_columns_may_be_in_any_order_and_extra_columns_are_ignored(self):
        s = self.session()
        path = s.write("in.csv", "amount,notes,category,type,description,date\r\n"
                                 "12,ignored,Food,Expense,Lunch,2026-03-01\r\n")
        records, problems = bt.read_transactions(path)
        self.assertEqual(records, [record(description="Lunch", amount="12")])
        self.assertEqual(problems, [])

    def test_missing_columns_are_named_in_order(self):
        s = self.session()
        path = s.write("in.csv", "type,description\r\nIncome,x\r\n")
        with self.assertRaises(bt.LedgerError) as caught:
            bt.read_transactions(path)
        self.assertEqual(str(caught.exception),
                         "Missing columns in source file: amount, category, date")

    def test_a_file_with_no_header_at_all_is_missing_every_column(self):
        s = self.session()
        path = s.write("in.csv", "")
        with self.assertRaises(bt.LedgerError) as caught:
            bt.read_transactions(path)
        self.assertIn("amount, category, date, description, type", str(caught.exception))

    def test_a_byte_order_mark_is_not_part_of_the_first_column(self):
        s = self.session()
        path = s.write("in.csv", HEADER + "2026-03-01,Expense,Food,,1\r\n", encoding="utf-8-sig")
        self.assertEqual(len(bt.read_transactions(path)[0]), 1)

    def test_text_in_another_encoding_is_a_ledger_error(self):
        s = self.session()
        path = s.write("in.csv", HEADER + "2026-03-01,Expense,Food,£5,5\r\n", encoding="cp1252")
        with self.assertRaises(bt.LedgerError) as caught:
            bt.read_transactions(path)
        self.assertIn("CSV UTF-8", str(caught.exception))

    def test_non_ascii_text_in_utf8_is_kept(self):
        s = self.session()
        path = s.write("in.csv", HEADER + "2026-03-01,Expense,Food,£5 café काठ,5\r\n")
        self.assertEqual(bt.read_transactions(path)[0][0]["description"],
                         "£5 café काठ")

    def test_a_missing_file_is_an_os_error(self):
        with self.assertRaises(OSError):
            bt.read_transactions(os.path.join(self.tmp, "nope.csv"))


class TheDataFile(LedgerCase):

    def test_no_file_and_an_empty_file_are_both_an_empty_ledger(self):
        s = self.session()
        with s.active():
            self.assertEqual(bt.load_ledger(), ([], []))
            s.write_ledger("")
            self.assertEqual(bt.load_ledger(), ([], []))
            s.write_ledger(HEADER)
            self.assertEqual(bt.load_ledger(), ([], []))

    def test_the_first_save_creates_the_file_with_its_header(self):
        s = self.session()
        with s.active():
            bt.save_transaction(record(amount="12.5"))
        self.assertEqual(s.ledger_text(), HEADER + "2026-03-01,Expense,Food,,12.50\r\n")

    def test_a_saved_record_loads_back_equal(self):
        s = self.session()
        recs = [record(description='Says "hi", then leaves', amount="3.10"),
                record(date="2026-01-02", t_type="Income", category="Gift",
                       description="café, काठ", amount="1000")]
        with s.active():
            bt.save_transactions(recs)
            self.assertEqual(bt.load_transactions(), recs)

    def test_many_records_are_appended_in_order_after_what_is_there(self):
        s = self.session()
        s.write_ledger(HEADER + "2026-01-01,Income,Salary,,1.00\r\n")
        with s.active():
            bt.save_transactions([record(amount="2"), record(amount="3")])
            self.assertEqual([t["amount"] for t in bt.load_transactions()],
                             [D("1.00"), D("2.00"), D("3.00")])

    def test_saving_nothing_to_a_missing_file_creates_only_the_header(self):
        s = self.session()
        with s.active():
            bt.save_transactions([])
        self.assertEqual(s.ledger_text(), HEADER)

    def test_a_file_ending_in_a_bare_newline_gets_no_blank_line(self):
        s = self.session()
        s.write_ledger("date,type,category,description,amount\n2026-01-01,Income,Salary,,1\n")
        with s.active():
            bt.save_transaction(record())
        self.assertEqual(s.ledger_text(), "date,type,category,description,amount\n"
                                          "2026-01-01,Income,Salary,,1\n"
                                          "2026-03-01,Expense,Food,,1.00\r\n")

    def test_a_row_left_unfinished_by_an_editor_is_finished_first(self):
        s = self.session()
        s.write_ledger(HEADER + "2026-01-01,Income,Salary,,1")
        with s.active():
            bt.save_transaction(record())
        self.assertEqual(s.ledger_text(), HEADER + "2026-01-01,Income,Salary,,1\r\n"
                                                   "2026-03-01,Expense,Food,,1.00\r\n")

    def test_a_column_added_in_a_spreadsheet_is_kept_and_left_blank(self):
        s = self.session()
        s.write_ledger("notes,date,type,category,description,amount\r\n"
                       "mine,2026-01-01,Income,Salary,,1.00\r\n")
        with s.active():
            bt.save_transaction(record())
            self.assertEqual(len(bt.load_transactions()), 2)
        self.assertTrue(s.ledger_text().endswith("\r\n,2026-03-01,Expense,Food,,1.00\r\n"))

    def test_bad_rows_are_left_in_the_file_and_reported(self):
        s = self.session()
        text = HEADER + "2026-01-01,Income,Salary,,1\r\nnot,a,row,,x\r\n"
        s.write_ledger(text)
        with s.active():
            txns, problems = bt.load_ledger()
            bt.save_transaction(record())
        self.assertEqual(len(txns), 1)
        self.assertEqual(problems, ["Row 3 skipped: invalid date 'not'."])
        self.assertTrue(s.ledger_text().startswith(text))

    def test_a_ledger_saved_by_the_original_version_loads(self):
        # The original wrote float reprs and whatever date was typed.
        s = self.session()
        s.write_ledger(HEADER + "2026-3-1,Income,Salary,March salary,2500.0\r\n"
                                "2026-03-02,Expense,Food,,45.3\r\n")
        with s.active():
            txns, problems = bt.load_ledger()
        self.assertEqual(problems, [])
        self.assertEqual([(t["date"], t["amount"]) for t in txns],
                         [("2026-03-01", D("2500.00")), ("2026-03-02", D("45.30"))])

    def test_the_bundled_sample_data_loads_cleanly(self):
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        txns, problems = bt.read_transactions(os.path.join(here, "test_data.csv"))
        self.assertEqual(problems, [])
        self.assertEqual(len(txns), 37)
        self.assertEqual({t["type"] for t in txns}, {"Income", "Expense"})


if __name__ == "__main__":
    unittest.main()
