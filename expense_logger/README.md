# Expense Logger

A simple Python CLI to log daily expenses in a local SQLite database.

## Quickstart

- Run help:

```
python3 expense_logger.py -h
```

- Add an expense:

```
python3 expense_logger.py add 12.50 food -- Lunch burrito
```

- List recent expenses:

```
python3 expense_logger.py list --limit 10
```

- Summarize by month between dates:

```
python3 expense_logger.py summary --start 2025-01-01 --end 2025-12-31 --by month
```

- Export to CSV:

```
python3 expense_logger.py export expenses.csv --start 2025-01-01 --end 2025-12-31
```

- Edit an expense:

```
python3 expense_logger.py edit 3 --amount 9.99 --note "Corrected amount"
```

- Delete an expense:

```
python3 expense_logger.py delete 3
```

By default, the database is stored at `~/.expense_logger.sqlite3`. Override with `--db` or env var `EXPENSE_LOGGER_DB`.