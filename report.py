"""Step 2: read the cleaned CSV from preprocess.py and write the daily Excel report.

Usage:
    uv run report.py                       # processed/messages_<today>.csv
    uv run report.py --date 2026-11-08
    uv run report.py --all                 # every CSV in processed/

Each rep posts ONE end-of-day (EOD) message, one product per line, "number - product":
    45 - mobil kontrat
    2 - spbx
The dash is optional ("45 mobil kontrat" works too). If a rep posts more than one
report in a day, the latest one replaces the earlier ones (noted on the Issues sheet).
"""
import argparse
import csv
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import config

# "45 - mobil kontrat", "45 mobil kontrat", "+2 upcell"  (separator can be - – — : =)
SEGMENT = re.compile(r"^\+?(?P<n>\d+)\s*(?P<sep>[-–—:=])?\s*(?P<name>[^\d\s].*)$")
# The same written the wrong way round: "mobil kontrat: 45", "up 2". Not counted, always flagged.
REVERSED = re.compile(r"^(?P<name>[^\d\s].*?)\s*[-–—:=]?\s*\+?(?P<n>\d+)$")
FOLD = str.maketrans("ıüöşçğâîû", "iuoscgaiu")


def product_key(name):
    """Comparable form of a product name: lowercase, Turkish letters folded, no emoji/punctuation."""
    s = name.replace("I", "ı").replace("İ", "i").lower().translate(FOLD)
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


ALIASES = {}
for canonical, others in config.PRODUCTS.items():
    for name in [canonical, *others]:
        ALIASES[product_key(name)] = canonical
IGNORED = {product_key(n) for n in config.IGNORE}
PRODUCT_NAMES = list(config.PRODUCTS)


def parse_report(text):
    """Return ({product: count}, [problems]) for one message. Pure chatter gives ({}, [])."""
    counts, problems, maybe, seen = {}, [], [], set()
    for chunk in re.split(r"[\n,;]", text):
        chunk = re.sub(r"^[-•*]\s+", "", chunk.strip())
        if not chunk:
            continue
        match = SEGMENT.match(chunk)
        if not match:
            reversed_ = REVERSED.match(chunk)
            if reversed_ and product_key(reversed_["name"]) in ALIASES:
                # flagged even if nothing else in the message counts, so a whole report
                # written product-first can't vanish without a note on the Issues sheet
                problems.append(f"Number after the product, not counted: '{chunk}' "
                                f"(write it as '{reversed_['n']} - {reversed_['name']}')")
            else:
                maybe.append(f"Line not understood: '{chunk}'")
            continue
        key = product_key(match["name"])
        if key in IGNORED:
            continue
        product = ALIASES.get(key)
        if product is None:
            note = f"Unrecognised product, not counted: '{chunk}'"
            # "N - something" is clearly meant as a report line; "N something" may be chatter
            (problems if match["sep"] else maybe).append(note)
            continue
        if key in seen:    # the exact same line twice is probably a mistake: flag it
            problems.append(f"'{key}' listed twice in one message; numbers added together")
        seen.add(key)
        # different spellings of one product (e.g. "spbx" and "spbx up") are simply added up
        counts[product] = counts.get(product, 0) + int(match["n"])
    if counts:      # it is a report, so also point out the lines we could not read
        problems += maybe
    return counts, problems


def load_messages(path):
    with Path(path).open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            yield (datetime.strptime(row["time"], "%H:%M:%S").time(), row["sender"], row["text"])


def build_report(messages):
    latest, posts, issues = {}, {}, []
    for time, sender, text in sorted(messages, key=lambda m: m[0]):
        counts, problems = parse_report(text)
        stamp = time.strftime("%H:%M")
        for p in problems:
            issues.append((sender, stamp, p))
        if counts:
            latest[sender] = (stamp, counts)    # later messages overwrite earlier ones
            posts[sender] = posts.get(sender, 0) + 1
    for rep, n in posts.items():
        if n > 1:
            issues.append((rep, latest[rep][0], f"Posted {n} reports; latest one used"))
    if config.ROSTER:
        for rep in config.ROSTER:
            if rep not in latest:
                issues.append((rep, "", "No report received"))
        for rep in latest:
            if rep not in config.ROSTER:
                issues.append((rep, latest[rep][0], "Name not in ROSTER (check spelling)"))
    return latest, issues


def write_excel(latest, issues, day, out_dir):
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="305496")

    ws["A1"] = f"Daily sales report - {day.isoformat()}"
    ws["A1"].font = Font(bold=True, size=14)
    headers = ["Rep", *PRODUCT_NAMES, "Last post"]
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row=3, column=col, value=text)
        cell.font, cell.fill = head_font, head_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    row = 3
    for rep in sorted(latest, key=str.lower):
        row += 1
        stamp, counts = latest[rep]
        ws.cell(row=row, column=1, value=rep)
        for col, product in enumerate(PRODUCT_NAMES, start=2):
            ws.cell(row=row, column=col, value=counts.get(product, 0))
        ws.cell(row=row, column=len(headers), value=stamp)

    total_row = row + 2
    ws.cell(row=total_row, column=1, value="TOTAL").font = Font(bold=True)
    for col, product in enumerate(PRODUCT_NAMES, start=2):
        total = sum(counts.get(product, 0) for _, counts in latest.values())
        ws.cell(row=total_row, column=col, value=total).font = Font(bold=True)   # plain number, not a formula

    ws.column_dimensions["A"].width = 24
    for col in range(2, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 15
    ws.freeze_panes = "B4"

    wi = wb.create_sheet("Issues")
    for col, text in enumerate(["Rep", "Time", "Note"], start=1):
        cell = wi.cell(row=1, column=col, value=text)
        cell.font, cell.fill = head_font, head_fill
    for r, (rep, stamp, note) in enumerate(issues, start=2):
        wi.cell(row=r, column=1, value=rep)
        wi.cell(row=r, column=2, value=stamp)
        wi.cell(row=r, column=3, value=note)
    wi.column_dimensions["A"].width = 24
    wi.column_dimensions["B"].width = 8
    wi.column_dimensions["C"].width = 70

    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)
    path = out_dir / f"sales_report_{day.isoformat()}.xlsx"
    wb.save(path)
    return path


def run(day):
    """Build the Excel report for one day from its cleaned CSV. Returns the .xlsx path or None."""
    path = Path(config.PROCESSED) / f"messages_{day.isoformat()}.csv"
    if not path.exists():
        print(f"{path} not found. Run preprocess.py first (same --date).")
        return None
    latest, issues = build_report(list(load_messages(path)))
    out = write_excel(latest, issues, day, config.OUT)
    print(f"{day}: {len(latest)} rep(s) reported, {len(issues)} issue(s) -> {out}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="report day as YYYY-MM-DD; default: today")
    ap.add_argument("--all", action="store_true", help="one report per CSV in processed/")
    args = ap.parse_args()
    if args.all:
        days = sorted(date.fromisoformat(p.stem.removeprefix("messages_"))
                      for p in Path(config.PROCESSED).glob("messages_*.csv"))
    else:
        days = [date.fromisoformat(args.date) if args.date else date.today()]
    results = [run(d) for d in days]
    if not any(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
