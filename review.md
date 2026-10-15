# Personal Budget Tracker — review and cleanup record

First reviewed 2026-09-04. Remediated 2026-09-30 on branch `cleanup/2026-09-30`.
Nothing pushed.

**105 tests, all passing.** `python tests/run.py`, with the packages from
`requirements.txt`; plain `unittest`, nothing else. Here it runs from
`D:\dev-tools\venvs\budget` (Python 3.12, rich 15.0.0, plotext 5.3.2).

---

## Corrections to the first review

The first review called the issues "real but small", and said none of them
would be out of place in a first-year project. Its two P2s were real. But it
read the code as a sequence of reasonable-looking steps. It did not ask what
happens when those steps meet the file they write to, or the text people
actually type, and that is where the serious defects were.

**It missed the worst one.** Importing `budget_data.csv` into itself never
finished. `import_csv` appended each row as it read it, so the reader kept
finding the rows it had just written. Three rows grew until the disk filled.
The review praised the importer's per-row reporting, which is in the same loop.

**It missed that the program corrupted its own file.** A ledger saved by a text
editor often has no newline after its last row. `save_transaction` appended
straight onto that line and joined two rows into one, with an amount of
`12.52026-03-02`. From then on the program crashed at every startup. That is
worse than the review's P2 (a malformed amount crashes the loader), because
here the program is what writes the malformed amount.

**It missed that Rich reads data as markup.** Every description, category and
path went into a markup string. A description containing `[/]` crashed View
All Transactions. That happened every time, because the row stays in the
ledger. `Amazon [refund] item` displayed as `Amazon  item`.

**Its money finding was right in kind and wrong in symptom.** It predicted
totals like `1234.5600000000002`. That cannot appear, because every figure is
printed to two decimal places. The sign can, though: 0.30 of income less
0.10 + 0.20 of spending gave a balance of `-0.00`, coloured red.

**"Imports are validated" was half true.** The date was checked for presence
but not for being a date, which the review did note. The type was not checked
at all, which it did not: `income` in lower case, or any other type, was
subtracted from the balance as spending. And `float("nan") <= 0` is false, so
`nan` passed the positive-number check, at the prompt as well as on import.

