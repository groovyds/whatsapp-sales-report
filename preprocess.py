"""Step 1: turn a raw WhatsApp export into a clean CSV per day.

Usage:
    uv run preprocess.py                       # newest .txt in inbox/, today
    uv run preprocess.py --date 2026-11-08
    uv run preprocess.py --all                 # every day in the export
    uv run preprocess.py inbox/chat.txt --date 2026-11-08

Output: processed/messages_YYYY-MM-DD.csv   (columns: date, time, sender, text)
What it does: splits the export into messages (a message can span several lines),
removes invisible characters, lowercases the message text (Turkish-aware), renames "You"
to SELF_NAME, drops noise (link-only posts, deleted/omitted media) and keeps the chosen day.
"""
import argparse
import csv
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

import config

# WhatsApp inserts invisible direction marks and narrow no-break spaces; remove them.
INVISIBLE = dict.fromkeys(map(ord, "‎‏‪‫‬‭‮⁦⁧⁨⁩﻿"))
SPACES = str.maketrans({" ": " ", " ": " "})

# Matches these styles:
#   [11/8/26, 4:17:37 PM] Ali: text        (Mac, English settings)
#   [27.08.2026, 10:35:25] Ali: text       (Mac, Turkish settings)
#   08/11/2026, 18:05 - Ali: text          (Android)
HEADER = re.compile(
    r"^\[?(?P<date>\d{1,4}[./-]\d{1,2}[./-]\d{1,4}),?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\s?[APap]\.?[Mm]\.?)?)\]?"
    r"\s*(?:-\s+)?(?P<sender>[^:]{1,60}?):\s?(?P<text>.*)$"
)
URL_ONLY = re.compile(r"(?:https?://|www\.)\S+")
EDITED = re.compile(r"\s*<this message was edited>")
NOISE = re.compile(
    r"<?(?:image|video|audio|sticker|gif|document|media|contact card|poll)? ?omitted>?"
    r"|this message was deleted\.?|you deleted this message\.?|<attached: .*>"
)


def parse_date(s):
    parts = re.split(r"[./-]", s)
    a, b, c = (int(p) for p in parts)
    if len(parts[0]) == 4:
        y, m, d = a, b, c
    else:
        y = c + 2000 if c < 100 else c
        day_first = "." in s or config.DATE_ORDER == "DMY"   # dotted dates are always day first
        d, m = (a, b) if day_first else (b, a)
    return date(y, m, d)


def parse_time(s):
    s = s.strip().upper().replace(".", "")
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p", "%I:%M:%S%p", "%I:%M%p"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            pass
    raise ValueError(s)


def read_messages(text):
    """Split the raw export text into messages: {date, time, sender, lines}."""
    messages, current = [], None
    for raw in text.splitlines():
        line = raw.translate(INVISIBLE).translate(SPACES)
        header = HEADER.match(line)
        stamp = None
        if header:
            try:
                stamp = (parse_date(header["date"]), parse_time(header["time"]))
            except ValueError:
                stamp = None
        if stamp:
            current = {"date": stamp[0], "time": stamp[1],
                       "sender": header["sender"].strip(" *"), "lines": [header["text"]]}
            messages.append(current)
        elif current is not None:       # continuation line (system lines before the first message are skipped)
            current["lines"].append(line)
    return messages


def turkish_lower(text):
    """Lowercase with Turkish rules: I -> ı, İ -> i."""
    return unicodedata.normalize("NFC", text).replace("I", "ı").replace("İ", "i").lower()


def clean_text(lines):
    """Lowercase, trim, drop empty lines. Returns '' for messages that are just noise."""
    text = EDITED.sub("", turkish_lower("\n".join(lines)))
    kept = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not kept:
        return ""
    if all(URL_ONLY.fullmatch(ln) for ln in kept):
        return ""
    if all(NOISE.fullmatch(ln) for ln in kept):
        return ""
    return "\n".join(kept)


def newest_export():
    files = [p for p in Path(config.INBOX).glob("*") if p.suffix.lower() == ".txt"]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def rows_for_day(messages, day):
    rows = []
    for msg in sorted(messages, key=lambda m: (m["date"], m["time"])):   # stable: ties keep file order
        if msg["date"] != day:
            continue
        text = clean_text(msg["lines"])
        if not text:
            continue
        sender = msg["sender"]
        if sender.lower() == "you" and config.SELF_NAME:
            sender = config.SELF_NAME
        rows.append([day.isoformat(), msg["time"].strftime("%H:%M:%S"), sender, text])
    return rows


def write_csv(rows, day):
    out_dir = Path(config.PROCESSED)
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"messages_{day.isoformat()}.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "time", "sender", "text"])
        writer.writerows(rows)
    return out


def run(path, day=None):
    """Write one CSV per day (all days if day is None). Returns the days written."""
    messages = read_messages(Path(path).read_text(encoding="utf-8-sig"))
    if not messages:
        sys.exit(f"Could not find any messages in {path}. Is the line format different?")
    dates = sorted({m["date"] for m in messages})
    days = dates if day is None else [day]
    written = []
    for d in days:
        rows = rows_for_day(messages, d)
        if not rows:       # never overwrite a good CSV with an empty one
            print(f"No messages dated {d} in {Path(path).name} (it covers {dates[0]} to {dates[-1]}).")
            continue
        out = write_csv(rows, d)
        print(f"{Path(path).name}: {len(rows)} message(s) on {d} -> {out}")
        written.append(d)
    return written


def resolve_path(arg):
    path = Path(arg) if arg else newest_export()
    if path is None or not path.exists():
        sys.exit(f"No export file found. Put the .txt export in '{config.INBOX}/'.")
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="raw .txt export; default: newest in inbox/")
    ap.add_argument("--date", help="day to keep as YYYY-MM-DD; default: today")
    ap.add_argument("--all", action="store_true", help="write a CSV for every day in the export")
    args = ap.parse_args()
    day = None if args.all else (date.fromisoformat(args.date) if args.date else date.today())
    if not run(resolve_path(args.file), day):
        sys.exit(1)


if __name__ == "__main__":
    main()
