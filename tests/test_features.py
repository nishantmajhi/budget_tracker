"""The features, driven through their prompts against a scratch ledger."""

import os
import unittest
from decimal import Decimal
from unittest import mock

import budget_tracker as bt

from helpers import HEADER, LedgerCase

SAMPLE = (HEADER
          + "2026-03-05,Expense,Food,Groceries,45.30\r\n"
          + "2026-03-01,Income,Salary,March salary,2500.00\r\n"
          + "2026-02-10,Expense,Rent,February rent,850.00\r\n")


class AddTransaction(LedgerCase):

    def test_an_expense_is_saved_with_the_answers_given(self):
        s = self.session()
        s.call("add_transaction", answers=["2", "1", "Lunch", "4.5", "2026-3-7"])
        self.assertEqual(s.ledger_text(), HEADER + "2026-03-07,Expense,Food,Lunch,4.50\r\n")
        self.assertIn("Expense of GBP 4.50 added under 'Food'.", s.output)

    def test_an_income_uses_the_income_categories(self):
        s = self.session()
        s.call("add_transaction", answers=["1", "4", "", "20", "2026-03-07"])
        self.assertEqual(s.ledger_text(), HEADER + "2026-03-07,Income,Gift,,20.00\r\n")

    def test_bad_answers_are_asked_again(self):
        s = self.session()
        s.call("add_transaction",
               answers=["2", "0", "99", "3", "", "nan", "-1", "0", "12", "2026-02-30", "2026-03-07"])
        self.assertEqual(s.ledger_text(), HEADER + "2026-03-07,Expense,Rent,,12.00\r\n")
        self.assertEqual(s.output.count("Invalid choice. Please enter a number"), 2)
        self.assertEqual(s.output.count("Please enter a valid positive number"), 3)
        self.assertEqual(s.output.count("Invalid date."), 1)

    def test_an_unknown_type_returns_to_the_menu_without_saving(self):
        s = self.session()
        s.call("add_transaction", answers=["3"])
        self.assertFalse(s.data_file.exists())
        self.assertIn("Invalid choice. Returning to menu.", s.output)

    def test_pressing_enter_at_the_date_uses_the_default_offered(self):
        s = self.session()
        seen = {}

        def ask(prompt, **kwargs):
            if "YYYY-MM-DD" in prompt:
                seen["default"] = kwargs.get("default")
                return kwargs["default"]
            return answers.pop(0)

        answers = ["2", "1", "", "1"]
        with s.active(), mock.patch.object(bt.Prompt, "ask", side_effect=ask):
            bt.add_transaction()
        self.assertEqual(bt.parse_date(seen["default"]), seen["default"])
        self.assertIn(f"{seen['default']},Expense,Food,,1.00", s.ledger_text())


