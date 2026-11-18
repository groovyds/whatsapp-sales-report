"""Checks that must pass before the report is emailed. Any problem blocks the email.

Usage:
    uv run checks.py                     # today's report
    uv run checks.py --date 2026-11-16

1. Totals match: every rep's row in the saved Excel file equals their latest WhatsApp post,
   and the TOTAL row equals the sum of the rows. Catches a file that was written or added up
   wrong. (A line the parser misread is not caught here; it's listed on the Issues sheet.)
2. Chat is for the report day: the cleaned messages exist and are all dated that day.
"""
import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

import config
import report


def csv_path(day):
    return Path(config.PROCESSED) / f"messages_{day.isoformat()}.csv"


def xlsx_path(day):
    return Path(config.OUT) / f"sales_report_{day.isoformat()}.xlsx"


def read_summary(path):
    """Return ({rep: {product: n}}, {product: total} or None) from the Summary sheet."""
    ws = load_workbook(path, read_only=True, data_only=True)["Summary"]
    rows = list(ws.iter_rows(min_row=3, values_only=True))
    header = list(rows[0])
    products = header[1:header.index("Last post")]
    reps, total = {}, None
    for row in rows[1:]:
        name = row[0]
        if name is None:
            continue
        values = {p: row[i + 1] for i, p in enumerate(products)}
        if name == "TOTAL":
            total = values
        else:
            reps[name] = values
    return products, reps, total


def check_totals(day):
    """Compare the saved Excel file with the latest post of each rep. Returns problems."""
    xlsx, csv_file = xlsx_path(day), csv_path(day)
    for p in (xlsx, csv_file):
        if not p.exists():
            return [f"{p} is missing"]
    latest, _ = report.build_report(list(report.load_messages(csv_file)))
    products, reps, total = read_summary(xlsx)
    problems = []
    if products != report.PRODUCT_NAMES:
        problems.append(f"Excel columns {products} differ from the products in config.py")
    for rep in sorted(set(latest) | set(reps), key=str.lower):
        if rep not in reps:
            problems.append(f"{rep}: posted a report but has no row in the Excel file")
            continue
        if rep not in latest:
            problems.append(f"{rep}: has a row in the Excel file but no report in the chat")
            continue
        posted = latest[rep][1]
        for p in products:
            want, got = posted.get(p, 0), reps[rep].get(p)
            if got != want:
                problems.append(f"{rep}, {p}: Excel says {got}, WhatsApp post says {want}")
    if total is None:
        problems.append("Excel file has no TOTAL row")
    else:
        for p in products:
            want = sum(posted.get(p, 0) for _, posted in latest.values())
            if total.get(p) != want:
                problems.append(f"TOTAL {p}: Excel says {total.get(p)}, the posts add up to {want}")
    return problems


def check_fresh(day):
    """The chat must be for the report day. Returns problems."""
    csv_file = csv_path(day)
    if not csv_file.exists():
        return [f"{csv_file} is missing"]
    messages = list(report.load_messages(csv_file))
    if not messages:
        return [f"No messages for {day}"]
    with csv_file.open(newline="", encoding="utf-8") as f:
        dates = {row["date"] for row in csv.DictReader(f)}
    if dates != {day.isoformat()}:
        return [f"Messages are dated {sorted(dates)}, not {day}"]
    return []


def run(day):
    return check_totals(day) + check_fresh(day)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="report day as YYYY-MM-DD; default: today")
    args = ap.parse_args()
    day = date.fromisoformat(args.date) if args.date else date.today()
    problems = run(day)
    for p in problems:
        print(f"  ✗ {p}")
    if problems:
        sys.exit(3)
    print(f"All checks passed for {day}.")


if __name__ == "__main__":
    main()
