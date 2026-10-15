"""Defects in the data layer: the original misbehaving, then the fix, in one run.

See `RegressionCase` in helpers.py for how each scenario is run twice.
"""

import contextlib
import os
import stat
import unittest
from decimal import Decimal
from unittest import mock

import budget_tracker as bt

import original
from helpers import HEADER, RegressionCase

ROW = {"date": "2026-03-02", "type": "Income", "category": "Salary",
       "description": "", "amount": 5.0}


class Runaway(BaseException):
    """Raised by the guard when an import keeps writing. A BaseException, so
    the original's `except Exception` cannot swallow it."""


class Regression(RegressionCase):

    # -- The data file ------------------------------------------------------

    def test_importing_the_data_file_into_itself_terminates(self):
        # The original appended each row as it read it, so the reader kept
        # finding the rows it had just written: three rows grew without end.
        def scenario(s):
            s.write_ledger(HEADER + "".join(
                f"2026-03-0{i},Expense,Food,row {i},1\r\n" for i in (1, 2, 3)))

            def guard(original_fn):
                def wrapped(*args):
                    if os.path.getsize(s.data_file) > 20_000:
                        raise Runaway
                    return original_fn(*args)
                return wrapped

            with contextlib.ExitStack() as stack:
                for name in ("save_transaction", "save_transactions"):
                    if hasattr(s.m, name):
                        stack.enter_context(
                            mock.patch.object(s.m, name, guard(getattr(s.m, name))))
                try:
                    s.call("import_csv", answers=[str(s.data_file)])
                except Runaway:
                    return "runaway"
            return len(s.call("load_transactions"))

        orig, cur = self.both(scenario)
        self.assertEqual(orig, "runaway")
        self.assertEqual(cur, 3, "the ledger must be left as it was")

    def test_a_row_appended_to_a_file_without_a_final_newline_stays_a_row(self):
        # A hand-edited ledger often has no newline after its last row. The
        # original appended straight onto it, joining two rows into one whose
        # amount was "12.52026-03-02" -- and then crashed on every startup.
        def scenario(s):
            s.write_ledger(HEADER + "2026-03-01,Expense,Food,,12.5")
            s.call("save_transaction", dict(ROW))
            return self.outcome(lambda: [t["amount"] for t in s.call("load_transactions")])

        orig, cur = self.both(scenario)
        self.assertIsInstance(orig, ValueError)
        self.assertEqual(cur, [Decimal("12.50"), Decimal("5.00")])

    def test_a_row_appended_to_a_reordered_file_follows_its_columns(self):
        # A spreadsheet can reorder the columns. The original appended in its
        # own order regardless, so the new row's fields landed under the
        # wrong headings: here a description read back as the category.
        def scenario(s):
            s.write_ledger("date,type,description,category,amount\r\n"
                           "2026-03-01,Expense,Weekly shop,Food,12.50\r\n")
            s.call("save_transaction", {"date": "2026-03-02", "type": "Expense",
                                        "category": "Transport", "description": "Bus",
                                        "amount": 2.0})
            return [t["category"] for t in s.call("load_transactions")]

        orig, cur = self.both(scenario)
        self.assertEqual(orig, ["Food", "Bus"])
        self.assertEqual(cur, ["Food", "Transport"])

    def test_an_empty_data_file_gets_a_header_before_its_first_row(self):
        # The original wrote the header only when the file did not exist, so
        # into an empty file the first transaction became the header and the
        # ledger read back as empty.
        def scenario(s):
            s.write_ledger("")
            s.call("save_transaction", dict(ROW))
            return len(s.call("load_transactions"))

        orig, cur = self.both(scenario)
        self.assertEqual(orig, 0)
        self.assertEqual(cur, 1)

    def test_a_malformed_amount_in_the_data_file_does_not_stop_the_program(self):
        # The review's P2. One bad row made the original raise at the top of
        # the main loop, so the program could not start at all.
        def scenario(s):
            s.write_ledger(HEADER + "2026-03-01,Income,Salary,,100\r\n"
                                    "2026-03-02,Expense,Food,,abc\r\n")
            result = self.outcome(lambda: s.call("main", answers=["8"], confirms=[True]))
            return result, s.output

        (orig, _), (cur, out) = self.both(scenario)
        self.assertIsInstance(orig, ValueError)
        self.assertIsNone(cur)
        self.assertIn("GBP 100.00", out)
        self.assertIn("1 row(s)", out)
        self.assertIn("invalid amount 'abc'", out)

    def test_a_data_file_saved_by_excel_as_csv_utf8_still_loads(self):
        # Excel's "CSV UTF-8" starts the file with a byte-order mark, which the
        # original read as part of the first column name. Loading succeeded;
        # every feature that looked at a date then raised KeyError 'date'.
        def scenario(s):
            s.write("budget_data.csv", HEADER + "2026-03-01,Income,Salary,,100\r\n",
                    encoding="utf-8-sig")
            return self.outcome(lambda: s.call("monthly_summary")), s.output

        (orig, _), (cur, out) = self.both(scenario)
        self.assertIsInstance(orig, KeyError)
        self.assertIsNone(cur)
        self.assertIn("2026-03", out)
        self.assertIn("100.00", out)

    def test_a_data_file_that_is_not_utf8_is_reported_not_a_traceback(self):
        # Excel's plain "CSV" is Windows-1252, so a pound sign becomes a byte
        # UTF-8 cannot decode. The original died with UnicodeDecodeError.
        def scenario(s):
            s.write("budget_data.csv", HEADER + "2026-03-01,Expense,Food,£5 lunch,5\r\n",
                    encoding="cp1252")
            before = s.data_file.read_bytes()
            result = self.outcome(lambda: s.call("main"))
            return result, s.output, s.data_file.read_bytes() == before

        (orig, _, _), (cur, out, unchanged) = self.both(scenario)
        self.assertIsInstance(orig, UnicodeDecodeError)
        self.assertIsNone(cur)
        self.assertIn("not UTF-8", out)
        self.assertTrue(unchanged)

    # -- Money --------------------------------------------------------------

    def test_a_balance_of_exactly_zero_is_not_shown_as_negative(self):
        # 0.3 of income less 0.1 + 0.2 of spending is -2.8e-17 in floats,
        # which the original formatted as "-0.00" and coloured red.
        def scenario(s):
            s.write_ledger(HEADER + "2026-03-01,Income,Salary,,0.3\r\n"
                                    "2026-03-02,Expense,Food,,0.1\r\n"
                                    "2026-03-03,Expense,Food,,0.2\r\n")
            balance = s.m.get_running_balance(s.call("load_transactions"))
            s.call("monthly_summary")
            return f"{balance:.2f}", balance < 0, s.output

        (o_text, o_neg, o_out), (c_text, c_neg, c_out) = self.both(scenario)
        self.assertEqual((o_text, o_neg), ("-0.00", True))
        self.assertIn("-0.00", o_out)
        self.assertEqual((c_text, c_neg), ("0.00", False))
        self.assertNotIn("-0.00", c_out)

    def test_nan_and_infinity_are_not_amounts(self):
        # float("nan") <= 0 is False, so the original accepted it, and one
        # NaN made the balance "GBP nan" for good.
        def scenario(s):
            got = [s.call("validate_amount", "Amount", answers=[bad, "12.5"])
                   for bad in ("nan", "inf", "-inf")]
            return [f"{a}" for a in got]

        orig, cur = self.both(scenario)
        self.assertEqual(orig, ["nan", "inf", "12.5"])
        self.assertEqual(cur, ["12.50", "12.50", "12.50"])

    def test_imported_nan_is_skipped(self):
        def scenario(s):
            src = s.write("in.csv", HEADER + "2026-03-01,Income,Salary,,nan\r\n"
                                             "2026-03-02,Income,Salary,,10\r\n")
            s.call("import_csv", answers=[src])
            return f"{s.m.get_running_balance(s.call('load_transactions'))}"

        orig, cur = self.both(scenario)
        self.assertEqual(orig, "nan")
        self.assertEqual(cur, "10.00")

    # -- Types and dates ----------------------------------------------------

    def test_an_imported_type_is_matched_without_regard_to_case(self):
        # Everything not spelled exactly "Income" was subtracted, so a bank
        # export's "income" took 100 off the balance instead of adding it,
        # and an unknown type like "Refund" was silently counted as spending.
        def scenario(s):
            src = s.write("in.csv", HEADER + "2026-03-01,income,Salary,,100\r\n"
                                             "2026-03-02,EXPENSE,Food,,30\r\n"
                                             "2026-03-03,Refund,Shopping,,20\r\n")
            s.call("import_csv", answers=[src])
            txns = s.call("load_transactions")
            return f"{s.m.get_running_balance(txns):.2f}", sorted({t['type'] for t in txns}), s.output

        (o_bal, o_types, _), (c_bal, c_types, c_out) = self.both(scenario)
        self.assertEqual(o_bal, "-150.00")
        self.assertIn("Refund", o_types)
        self.assertEqual(c_bal, "70.00")
        self.assertEqual(c_types, ["Expense", "Income"])
        self.assertIn("Row 4 skipped: invalid type 'Refund'", c_out)

    def test_a_date_typed_without_zero_padding_is_stored_padded(self):
        # strptime accepts 2026-2-5, and the original stored what was typed.
        # It then sorted after 2026-12-01 and summarised as month "2026-2-".
        def scenario(s):
            return s.call("validate_date", "Date", answers=["2026-2-5"])

        orig, cur = self.both(scenario)
        self.assertEqual(orig, "2026-2-5")
        self.assertEqual(cur, "2026-02-05")

    def test_an_imported_date_must_be_a_date(self):
        def scenario(s):
            src = s.write("in.csv", HEADER + "2026/03/05,Expense,Food,,1\r\n"
                                             "next tuesday,Expense,Food,,1\r\n"
                                             "2026-03-06,Expense,Food,,1\r\n")
            s.call("import_csv", answers=[src])
            return sorted(t["date"] for t in s.call("load_transactions"))

        orig, cur = self.both(scenario)
        self.assertEqual(orig, ["2026-03-06", "2026/03/05", "next tuesday"])
        self.assertEqual(cur, ["2026-03-06"])

    def test_unpadded_dates_already_in_a_ledger_are_summarised_by_month(self):
        def scenario(s):
            s.write_ledger(HEADER + "2026-2-5,Expense,Food,,1\r\n"
                                    "2026-02-20,Expense,Food,,2\r\n")
            s.call("monthly_summary")
            return [line for line in s.output.splitlines() if "2026-" in line]

        orig, cur = self.both(scenario)
        self.assertEqual(len(orig), 2, "the original split February in two")
        self.assertEqual(len(cur), 1)
        self.assertIn("3.00", cur[0])

    # -- Import -------------------------------------------------------------

    def test_an_import_saved_by_excel_as_csv_utf8_is_accepted(self):
        def scenario(s):
            src = s.write("in.csv", HEADER + "2026-03-01,Expense,Food,x,1\r\n",
                          encoding="utf-8-sig")
            s.call("import_csv", answers=[src])
            return s.output

        orig, cur = self.both(scenario)
        self.assertIn("Missing columns in source file: date", orig)
        self.assertIn("1 row(s) added", cur)

    def test_an_import_that_fails_part_way_adds_nothing(self):
        # The original saved each row as it went, so a file that failed to
        # decode 25 KB in left every row before that point in the ledger --
        # under a message saying the file could not be read. Importing again
        # after fixing the file then doubled them.
        def scenario(s):
            good = "".join(f"2026-03-01,Expense,Food,row {i},1\r\n" for i in range(800))
            src = s.path("in.csv")
            with open(src, "wb") as f:
                f.write((HEADER + good).encode("utf-8") + b"2026-03-02,Expense,Food,\xa35,5\r\n")
            s.call("import_csv", answers=[src])
            return len(s.call("load_transactions"))

        orig, cur = self.both(scenario)
        self.assertGreater(orig, 0)
        self.assertEqual(cur, 0)

    # -- Add ----------------------------------------------------------------

    def test_a_locked_data_file_is_reported_rather_than_crashing(self):
        # Excel locks a CSV it has open, so adding a transaction while the
        # ledger is open there raised PermissionError out of the main loop.
        # A read-only file fails the same way and needs no Excel.
        def scenario(s):
            s.write_ledger(HEADER)
            os.chmod(s.data_file, stat.S_IREAD)
            try:
                result = self.outcome(lambda: s.call(
                    "add_transaction", answers=["2", "1", "lunch", "5", "2026-03-01"]))
            finally:
                os.chmod(s.data_file, stat.S_IREAD | stat.S_IWRITE)
            return result, s.output, s.ledger_text()

        (orig, _, _), (cur, out, text) = self.both(scenario)
        self.assertIsInstance(orig, PermissionError)
        self.assertIsNone(cur)
        self.assertIn("Could not save the transaction", out)
        self.assertEqual(text, HEADER)


class DataFileLocation(unittest.TestCase):

    def test_the_data_file_is_beside_the_script_not_in_the_working_directory(self):
        # Started from any other directory, the original silently used (or
        # created) a different, empty ledger there.
        orig = original.require()
        self.assertEqual(orig.DATA_FILE, "budget_data.csv")
        self.assertTrue(os.path.isabs(bt.DATA_FILE))
        self.assertEqual(os.path.dirname(bt.DATA_FILE), os.path.dirname(os.path.abspath(bt.__file__)))
        self.assertEqual(os.path.basename(bt.DATA_FILE), "budget_data.csv")


if __name__ == "__main__":
    unittest.main()