class ImportCsv(LedgerCase):

    def test_good_rows_are_added_and_bad_ones_reported(self):
        s = self.session()
        src = s.write("in.csv", HEADER
                      + "2026-03-01,Income,Salary,,100\r\n"
                      + "2026-03-02,Expense,Food,,-4\r\n"
                      + "2026-03-03,expense,Food,  Lunch ,4.555\r\n")
        s.call("import_csv", answers=[src])
        self.assertEqual(s.ledger_text(), HEADER
                         + "2026-03-01,Income,Salary,,100.00\r\n"
                         + "2026-03-03,Expense,Food,Lunch,4.56\r\n")
        self.assertIn("Row 3 skipped: invalid amount '-4'.", s.output)
        self.assertIn("Import complete: 2 row(s) added, 1 row(s) skipped.", s.output)

    def test_imports_append_to_what_is_already_there(self):
        s = self.session()
        s.write_ledger(SAMPLE)
        src = s.write("in.csv", HEADER + "2026-04-01,Income,Gift,,5\r\n")
        s.call("import_csv", answers=[src])
        self.assertEqual(s.ledger_text(), SAMPLE + "2026-04-01,Income,Gift,,5.00\r\n")

    def test_a_missing_file_is_reported(self):
        s = self.session()
        s.call("import_csv", answers=[s.path("nope.csv")])
        self.assertIn("File not found:", s.output)
        self.assertFalse(s.data_file.exists())

    def test_missing_columns_are_reported_and_nothing_is_written(self):
        s = self.session()
        src = s.write("in.csv", "date,amount\r\n2026-03-01,5\r\n")
        s.call("import_csv", answers=[src])
        self.assertIn("Missing columns in source file: category, description, type", s.output)
        self.assertFalse(s.data_file.exists())

    def test_a_file_in_another_encoding_is_reported_and_nothing_is_written(self):
        s = self.session()
        src = s.write("in.csv", HEADER + "2026-03-01,Expense,Food,£5,5\r\n", encoding="cp1252")
        s.call("import_csv", answers=[src])
        self.assertIn("not UTF-8", s.output)
        self.assertFalse(s.data_file.exists())

    def test_a_file_with_no_usable_rows_does_not_create_the_ledger(self):
        s = self.session()
        src = s.write("in.csv", HEADER + "2026-03-01,Expense,Food,,zero\r\n")
        s.call("import_csv", answers=[src])
        self.assertIn("0 row(s) added, 1 row(s) skipped", s.output)
        self.assertFalse(s.data_file.exists())

    def test_the_data_file_itself_is_refused(self):
        s = self.session()
        s.write_ledger(SAMPLE)
        s.call("import_csv", answers=[str(s.data_file)])
        self.assertIn("That is the tracker's own data file", s.output)
        self.assertEqual(s.ledger_text(), SAMPLE)

    def test_a_directory_is_reported_as_unreadable(self):
        s = self.session()
        s.call("import_csv", answers=[self.tmp])
        self.assertIn("Could not read file:", s.output)

    def test_the_whole_import_is_one_write(self):
        s = self.session()
        src = s.write("in.csv", HEADER + "".join(
            f"2026-03-01,Expense,Food,row {i},1\r\n" for i in range(50)))
        with mock.patch.object(bt, "save_transactions", wraps=bt.save_transactions) as save:
            s.call("import_csv", answers=[src])
        self.assertEqual(save.call_count, 1)
        self.assertEqual(len(save.call_args.args[0]), 50)

    def test_a_failure_to_save_is_reported(self):
        s = self.session()
        src = s.write("in.csv", HEADER + "2026-03-01,Expense,Food,,1\r\n")
        with mock.patch.object(bt, "save_transactions", side_effect=PermissionError("locked")):
            s.call("import_csv", answers=[src])
        self.assertIn("Could not save the imported rows: locked", s.output)
        self.assertNotIn("Import complete", s.output)


class ExportCsv(LedgerCase):

    def test_everything_is_written_in_date_order(self):
        s = self.session()
        s.write_ledger(SAMPLE)
        dest = s.path("out.csv")
        s.call("export_csv", answers=[dest])
        with open(dest, newline="", encoding="utf-8") as f:
            self.assertEqual(f.read(), HEADER
                             + "2026-02-10,Expense,Rent,February rent,850.00\r\n"
                             + "2026-03-01,Income,Salary,March salary,2500.00\r\n"
                             + "2026-03-05,Expense,Food,Groceries,45.30\r\n")
        self.assertIn("Exported 3 transaction(s)", s.output)

    def test_an_export_imports_back_to_the_same_ledger(self):
        s = self.session()
        s.write_ledger(SAMPLE)
        dest = s.path("out.csv")
        s.call("export_csv", answers=[dest])
        with s.active():
            before = sorted(bt.load_transactions(), key=lambda t: t["date"])
        os.remove(s.data_file)
        s.call("import_csv", answers=[dest])
        with s.active():
            self.assertEqual(bt.load_transactions(), before)

    def test_the_default_name_carries_todays_date(self):
        s = self.session()
        s.write_ledger(SAMPLE)
        seen = {}

        def ask(prompt, **kwargs):
            seen["default"] = kwargs.get("default")
            return s.path("x.csv")

        with s.active(), mock.patch.object(bt.Prompt, "ask", side_effect=ask):
            bt.export_csv()
        self.assertRegex(seen["default"], r"^budget_export_\d{8}\.csv$")

    def test_an_existing_file_is_kept_unless_the_user_agrees(self):
        s = self.session()
        s.write_ledger(SAMPLE)
        dest = s.write("out.csv", "keep me")
        s.call("export_csv", answers=[dest], confirms=[False])
        self.assertIn("Export cancelled.", s.output)
        with open(dest, encoding="utf-8") as f:
            self.assertEqual(f.read(), "keep me")
        s.call("export_csv", answers=[dest], confirms=[True])
        with open(dest, encoding="utf-8") as f:
            self.assertTrue(f.read().startswith("date,type"))

    def test_nothing_to_export_is_said_so(self):
        s = self.session()
        s.call("export_csv")
        self.assertIn("No transactions to export.", s.output)

    def test_a_destination_that_cannot_be_written_is_reported(self):
        s = self.session()
        s.write_ledger(SAMPLE)
        s.call("export_csv", answers=[os.path.join(self.tmp, "no", "such", "dir.csv")])
        self.assertIn("Could not write file:", s.output)


