# Personal Budget Tracker

A personal finance tracker that runs in the terminal. You record income and
expenses, and it shows them as tables and bar charts. Everything is kept in one
CSV file that you can open in a spreadsheet.

It is a single Python file. It uses [`rich`](https://github.com/Textualize/rich)
for the tables and prompts and [`plotext`](https://github.com/piccolomo/plotext)
for the charts.

## Running it

You need Python 3.10 or later.

```bash
git clone https://github.com/nishantmajhi/budget_tracker.git
cd budget_tracker
pip install -r requirements.txt
python budget_tracker.py
```

Install from `requirements.txt`, not with a bare `pip install plotext`.
plotext 6 dropped the functions the charts use, so the file pins the 5.x
series.

To try it with some data, choose **6 → 1** (Import) and give the path to
`test_data.csv`. That file holds 37 invented transactions from March to May
2026.

## What it does

| Option | Feature |
| --- | --- |
| 1 | **Add Transaction.** Income or expense, a category, an optional description, the amount in GBP, and the date (Enter means today) |
| 2 | **View All Transactions.** Every record in date order, income in green and expenses in red |
| 3 | **Monthly Summary.** Income, expenses and net for each month |
| 4 | **Income vs Expenses Chart.** A bar chart with income and spending side by side for each month |
| 5 | **Spending Breakdown by Category.** Each expense category's total and its share of all spending, as a table and a bar chart |
| 6 | **Import / Export Data.** Add transactions from another CSV file, or save them all to one |
| 7 | Clear Screen |
| 8 | Exit |

The menu shows the current balance (all income less all expenses) every time
it comes round.

The categories are fixed:

- **Income:** Salary, Freelance, Investment, Gift, Other Income
- **Expense:** Food, Transport, Rent, Utilities, Entertainment, Health,
  Shopping, Other Expense

An imported file may use other category names, and they are kept as written.

## Where the data lives

Your transactions are stored in `budget_data.csv`, in the same folder as
`budget_tracker.py`. It does not matter which directory you start the tracker
from. The file is created when you add or import your first transaction, and
each new transaction is appended to the end of it.

`.gitignore` lists `budget_data.csv` and any `budget_export_*.csv`, so your
own records cannot be committed by accident.

You can edit the file by hand or in a spreadsheet. If you do, save it as
**CSV UTF-8**. Excel's plain "CSV" format uses a different encoding, and the
tracker will refuse to open that file rather than guess.

## The CSV format

The data file, imported files and exported files all share one format: a
header row with these five columns, in any order. Extra columns are ignored.

| Column | What is accepted | Example |
| --- | --- | --- |
| `date` | A real calendar date, `YYYY-MM-DD`. `2026-5-4` is accepted and stored as `2026-05-04` | `2026-05-14` |
| `type` | `Income` or `Expense`, in any mix of upper and lower case | `Expense` |
| `category` | Any non-empty text | `Food` |
| `description` | Any text, or empty | `Weekly groceries` |
| `amount` | A positive number, with no currency sign or thousands separator. It is rounded half-up to the penny, and anything that rounds to zero is refused | `47.30` |

A row that breaks any of these rules is never used. What happens to it
depends on where it is:

- **When importing**, the row is skipped and reported with its line number,
  and the rest of the file is imported. The whole file is read and checked
  before anything is written, so an import that fails part-way adds nothing.
- **In `budget_data.csv`**, the row is left in the file exactly as it is, but
  it is left out of every total. A line under the balance says how many rows
  were left out and what is wrong with the first one.

If a file is missing a column, or is not UTF-8 text, it is not read at all.
The tracker says why and leaves the file untouched.

Amounts are held as exact decimals, never as floating-point numbers, so every
total is exact to the penny.

## Tests

```bash
python tests/run.py
```

The suite is about 100 tests written with the standard library's `unittest`.
It needs only the packages in `requirements.txt`. The tests use temporary
directories and never touch your `budget_data.csv`.

Some tests are regression tests. Each one runs the same scenario against the
original version of the program, which it reads from git history, and checks
that the original shows the bug before checking that the current code does
not. Outside a git checkout those tests are skipped.

## Project layout

```
budget_tracker/
├── budget_tracker.py   the whole program
├── requirements.txt
├── test_data.csv       sample transactions to import
└── tests/
    ├── run.py          runs the suite
    ├── helpers.py      scratch ledger, captured console, scripted prompts
    ├── original.py     loads the original program from git history
    ├── chart.py        reads plotext's output back by colour
    └── test_*.py
```

## Licence

Free for personal, non-commercial use. You may use, study and modify this
software for yourself, but you may not use it commercially, and you may not
share or publish it, in its original form or modified. See [LICENSE](LICENSE)
for the full terms.
