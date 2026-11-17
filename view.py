"""Print the Excel report in the terminal, using pandas.

Usage:
    python view.py                                  # newest report in out/
    python view.py out/sales_report_2026-11-08.xlsx
"""
import sys
from pathlib import Path

import pandas as pd

import config

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", None)


def show(path):
    print(path, "\n")
    summary = pd.read_excel(path, sheet_name="Summary", header=2).dropna(how="all").convert_dtypes()
    summary["Last post"] = summary["Last post"].fillna("")
    issues = pd.read_excel(path, sheet_name="Issues")
    print(summary.to_string(index=False, na_rep=""))
    print("\nIssues:")
    print(issues.to_string(index=False) if len(issues) else "  none")


def main():
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        files = sorted(Path(config.OUT).glob("*.xlsx"), key=lambda p: p.stat().st_mtime)
        if not files:
            sys.exit(f"No .xlsx files in '{config.OUT}/'. Run report.py first.")
        path = files[-1]
    show(path)


if __name__ == "__main__":
    main()