class Summaries(LedgerCase):

    def test_the_monthly_summary_totals_each_month(self):
        s = self.session()
        s.write_ledger(SAMPLE)
        s.call("monthly_summary")
        lines = [line for line in s.output.splitlines() if "2026-0" in line]
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"2026-02.*0\.00.*850\.00.*-850\.00")
        self.assertRegex(lines[1], r"2026-03.*2500\.00.*45\.30.*2454\.70")

    def test_the_breakdown_gives_each_categorys_share(self):
        s = self.session()
        s.write_ledger(SAMPLE)
        with mock.patch.object(bt.plt, "show"):
            s.call("category_breakdown")
        self.assertRegex(s.output, r"Rent.*850\.00.*94\.9%")
        self.assertRegex(s.output, r"Food.*45\.30.*5\.1%")

    def test_empty_ledgers_are_said_so(self):
        s = self.session()
        for name, message in (("view_transactions", "No transactions found."),
                              ("monthly_summary", "No transactions to summarise."),
                              ("show_chart", "No data to chart yet."),
                              ("category_breakdown", "No expense data found.")):
            with self.subTest(name=name):
                s.call(name)
                self.assertIn(message, s.output)

    def test_the_transactions_are_listed_in_date_order(self):
        s = self.session()
        s.write_ledger(SAMPLE)
        s.call("view_transactions")
        dates = [d for d in ("2026-02-10", "2026-03-01", "2026-03-05")]
        positions = [s.output.index(d) for d in dates]
        self.assertEqual(positions, sorted(positions))


class MainMenu(LedgerCase):

    def test_the_balance_is_shown_and_exit_asks_first(self):
        s = self.session()
        s.write_ledger(SAMPLE)
        s.call("main", answers=["8", "8"], confirms=[False, True])
        self.assertEqual(s.output.count("Current Balance: GBP 1604.70"), 2)
        self.assertIn("Goodbye!", s.output)

    def test_unreadable_rows_are_counted_under_the_balance(self):
        s = self.session()
        s.write_ledger(SAMPLE + "2026-03-09,Expense,Food,,abc\r\n2026-13-01,Expense,Food,,1\r\n")
        s.call("main", answers=["8"], confirms=[True])
        self.assertIn("Current Balance: GBP 1604.70", s.output)
        self.assertIn("2 row(s) in budget_data.csv could not be read", s.output)
        self.assertIn("Row 5 skipped: invalid amount 'abc'.", s.output)

    def test_a_ledger_missing_a_column_stops_the_program_without_touching_it(self):
        s = self.session()
        s.write_ledger("date,type,category,amount\r\n2026-03-01,Income,Salary,5\r\n")
        s.call("main")
        self.assertIn("Missing columns in source file: description", s.output)
        self.assertIn("The file has not been changed.", s.output)

    def test_a_ledger_that_breaks_during_the_session_stops_it_cleanly(self):
        s = self.session()
        s.write_ledger(SAMPLE)
        with s.active(answers=["2"]), \
                mock.patch.object(bt, "load_transactions", side_effect=bt.LedgerError("broken")):
            bt.main()
        self.assertIn("broken", s.output)
        self.assertIn("The file has not been changed.", s.output)

    def test_every_menu_option_runs_against_the_sample_data(self):
        s = self.session()
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        s.call("import_csv", answers=[os.path.join(here, "test_data.csv")])
        with mock.patch.object(bt.plt, "show"):
            s.call("main", answers=["2", "3", "4", "5", "6", "3", "7", "8"], confirms=[True])
        self.assertIn("Import complete: 37 row(s) added, 0 row(s) skipped.", s.output)
        self.assertIn("Goodbye!", s.output)


if __name__ == "__main__":
    unittest.main()
