"""
Personal Budget Tracker
=======================
A terminal-based personal finance tracker with rich UI and plotext charts.
Data is persisted to a CSV file between sessions.
"""

import csv
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from collections import defaultdict

# Third-party libraries (pip install -r requirements.txt)
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich import box
import plotext as plt

# ---------------------------------------------
# CONFIGURATION
# ---------------------------------------------
# Beside this script, so the same ledger is used whichever directory the
# tracker is started from.
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "budget_data.csv")
CSV_HEADERS = ["date", "type", "category", "description", "amount"]
TRANSACTION_TYPES = ["Income", "Expense"]

INCOME_CATEGORIES = ["Salary", "Freelance", "Investment", "Gift", "Other Income"]
EXPENSE_CATEGORIES = ["Food", "Transport", "Rent", "Utilities",
                       "Entertainment", "Health", "Shopping", "Other Expense"]

console = Console()


# ---------------------------------------------
# DATA LAYER - CSV read / write
# ---------------------------------------------

class LedgerError(Exception):
    """A CSV file that cannot be read as transactions at all."""


def parse_amount(text) -> Decimal | None:
    """Return a positive amount rounded to the penny, or None if `text` is not one.

    Money is held as Decimal so that totals are exact: in floats, 0.30 of
    income less 0.10 + 0.20 of spending is a balance of -0.00."""
    try:
        amount = Decimal(str(text or "").strip())
        if not amount.is_finite():
            return None
        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return None
    return amount if amount > 0 else None


