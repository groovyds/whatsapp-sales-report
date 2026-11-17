"""One command for the whole daily run: export -> cleaned CSV -> Excel report -> printout.

Usage (after putting today's WhatsApp export in inbox/):
    uv run daily.py                        # today, newest .txt in inbox/
    uv run daily.py --date 2026-11-08      # another day
    uv run daily.py --all                  # every day in the export
    uv run daily.py inbox/chat.txt         # a specific export file

The report covers the whole calendar day of the chosen date (start of day to the moment of
the export), so run it after EOD. The .xlsx lands in out/; attach it to your email to the TL.
"""
import argparse
import sys
from datetime import date

import preprocess
import report
import view


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="raw .txt export; default: newest in inbox/")
    ap.add_argument("--date", help="report day as YYYY-MM-DD; default: today")
    ap.add_argument("--all", action="store_true", help="every day in the export")
    args = ap.parse_args()

    path = preprocess.resolve_path(args.file)
    day = None if args.all else (date.fromisoformat(args.date) if args.date else date.today())
    print(f"Export: {path}\n")
    days = preprocess.run(path, day)
    if not days:
        sys.exit("Nothing to report. Check that the export includes the day you want.")
    print()
    outputs = [report.run(d) for d in days]
    if day is not None:                  # single day: print the report so you can check it
        print()
        view.show(outputs[0])


if __name__ == "__main__":
    main()