**The README's install line had broken since the review.** `pip install rich
plotext` now installs plotext 6.1. That release is a rewrite with no `clf()`,
`bar()`, `theme()` or `show()`, so menu options 4 and 5 raised AttributeError
on a fresh install. The review could not have seen this, since it depends on
the date. It is recorded because "run with `pip install rich plotext`" was the
review's own note for the next session.

## Fixed

Every item was reproduced against the original code before it was fixed. The
tests in `tests/test_*_regressions.py` and `tests/test_chart.py` run each
scenario against the original, read out of git, and assert that the defect is
there before asserting that it is fixed. Each regression test was also seen
failing against the working code before its fix went in.

| #   | Defect                                                                                                                          | Test                                                                                                                         |
| --- | ------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 1   | Importing the data file into itself never terminated                                                                            | `test_importing_the_data_file_into_itself_terminates`                                                                        |
| 2   | Appending to a file with no final newline joined two rows, and then every startup crashed                                       | `test_a_row_appended_to_a_file_without_a_final_newline_stays_a_row`                                                          |
| 3   | An empty (0-byte) data file never got a header; the first transaction became it                                                 | `test_an_empty_data_file_gets_a_header_before_its_first_row`                                                                 |
| 4   | Rows appended to a ledger whose columns had been reordered in a spreadsheet went under the wrong headings, sometimes silently   | `test_a_row_appended_to_a_reordered_file_follows_its_columns`                                                                |
| 5   | **P2** One malformed amount stopped the program starting                                                                        | `test_a_malformed_amount_in_the_data_file_does_not_stop_the_program`                                                         |
| 6   | A ledger re-saved by Excel as CSV UTF-8 (with a BOM) crashed every feature that read a date                                     | `test_a_data_file_saved_by_excel_as_csv_utf8_still_loads`                                                                    |
| 7   | A ledger re-saved by Excel as plain CSV (Windows-1252) was a UnicodeDecodeError traceback                                       | `test_a_data_file_that_is_not_utf8_is_reported_not_a_traceback`                                                              |
| 8   | A balance of exactly zero showed as a red `-0.00`                                                                               | `test_a_balance_of_exactly_zero_is_not_shown_as_negative`                                                                    |
| 9   | `nan` and `inf` were accepted as amounts                                                                                        | `test_nan_and_infinity_are_not_amounts`, `test_imported_nan_is_skipped`                                                      |
| 10  | Any imported type except exactly `Income` counted as spending                                                                   | `test_an_imported_type_is_matched_without_regard_to_case`                                                                    |
| 11  | `2026-2-5` was stored unpadded: it sorted after December and summarised as month `2026-2-`                                      | `test_a_date_typed_without_zero_padding_is_stored_padded`, `test_unpadded_dates_already_in_a_ledger_are_summarised_by_month` |
| 12  | Imported dates were not checked at all                                                                                          | `test_an_imported_date_must_be_a_date`                                                                                       |
| 13  | An import from Excel's CSV UTF-8 was refused for a missing `date` column                                                        | `test_an_import_saved_by_excel_as_csv_utf8_is_accepted`                                                                      |
| 14  | An import that failed part-way had already saved everything before that point                                                   | `test_an_import_that_fails_part_way_adds_nothing`                                                                            |
| 15  | Adding a transaction while Excel held the ledger open (PermissionError) crashed the program                                     | `test_a_locked_data_file_is_reported_rather_than_crashing`                                                                   |
| 16  | `DATA_FILE` depended on the working directory, so starting elsewhere silently used a different, empty ledger                    | `test_the_data_file_is_beside_the_script_not_in_the_working_directory`                                                       |
| 17  | `[/]` in a description crashed View; `[refund]` vanished from it                                                                | `test_a_description_containing_a_closing_tag_…`, `test_square_brackets_in_a_description_are_shown`                           |
| 18  | A bracketed category vanished from the breakdown; a bracketed path was mangled; a bracketed bad value crashed an import         | three tests in `test_display_regressions.py`                                                                                 |
| 19  | Typing `²` at a numbered prompt crashed (`isdigit` is true, `int()` fails)                                                      | `test_a_superscript_digit_at_a_number_prompt_asks_again`                                                                     |
| 20  | The "grouped" monthly chart drew expenses over income at the same x, so a month that spent more than it earned showed no income | `test_the_income_bar_is_not_hidden_behind_the_expense_bar`                                                                   |
| 21  | **P2** No `.gitignore`: the ledger would have been committed by `git add -A`                                                    | —                                                                                                                            |
| 22  | plotext 6 broke both charts on a fresh install                                                                                  | `test_the_installed_plotext_has_the_api_the_charts_use`                                                                      |

The shape of the fix is one `parse_transaction()`, built from `parse_amount`,
`parse_date` and `parse_type`. Both the loader and the importer use it, so the
two can no longer disagree about what a valid row is.

`read_transactions()` reads the whole file before it returns, which fixes items
1 and 14. Money is `Decimal`, rounded half-up to the penny, as it was typed
(2.675 → 2.68, where `round()` on a float gave 2.67). Rows the loader cannot
use are left in the file, never rewritten, and a line under the balance counts
them.

The review's P3s are all done: dates are validated, `DATA_FILE` is resolved
against the script, imports are written in one batch, `shutil` is gone, and
the Decimal reasoning is in the README. The two `except Exception` clauses now
catch `OSError`, plus `UnicodeDecodeError` and `csv.Error` inside
`read_transactions`.

### The one visible change

Item 20 changes how the chart looks: each month has two narrower bars instead
of one overlapping pair. It is a correctness fix, since the README and the code
comment both promised a grouped chart and the old one hid data. But it is the
only change a user would see that is not an error message, so it is a commit of
its own (`d0e847f`) and can be reverted alone.

Three messages are new, each for a condition that used to be a traceback or a
silent failure:

- the count of unreadable rows under the balance;
- "Cannot read … The file has not been changed" for a ledger that cannot be
  opened;
- "That is the tracker's own data file" when you import the ledger into
  itself.

## Deliberately not done

- **Load once at startup** (the review's first "bug"). The whole file is still
  parsed on every menu loop. At 10,000 rows a load takes about 120 ms here, so
  a summary costs a quarter of a second. Appending at once is what keeps a
  crash from losing a transaction, so the trade is still the right one.
- **Edit and delete, custom categories.** These are features, not fixes.
- **Ctrl+C or end-of-input at a prompt prints a traceback.** That is how the
  program exits, which makes it UX, and it destroys nothing.
- **CSV formula injection on export.** A description beginning with `=` is
  exported as written, and a spreadsheet may treat it as a formula. Guarding it
  would change the data on a round trip. The only source of such a description
  is the user or a file the user imported, so it is left alone.
- **Exporting over `budget_data.csv`** writes only the rows the tracker could
  read. Any unreadable rows are dropped, after the overwrite confirmation. It
  is an odd thing to do, and the main menu will already have been reporting
  those rows. It is noted, not guarded.
- **The duplicated `FEATURE 6` section header** (Import is feature 6, and so
  is the Import/Export submenu). The review said to check whether the
  section-per-feature layout was a rubric requirement, so the file's layout is
  unchanged: one file, same sections, same order. New functions sit in the
  existing DATA LAYER and HELPER FUNCTIONS sections.

## Structure

The program is still one file, `budget_tracker.py`, for the reason above. What
changed inside it is that the decisions are now functions with no I/O:
`parse_amount`, `parse_date`, `parse_type`, `parse_transaction`,
`monthly_totals`, `category_totals` and `get_running_balance`. Most of the
suite tests those directly.

Added: `requirements.txt` (plotext pinned `>=5.2,<6`), `.gitignore`, and
`tests/`:

- `helpers.py` points a module's `DATA_FILE`, `console` and prompts at a
  scratch directory, a string buffer and a scripted list of answers. It also
  holds `RegressionCase`, which runs one scenario against both versions of the
  code.
- `original.py` imports the baseline from git, looking the commit up by its
  subject line ("Initial commit"). Without git, those tests skip.
- `chart.py` decodes plotext's ANSI output cell by cell, so a test can say
  which series is visible where.

## Notes for whoever is next

- **Rich markup is a data-escaping problem.** Any `console.print(f"…{x}…")`
  where `x` came from a file or the keyboard needs `escape(x)`. Watch for one
  trap when you test it: on Windows a path built with `pathlib` puts a
  backslash before the bracket, and Rich reads that as an escape. A test that
  builds its path that way passes against the unfixed code. The first draft of
  `test_a_path_with_square_brackets_is_shown_as_typed` did exactly that.
- **plotext's two series differ only by colour**, and `tests/chart.py` reads
  them that way. The axis label "Amount (GBP)" has a G of its own, so the
  decoder only looks inside the plot frame. An earlier draft did not, and
  "found" green bars in the original chart.
- **Excel is the likeliest second writer of this file.** It adds a BOM with
  CSV UTF-8, writes Windows-1252 with plain CSV, locks the file while it is
  open, and can reorder columns. Each of those was a separate defect here.
- Python for this project: `D:\dev-tools\venvs\budget\Scripts\python.exe
tests/run.py`.

## For the author

- **Licence.** The old README said "MIT" and linked a `LICENSE` file that
  never existed. The new README says no licence has been chosen. Adding one is
  yours to decide, and so is whose name goes on it.
- **The data file moved.** It is now always beside `budget_tracker.py`. Anyone
  who ran the tracker from another directory has a `budget_data.csv` in that
  directory. The tracker will not find it, and it should be moved beside the
  script.

## Five minutes at a real keyboard

Every feature was driven end to end: the real program ran with piped input
from a different working directory. It imported `test_data.csv`, went through
every menu option and exported. The charts were checked in that output. The
things that output cannot show:

1. Run it in Windows Terminal and look at options 4 and 5 in colour, at your
   real window width. The tests fix the chart size at 60×16.
2. Open `budget_data.csv` in Excel, add a transaction in the tracker, and
   confirm it says it could not save rather than crashing. Then close Excel and
   add it again.