def parse_date(text) -> str | None:
    """Return `text` as a YYYY-MM-DD string, or None if it is not a real date.

    strptime accepts "2026-2-5", so the date is written back out padded;
    otherwise it would sort after "2026-12-01" and group as month "2026-2-"."""
    try:
        return datetime.strptime(str(text or "").strip(), "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def parse_type(text) -> str | None:
    """Return "Income" or "Expense" whatever the case of `text`, else None.

    Everything that is not income is subtracted from the balance, so an
    unrecognised type has to be refused rather than counted as spending."""
    wanted = str(text or "").strip().lower()
    for t_type in TRANSACTION_TYPES:
        if t_type.lower() == wanted:
            return t_type
    return None


def parse_transaction(row: dict) -> tuple[dict | None, str | None]:
    """Validate one CSV row. Returns (record, None), or (None, reason) if it is unusable."""
    if not all(str(row.get(field) or "").strip() for field in ("date", "type", "category")):
        return None, "missing date, type, or category."

    date = parse_date(row["date"])
    if date is None:
        return None, f"invalid date '{row['date']}'."
    t_type = parse_type(row["type"])
    if t_type is None:
        return None, f"invalid type '{row['type']}'."
    amount = parse_amount(row.get("amount"))
    if amount is None:
        return None, f"invalid amount '{row.get('amount') or ''}'."

    return {
        "date":        date,
        "type":        t_type,
        "category":    row["category"].strip(),
        "description": str(row.get("description") or "").strip(),
        "amount":      amount,
    }, None


def read_transactions(path: str) -> tuple[list[dict], list[str]]:
    """Read and validate every row of a transactions CSV.

    Returns the usable records and a message for each row that was skipped.
    The whole file is read before anything is returned, so a caller that
    writes afterwards can never read back its own rows, and a file that fails
    part-way leaves nothing half-imported.

    Raises LedgerError if the file has no usable header or is not UTF-8 text,
    and OSError if it cannot be opened."""
    records, problems = [], []
    try:
        # utf-8-sig: Excel's "CSV UTF-8" starts the file with a byte-order mark
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            missing = sorted(set(CSV_HEADERS) - set(reader.fieldnames or []))
            if missing:
                raise LedgerError(f"Missing columns in source file: {', '.join(missing)}")
            for row in reader:
                record, reason = parse_transaction(row)
                if record is None:
                    problems.append(f"Row {reader.line_num} skipped: {reason}")
                else:
                    records.append(record)
    except UnicodeDecodeError:
        raise LedgerError("The file is not UTF-8 text. In Excel, save it as 'CSV UTF-8'.") from None
    except csv.Error as e:
        raise LedgerError(f"The file is not valid CSV: {e}") from None
    return records, problems


def load_ledger() -> tuple[list[dict], list[str]]:
    """Load the data file: the usable transactions, and a message for each row
    that could not be read. Unreadable rows are left in the file untouched.
    Returns empty lists if the file does not exist yet or is empty."""
    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        return [], []
    return read_transactions(DATA_FILE)


def load_transactions() -> list[dict]:
    """Load all usable transactions from the CSV file."""
    return load_ledger()[0]


def save_transactions(transactions: list[dict]) -> None:
    """Append transactions to the CSV file in a single write.
    Creates the file with headers if it does not exist or is empty."""
    needs_header = not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0
    needs_newline = False
    columns = CSV_HEADERS
    if not needs_header:
        # A file last saved by a text editor may not end with a line break,
        # and the first new row would then be joined onto its last row.
        with open(DATA_FILE, "rb") as f:
            f.seek(-1, os.SEEK_END)
            needs_newline = f.read(1) not in (b"\n", b"\r")
        # A spreadsheet may have reordered or added columns; follow the file
        with open(DATA_FILE, newline="", encoding="utf-8-sig") as f:
            header = next(csv.reader(f), [])
        if set(CSV_HEADERS) <= set(header):
            columns = header
    with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
        if needs_newline:
            f.write("\r\n")
        writer = csv.DictWriter(f, fieldnames=columns, restval="")
        if needs_header:
            writer.writeheader()
        writer.writerows(transactions)


def save_transaction(transaction: dict) -> None:
    """Append a single transaction to the CSV file."""
    save_transactions([transaction])


# ---------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------

def get_running_balance(transactions: list[dict]) -> Decimal:
    """Calculate the current balance from all transactions."""
    balance = Decimal("0.00")
    for t in transactions:
        if t["type"] == "Income":
            balance += t["amount"]
        else:
            balance -= t["amount"]
    return balance


def monthly_totals(transactions: list[dict]) -> dict[str, dict[str, Decimal]]:
    """Total income and expense for each month (YYYY-MM), in month order."""
    monthly: dict[str, dict] = defaultdict(lambda: {"income": Decimal("0.00"),
                                                    "expense": Decimal("0.00")})
    for t in transactions:
        month = t["date"][:7]          # e.g. "2026-05"
        if t["type"] == "Income":
            monthly[month]["income"] += t["amount"]
        else:
            monthly[month]["expense"] += t["amount"]
    return dict(sorted(monthly.items()))


def category_totals(transactions: list[dict]) -> list[tuple[str, Decimal]]:
    """Total spending per expense category, highest first."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for t in transactions:
        if t["type"] == "Expense":
            totals[t["category"]] += t["amount"]
    return sorted(totals.items(), key=lambda x: x[1], reverse=True)


def pick_from_list(options: list[str], prompt_text: str) -> str:
    """Display a numbered list and return the user's chosen option.
    Keeps prompting until a valid number is entered."""
    for i, option in enumerate(options, 1):
        console.print(f"  [cyan]{i}.[/cyan] {option}")
    while True:
        choice = Prompt.ask(prompt_text)
        # isdecimal, not isdigit: "²" is a digit that int() cannot read
        if choice.isdecimal() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        console.print("[red]Invalid choice. Please enter a number from the list.[/red]")


def validate_amount(prompt_text: str) -> Decimal:
    """Prompt for a positive numeric amount, re-asking on invalid input."""
    while True:
        amount = parse_amount(Prompt.ask(prompt_text))
        if amount is not None:
            return amount
        console.print("[red]Please enter a valid positive number (e.g. 25.50).[/red]")


def validate_date(prompt_text: str) -> str:
    """Prompt for a date in YYYY-MM-DD format, defaulting to today."""
    today = datetime.today().strftime("%Y-%m-%d")
    while True:
        raw = Prompt.ask(f"{prompt_text} [dim](YYYY-MM-DD, press Enter for today)[/dim]",
                         default=today)
        date = parse_date(raw)
        if date is not None:
            return date
        console.print("[red]Invalid date. Please use YYYY-MM-DD format.[/red]")


# ---------------------------------------------
# FEATURE 1 - Add a transaction
# ---------------------------------------------

def add_transaction() -> None:
    """Guide the user through adding an income or expense entry."""
    console.print(Panel("[bold green]Add Transaction[/bold green]", expand=False))

    # Select transaction type
    console.print("\n  [cyan]1.[/cyan] Income\n  [cyan]2.[/cyan] Expense")
    t_type_choice = Prompt.ask("Select type")
    if t_type_choice == "1":
        t_type = "Income"
        categories = INCOME_CATEGORIES
    elif t_type_choice == "2":
        t_type = "Expense"
        categories = EXPENSE_CATEGORIES
    else:
        console.print("[red]Invalid choice. Returning to menu.[/red]")
        return

    # Select category
    console.print("\nSelect a category:")
    category = pick_from_list(categories, "Category number")

    # Description
    description = Prompt.ask("Description (optional)", default="")

    # Amount
    amount = validate_amount("Amount (GBP)")

    # Date
    date = validate_date("Date")

    # Build and save the record
    transaction = {
        "date": date,
        "type": t_type,
        "category": category,
        "description": description,
        "amount": amount,
    }
    try:
        save_transaction(transaction)
    except OSError as e:
        # Most often the file is open in Excel, which locks it on Windows
        console.print(f"\n[red]Could not save the transaction: {escape(str(e))}[/red]\n")
        return

    # Confirmation message
    colour = "green" if t_type == "Income" else "red"
    console.print(f"\n[{colour}]{t_type} of GBP {amount:.2f} added under '{category}'.[/{colour}]\n")


# ---------------------------------------------
# FEATURE 2 - View all transactions
# ---------------------------------------------

def view_transactions() -> None:
    """Display every recorded transaction in a formatted table."""
    transactions = load_transactions()

    if not transactions:
        console.print("[yellow]No transactions found. Add one first![/yellow]\n")
        return

    table = Table(title="All Transactions", box=box.ROUNDED,
                  show_lines=True, header_style="bold magenta")
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Type", style="bold")
    table.add_column("Category")
    table.add_column("Description")
    table.add_column("Amount (GBP)", justify="right")

    for t in sorted(transactions, key=lambda x: x["date"]):
        colour = "green" if t["type"] == "Income" else "red"
        table.add_row(
            t["date"],
            f"[{colour}]{t['type']}[/{colour}]",
            escape(t["category"]),
            escape(t["description"]) or "-",
            f"[{colour}]{t['amount']:.2f}[/{colour}]",
        )

    console.print(table)
    console.print()

# ---------------------------------------------
# FEATURE 3 - Monthly summary
# ---------------------------------------------

def monthly_summary() -> None:
    """Show income, expenses, and net balance grouped by month."""
    transactions = load_transactions()

    if not transactions:
        console.print("[yellow]No transactions to summarise.[/yellow]\n")
        return

    monthly = monthly_totals(transactions)

    table = Table(title="Monthly Summary", box=box.ROUNDED,
                  header_style="bold magenta", show_lines=True)
    table.add_column("Month", style="cyan")
    table.add_column("Income (GBP)", justify="right", style="green")
    table.add_column("Expenses (GBP)", justify="right", style="red")
    table.add_column("Net (GBP)", justify="right", style="bold")

    for month, totals in monthly.items():
        inc = totals["income"]
        exp = totals["expense"]
        net = inc - exp
        net_colour = "green" if net >= 0 else "red"
        table.add_row(
            month,
            f"{inc:.2f}",
            f"{exp:.2f}",
            f"[{net_colour}]{net:.2f}[/{net_colour}]",
        )

    console.print(table)
    console.print()


# ---------------------------------------------
# FEATURE 4 - Terminal bar chart (plotext)
# ---------------------------------------------

def show_chart() -> None:
    """Render a bar chart of monthly income vs expenses in the terminal."""
    transactions = load_transactions()

    if not transactions:
        console.print("[yellow]No data to chart yet.[/yellow]\n")
        return

    monthly  = monthly_totals(transactions)
    months   = list(monthly)
    incomes  = [float(monthly[m]["income"])  for m in months]
    expenses = [float(monthly[m]["expense"]) for m in months]

    # plotext grouped bar chart. Two bar() calls would draw both series on the
    # same x positions, hiding the shorter bar behind the taller one.
    plt.clf()
    plt.theme("dark")
    plt.multiple_bar(months, [incomes, expenses],
                     labels=["Income", "Expenses"], color=["green", "red"])
    plt.title("Monthly Income vs Expenses")
    plt.xlabel("Month")
    plt.ylabel("Amount (GBP)")
    plt.show()
    console.print()


# ---------------------------------------------
# FEATURE 5 - Spending breakdown by category
# ---------------------------------------------

def category_breakdown() -> None:
    """Show how total spending is split across expense categories."""
    # Sorted highest to lowest so the chart and table order match
    sorted_totals = category_totals(load_transactions())

    if not sorted_totals:
        console.print("[yellow]No expense data found.[/yellow]\n")
        return

    categories  = [c for c, _ in sorted_totals]
    amounts     = [float(a) for _, a in sorted_totals]
    grand_total = sum(a for _, a in sorted_totals)

    # Table view
    table = Table(title="Expense Breakdown by Category", box=box.ROUNDED,
                  header_style="bold magenta", show_lines=True)
    table.add_column("Category")
    table.add_column("Total (GBP)", justify="right", style="white")
    table.add_column("% of Spend",  justify="right")

    for cat, amt in sorted_totals:
        pct = (amt / grand_total) * 100
        table.add_row(escape(cat), f"{amt:.2f}", f"{pct:.1f}%")

    console.print(table)

    # Horizontal bar chart
    plt.clf()
    plt.theme("dark")
    plt.bar(categories, amounts, orientation="horizontal", color="red")
    plt.title("Spending by Category")
    plt.show()
    console.print()


# ---------------------------------------------
# FEATURE 6 - Import CSV
# ---------------------------------------------

def import_csv() -> None:
    """Import transactions from an external CSV file into the main data file.

    The source file must have the same column headers as the internal format:
        date, type, category, description, amount

    Rows that are missing required fields or contain an invalid date, type or
    amount are skipped and reported to the user so the rest of the import can
    continue. Nothing is written until the whole file has been read.
    """
    console.print(Panel("[bold yellow]Import CSV[/bold yellow]", expand=False))
    console.print(
        "\n[dim]The file must have these columns (with a header row):[/dim]"
        "\n  date, type, category, description, amount\n"
    )

    source_path = Prompt.ask("Enter the full path to the CSV file you want to import")

    # Validate that the file actually exists
    if not os.path.exists(source_path):
        console.print(f"[red]File not found: {escape(source_path)}[/red]\n")
        return

    # Importing the ledger into itself would only duplicate every row
    if os.path.exists(DATA_FILE) and os.path.samefile(source_path, DATA_FILE):
        console.print("[red]That is the tracker's own data file; its transactions are already loaded.[/red]\n")
        return

    try:
        records, problems = read_transactions(source_path)
    except LedgerError as e:
        console.print(f"[red]{escape(str(e))}[/red]\n")
        return
    except OSError as e:
        console.print(f"[red]Could not read file: {escape(str(e))}[/red]\n")
        return

    for problem in problems:
        console.print(f"[yellow]{escape(problem)}[/yellow]")

    # One write for the whole import, rather than reopening the file per row
    if records:
        try:
            save_transactions(records)
        except OSError as e:
            console.print(f"[red]Could not save the imported rows: {escape(str(e))}[/red]\n")
            return

    console.print(f"\n[green]Import complete: {len(records)} row(s) added, {len(problems)} row(s) skipped.[/green]\n")


# ---------------------------------------------
# FEATURE 7 - Export CSV
# ---------------------------------------------

def export_csv() -> None:
    """Export all current transactions to a CSV file chosen by the user.

    The exported file uses the same column format as the internal data file,
    so it can be re-imported later or opened in a spreadsheet application.
    """
    console.print(Panel("[bold yellow]Export CSV[/bold yellow]", expand=False))

    transactions = load_transactions()

    if not transactions:
        console.print("[yellow]No transactions to export.[/yellow]\n")
        return

    # Ask where to save the exported file
    default_name = f"budget_export_{datetime.today().strftime('%Y%m%d')}.csv"
    dest_path = Prompt.ask("Enter filename or full path for the export", default=default_name)

    # Warn if the file already exists and ask for confirmation before overwriting
    if os.path.exists(dest_path):
        if not Confirm.ask(f"[yellow]{escape(dest_path)} already exists. Overwrite?[/yellow]"):
            console.print("[dim]Export cancelled.[/dim]\n")
            return

    try:
        with open(dest_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            for t in sorted(transactions, key=lambda x: x["date"]):
                writer.writerow(t)

        console.print(f"\n[green]Exported {len(transactions)} transaction(s) to: {escape(dest_path)}[/green]\n")

    except OSError as e:
        console.print(f"[red]Could not write file: {escape(str(e))}[/red]\n")


# ---------------------------------------------
# FEATURE 6 - Import / Export submenu
# ---------------------------------------------

def import_export_csv() -> None:
    """Show a submenu letting the user choose between importing or exporting."""
    console.print(Panel("[bold]Import / Export Data[/bold]", expand=False))
    console.print("\n  [cyan]1.[/cyan] Import CSV")
    console.print("  [cyan]2.[/cyan] Export CSV")
    console.print("  [cyan]3.[/cyan] Back to main menu\n")

    sub = Prompt.ask("Choose an option [cyan][1/2/3][/cyan]", choices=["1", "2", "3"], show_choices=False)
    console.print()

    if sub == "1":
        import_csv()
    elif sub == "2":
        export_csv()
    # option 3 simply returns to the main loop


# ---------------------------------------------
# MAIN MENU
# ---------------------------------------------

def print_header() -> None:
    """Display the app banner."""
    console.print(Panel(
        "[bold cyan]Personal Budget Tracker[/bold cyan]\n"
        "[dim]Track income and expenses | View charts | Stay in control[/dim]",
        box=box.DOUBLE_EDGE,
        expand=False,
    ))


def main() -> None:
    """Main application loop - displays menu and routes user choices."""
    while True:
        print_header()

        try:
            transactions, problems = load_ledger()
        except (LedgerError, OSError) as e:
            report_unreadable_ledger(e)
            return

        # Show current balance as a quick summary
        balance      = get_running_balance(transactions)
        bal_colour   = "green" if balance >= 0 else "red"
        console.print(f"  Current Balance: [{bal_colour}]GBP {balance:.2f}[/{bal_colour}]\n")
        if problems:
            console.print(f"  [yellow]{len(problems)} row(s) in {os.path.basename(DATA_FILE)} could not be "
                          f"read and are left out of every total. {escape(problems[0])}[/yellow]\n")

        # Menu options
        console.print("[bold]Menu:[/bold]")
        console.print("  [cyan]1.[/cyan] Add Transaction")
        console.print("  [cyan]2.[/cyan] View All Transactions")
        console.print("  [cyan]3.[/cyan] Monthly Summary")
        console.print("  [cyan]4.[/cyan] Income vs Expenses Chart")
        console.print("  [cyan]5.[/cyan] Spending Breakdown by Category")
        console.print("  [cyan]6.[/cyan] Import / Export Data")
        console.print("  [cyan]7.[/cyan] Clear Screen")
        console.print("  [cyan]8.[/cyan] Exit\n")

        choice = Prompt.ask("Choose an option [cyan][1/2/3/4/5/6/7/8][/cyan]", choices=["1","2","3","4","5","6","7","8"], show_choices=False)
        console.print()

        try:
            if choice == "1":
                add_transaction()
            elif choice == "2":
                view_transactions()
            elif choice == "3":
                monthly_summary()
            elif choice == "4":
                show_chart()
            elif choice == "5":
                category_breakdown()
            elif choice == "6":
                import_export_csv()
            elif choice == "7":
                console.clear()
            elif choice == "8":
                if Confirm.ask("Are you sure you want to exit?"):
                    console.print("[bold green]Goodbye! Keep budgeting![/bold green]")
                    break
        except LedgerError as e:
            # The data file was changed by something else while the tracker ran
            report_unreadable_ledger(e)
            return


def report_unreadable_ledger(error: Exception) -> None:
    """Explain why the data file cannot be used. The file is not modified."""
    console.print(f"[red]Cannot read {escape(DATA_FILE)}: {escape(str(error))}[/red]")
    console.print("[red]The file has not been changed. Fix or move it, then start the tracker again.[/red]")


# ---------------------------------------------
# ENTRY POINT
# ---------------------------------------------
if __name__ == "__main__":
    main()