#!/usr/bin/env python3

import argparse
import csv
import datetime as dt
import os
import sqlite3
import sys
from typing import Iterable, Optional, Tuple

DB_PATH = os.environ.get("EXPENSE_LOGGER_DB", os.path.expanduser("~/.expense_logger.sqlite3"))

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    note TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
"""


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    return conn


def parse_amount_to_cents(amount_str: str) -> int:
    try:
        # Support comma, currency symbols, spaces
        cleaned = amount_str.strip().replace(",", "").replace("$", "")
        if cleaned.startswith("+"):
            cleaned = cleaned[1:]
        amount = round(float(cleaned) * 100)
        return int(amount)
    except Exception:
        raise argparse.ArgumentTypeError(f"Invalid amount: {amount_str}")


def cents_to_str(amount_cents: int) -> str:
    sign = "-" if amount_cents < 0 else ""
    abs_cents = abs(amount_cents)
    dollars = abs_cents // 100
    cents = abs_cents % 100
    return f"{sign}${dollars}.{cents:02d}"


def parse_date(date_str: Optional[str]) -> str:
    if not date_str or date_str.lower() in {"today", "now"}:
        return dt.date.today().isoformat()
    if date_str.lower() == "yesterday":
        return (dt.date.today() - dt.timedelta(days=1)).isoformat()
    # Accept YYYY-MM-DD or relative like -N (days ago)
    if date_str.startswith("-") and date_str[1:].isdigit():
        days = int(date_str)
        return (dt.date.today() + dt.timedelta(days=days)).isoformat()
    try:
        return dt.date.fromisoformat(date_str).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError("Date must be YYYY-MM-DD, 'today', 'yesterday', or -N")


def add_expense(conn: sqlite3.Connection, date: str, category: str, amount_cents: int, note: str) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO expenses(date, category, amount_cents, note) VALUES (?, ?, ?, ?)",
            (date, category, amount_cents, note),
        )
    return int(cur.lastrowid)


def list_expenses(
    conn: sqlite3.Connection,
    start_date: Optional[str],
    end_date: Optional[str],
    category: Optional[str],
    limit: Optional[int],
) -> Iterable[sqlite3.Row]:
    clauses = []
    params: Tuple = tuple()
    if start_date:
        clauses.append("date >= ?")
        params += (start_date,)
    if end_date:
        clauses.append("date <= ?")
        params += (end_date,)
    if category:
        clauses.append("category = ?")
        params += (category,)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    limit_sql = f" LIMIT {int(limit)}" if limit else ""
    sql = f"SELECT id, date, category, amount_cents, note FROM expenses{where} ORDER BY date DESC, id DESC{limit_sql}"
    return conn.execute(sql, params)


def summarize_expenses(
    conn: sqlite3.Connection,
    start_date: Optional[str],
    end_date: Optional[str],
    by: str,
) -> Iterable[sqlite3.Row]:
    if by not in {"day", "month", "category"}:
        raise ValueError("by must be one of: day, month, category")
    clauses = []
    params: Tuple = tuple()
    if start_date:
        clauses.append("date >= ?")
        params += (start_date,)
    if end_date:
        clauses.append("date <= ?")
        params += (end_date,)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

    if by == "day":
        group_expr = "date"
    elif by == "month":
        group_expr = "substr(date, 1, 7)"  # YYYY-MM
    else:
        group_expr = "category"

    sql = f"""
        SELECT {group_expr} AS group_key, SUM(amount_cents) AS total_cents, COUNT(*) AS num
        FROM expenses
        {where}
        GROUP BY {group_expr}
        ORDER BY {group_expr} ASC
    """
    return conn.execute(sql, params)


def export_csv(
    conn: sqlite3.Connection,
    output_path: str,
    start_date: Optional[str],
    end_date: Optional[str],
    category: Optional[str],
) -> None:
    rows = list(list_expenses(conn, start_date, end_date, category, limit=None))
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "date", "category", "amount", "note"])
        for r in rows:
            writer.writerow([r["id"], r["date"], r["category"], cents_to_str(r["amount_cents"]), r["note"]])


def delete_expense(conn: sqlite3.Connection, expense_id: int) -> int:
    with conn:
        cur = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        return cur.rowcount


def edit_expense(
    conn: sqlite3.Connection,
    expense_id: int,
    date: Optional[str],
    category: Optional[str],
    amount_cents: Optional[int],
    note: Optional[str],
) -> int:
    sets = []
    params: Tuple = tuple()
    if date:
        sets.append("date = ?")
        params += (date,)
    if category:
        sets.append("category = ?")
        params += (category,)
    if amount_cents is not None:
        sets.append("amount_cents = ?")
        params += (amount_cents,)
    if note is not None:
        sets.append("note = ?")
        params += (note,)
    if not sets:
        return 0
    params += (expense_id,)
    sql = f"UPDATE expenses SET {', '.join(sets)} WHERE id = ?"
    with conn:
        cur = conn.execute(sql, params)
        return cur.rowcount


def print_rows(rows: Iterable[sqlite3.Row]) -> None:
    # Simple aligned printing
    rows = list(rows)
    if not rows:
        print("No results")
        return
    # Determine widths
    headers = ["id", "date", "category", "amount", "note"]
    data = [
        [str(r["id"]), r["date"], r["category"], cents_to_str(r["amount_cents"]), r["note"]]
        for r in rows
    ]
    widths = [max(len(h), *(len(row[i]) for row in data)) for i, h in enumerate(headers)]
    fmt = "  ".join([f"{{:<{w}}}" for w in widths])
    print(fmt.format(*headers))
    print("  ".join(["-" * w for w in widths]))
    for row in data:
        print(fmt.format(*row))


def print_summary(rows: Iterable[sqlite3.Row]) -> None:
    rows = list(rows)
    if not rows:
        print("No results")
        return
    headers = ["group", "total", "count"]
    data = [
        [str(r["group_key"]), cents_to_str(r["total_cents"]), str(r["num"]) ]
        for r in rows
    ]
    widths = [max(len(h), *(len(row[i]) for row in data)) for i, h in enumerate(headers)]
    fmt = "  ".join([f"{{:<{w}}}" for w in widths])
    print(fmt.format(*headers))
    print("  ".join(["-" * w for w in widths]))
    for row in data:
        print(fmt.format(*row))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="expense-logger",
        description="Daily expense logger with SQLite storage",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--db", default=DB_PATH, help="Path to SQLite database file")

    sub = p.add_subparsers(dest="cmd", required=True)

    # add
    ap = sub.add_parser("add", help="Add an expense")
    ap.add_argument("amount", type=parse_amount_to_cents, help="Amount, e.g. 12.34")
    ap.add_argument("category", help="Category, e.g. food, transport")
    ap.add_argument("note", nargs=argparse.REMAINDER, help="Optional note after --")
    ap.add_argument("--date", "-d", type=parse_date, default=parse_date("today"), help="Date (YYYY-MM-DD or today/yesterday/-N)")

    # list
    lp = sub.add_parser("list", help="List expenses")
    lp.add_argument("--start", type=parse_date, help="Start date inclusive")
    lp.add_argument("--end", type=parse_date, help="End date inclusive")
    lp.add_argument("--category", help="Filter by category")
    lp.add_argument("--limit", type=int, help="Limit number of rows")

    # summary
    sp = sub.add_parser("summary", help="Summarize expenses")
    sp.add_argument("--start", type=parse_date, help="Start date inclusive")
    sp.add_argument("--end", type=parse_date, help="End date inclusive")
    sp.add_argument("--by", choices=["day", "month", "category"], default="month")

    # export
    ep = sub.add_parser("export", help="Export to CSV")
    ep.add_argument("output", help="Output CSV path")
    ep.add_argument("--start", type=parse_date, help="Start date inclusive")
    ep.add_argument("--end", type=parse_date, help="End date inclusive")
    ep.add_argument("--category", help="Filter by category")

    # delete
    dp = sub.add_parser("delete", help="Delete an expense by ID")
    dp.add_argument("id", type=int)

    # edit
    edp = sub.add_parser("edit", help="Edit an expense by ID")
    edp.add_argument("id", type=int)
    edp.add_argument("--date", type=parse_date)
    edp.add_argument("--category")
    edp.add_argument("--amount", type=parse_amount_to_cents)
    edp.add_argument("--note")

    return p


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    conn = get_connection(args.db)

    if args.cmd == "add":
        note_text = " ".join(args.note) if args.note else ""
        new_id = add_expense(conn, args.date, args.category, args.amount, note_text)
        print(f"Added expense #{new_id}: {cents_to_str(args.amount)} {args.category} on {args.date}")
        return 0

    if args.cmd == "list":
        rows = list_expenses(conn, args.start, args.end, args.category, args.limit)
        print_rows(rows)
        return 0

    if args.cmd == "summary":
        rows = summarize_expenses(conn, args.start, args.end, args.by)
        print_summary(rows)
        return 0

    if args.cmd == "export":
        export_csv(conn, args.output, args.start, args.end, args.category)
        print(f"Exported to {args.output}")
        return 0

    if args.cmd == "delete":
        n = delete_expense(conn, args.id)
        if n:
            print(f"Deleted {n} row(s)")
            return 0
        else:
            print("No such expense id", file=sys.stderr)
            return 1

    if args.cmd == "edit":
        n = edit_expense(conn, args.id, args.date, args.category, args.amount, args.note)
        if n:
            print(f"Updated {n} row(s)")
            return 0
        else:
            print("Nothing to update or no such id", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())