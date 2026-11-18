"""Step 0: export one day of the sales group straight from the WhatsApp Mac app. No phone needed.

Usage:
    uv run fetch_chat.py                    # today -> inbox/chat_YYYY-MM-DD.txt
    uv run fetch_chat.py --date 2026-11-08  # another day (only what the Mac app has synced)
    uv run fetch_chat.py --list             # group names, to fill in CHAT_NAME in config_local.py
    uv run fetch_chat.py --learn-names ~/Downloads/_chat.txt   # one-time: name reps not in your contacts

It reads the Mac app's local database read-only and never touches WhatsApp's servers.
The output uses the same line format as a manual export, so daily.py reads it unchanged.
The WhatsApp Mac app must be linked and have synced today's messages; open it before EOD.
"""
import argparse
import os
import sqlite3
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import config

# Where to read the databases. daily.sh sets WA_DATA_DIR to the copy made by tools/wa-snapshot,
# so this script never touches WhatsApp's own folder (see tools/README.md). Run by hand without
# it, it reads WhatsApp's folder directly and macOS may ask for permission.
DATA = Path(os.environ.get("WA_DATA_DIR") or
            Path.home() / "Library/Group Containers/group.net.whatsapp.WhatsApp.shared")
APPLE_EPOCH = 978307200          # the app stores times as seconds since 2001-01-01 UTC
TEXT_MESSAGE = 0                 # other types are media, stickers, system notices


def connect():
    db = DATA / "ChatStorage.sqlite"
    if not db.exists():
        sys.exit(f"WhatsApp data not found at {db}. Is the WhatsApp Mac app installed and linked?")
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        for name in ("ContactsV2", "LID"):
            con.execute(f"ATTACH 'file:{DATA / name}.sqlite?mode=ro' AS {name}")
        con.execute("SELECT 1 FROM ZWAMESSAGE LIMIT 1")
    except sqlite3.Error as e:
        sys.exit(f"Could not read WhatsApp data ({e}).\n"
                 "If this runs on a schedule, see tools/README.md.")
    return con


def list_groups(con):
    rows = con.execute("SELECT ZPARTNERNAME, ZLASTMESSAGEDATE FROM ZWACHATSESSION "
                       "WHERE ZSESSIONTYPE = 1 AND ZPARTNERNAME IS NOT NULL "
                       "ORDER BY ZLASTMESSAGEDATE DESC LIMIT 30").fetchall()
    for name, last in rows:
        when = datetime.fromtimestamp(last + APPLE_EPOCH).strftime("%Y-%m-%d %H:%M") if last else "-"
        print(f"{when}  {name}")


def find_chat(con, name):
    if not name:
        sys.exit("Set CHAT_NAME in config_local.py (copy config_local.example.py). "
                 "See group names with: uv run fetch_chat.py --list")
    rows = con.execute("SELECT Z_PK FROM ZWACHATSESSION WHERE ZSESSIONTYPE = 1 AND ZPARTNERNAME = ?",
                       (name,)).fetchall()
    if len(rows) != 1:
        problem = "No group" if not rows else f"{len(rows)} groups"
        sys.exit(f"{problem} named {name!r}. Check CHAT_NAME against: uv run fetch_chat.py --list")
    return rows[0][0]


def sender_name(con, jid, cache):
    """Your contact name for a member, else their WhatsApp profile name, else None."""
    if jid in cache:
        return cache[jid]
    name = config.SENDER_NAMES.get(jid)
    if not name:
        row = con.execute(
            "SELECT ZFULLNAME FROM ContactsV2.ZWAADDRESSBOOKCONTACT WHERE ZFULLNAME IS NOT NULL AND "
            "(ZLID = ?1 OR ZWHATSAPPID = ?1 OR ZWHATSAPPID IN "
            " (SELECT ZPHONENUMBER || '@s.whatsapp.net' FROM LID.ZWAPHONENUMBERLIDPAIR WHERE ZLID = ?1)) "
            "LIMIT 1", (jid,)).fetchone()
        name = row[0] if row else None
    if not name:
        row = con.execute("SELECT ZPUSHNAME FROM ZWAPROFILEPUSHNAME WHERE ZJID = ? AND ZPUSHNAME <> ''",
                          (jid,)).fetchone()
        name = f"~ {row[0]}" if row else None
    cache[jid] = name
    return name


def safe_name(name):
    """A sender name the export line format can carry: preprocess.py ends the name at the
    first ':' and accepts at most 60 characters, so a longer name or one with ':' would merge
    the message into the previous one or cut it off, and that rep would silently be missing."""
    return " ".join(name.replace(":", " ").split())[:60].strip() or "Unknown"


def fetch(con, chat, day):
    """Return (lines, unknown) for one calendar day in local time."""
    start = datetime.combine(day, time()).timestamp() - APPLE_EPOCH
    end = datetime.combine(day + timedelta(days=1), time()).timestamp() - APPLE_EPOCH
    rows = con.execute(
        "SELECT m.ZMESSAGEDATE, m.ZISFROMME, g.ZMEMBERJID, m.ZFROMJID, m.ZTEXT "
        "FROM ZWAMESSAGE m LEFT JOIN ZWAGROUPMEMBER g ON g.Z_PK = m.ZGROUPMEMBER "
        "WHERE m.ZCHATSESSION = ? AND m.ZMESSAGETYPE = ? AND m.ZTEXT IS NOT NULL "
        "AND m.ZMESSAGEDATE >= ? AND m.ZMESSAGEDATE < ? ORDER BY m.ZMESSAGEDATE, m.Z_PK",
        (chat, TEXT_MESSAGE, start, end)).fetchall()
    lines, unknown, cache = [], {}, {}
    for stamp, from_me, member, from_jid, text in rows:
        if from_me:
            name = "You"                                 # preprocess renames this to SELF_NAME
        else:
            jid = member or from_jid or "unknown"
            name = sender_name(con, jid, cache)
            if not name:
                name = f"Unknown {jid.split('@')[0]}"
                unknown.setdefault(jid, text.splitlines()[0][:40])
        when = datetime.fromtimestamp(stamp + APPLE_EPOCH)
        # Year-first date: unambiguous, so DATE_ORDER does not matter for these files.
        lines.append(f"[{when:%Y-%m-%d, %H:%M:%S}] {safe_name(name)}: {text}")
    return lines, unknown


def learn_names(con, chat, export_path):
    """Match a manual phone export against the database to name unknown senders.

    The same message has the same second-precise time and text in both, so the export's
    sender name can be copied onto the database's member id. Prints SENDER_NAMES lines.
    """
    import preprocess
    from collections import Counter, defaultdict
    msgs = preprocess.read_messages(Path(export_path).read_text(encoding="utf-8-sig"))
    by_key = {(m["date"], m["time"], m["lines"][0].strip()): m["sender"] for m in msgs}
    votes = defaultdict(Counter)
    for day in sorted({m["date"] for m in msgs}):
        start = datetime.combine(day, time()).timestamp() - APPLE_EPOCH
        rows = con.execute(
            "SELECT m.ZMESSAGEDATE, g.ZMEMBERJID, m.ZTEXT FROM ZWAMESSAGE m "
            "JOIN ZWAGROUPMEMBER g ON g.Z_PK = m.ZGROUPMEMBER "
            "WHERE m.ZCHATSESSION = ? AND m.ZISFROMME = 0 AND m.ZTEXT IS NOT NULL "
            "AND m.ZMESSAGEDATE >= ? AND m.ZMESSAGEDATE < ?",
            (chat, start, start + 86400)).fetchall()
        for stamp, jid, text in rows:
            when = datetime.fromtimestamp(stamp + APPLE_EPOCH)
            first = text.translate(preprocess.INVISIBLE).translate(preprocess.SPACES).splitlines()[0].strip()
            sender = by_key.get((when.date(), when.time().replace(microsecond=0), first))
            if sender and sender.lower() != "you":
                votes[jid][sender.strip("~ ").strip()] += 1
    cache = {}
    found = {jid: c.most_common(1)[0][0] for jid, c in votes.items() if not sender_name(con, jid, cache)}
    if not found:
        print("No unnamed senders matched. Is the export from the same group, covering recent days?")
        return
    print(f"Matched {len(found)} sender(s). Paste into SENDER_NAMES in config_local.py:")
    for jid, name in found.items():
        print(f'    "{jid}": "{name}",')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="day as YYYY-MM-DD; default: today")
    ap.add_argument("--list", action="store_true", help="show group names and exit")
    ap.add_argument("--learn-names", metavar="EXPORT.txt",
                    help="one-time: name unknown senders from a manual phone export of the group")
    args = ap.parse_args()

    con = connect()
    if args.list:
        list_groups(con)
        return
    if args.learn_names:
        learn_names(con, find_chat(con, config.CHAT_NAME), args.learn_names)
        return
    day = date.fromisoformat(args.date) if args.date else date.today()
    lines, unknown = fetch(con, find_chat(con, config.CHAT_NAME), day)
    if not lines:
        sys.exit(f"No text messages in {config.CHAT_NAME!r} on {day}. "
                 "Has the WhatsApp Mac app been opened and synced today?")

    out_dir = Path(config.INBOX)
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"chat_{day.isoformat()}.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(lines)} message(s) from {config.CHAT_NAME!r} on {day} -> {out}")
    if unknown:
        print(f"\n{len(unknown)} sender(s) have no name. Add them to SENDER_NAMES in config_local.py:")
        for jid, sample in unknown.items():
            print(f'    "{jid}": "",    # first message: {sample!r}')


if __name__ == "__main__":
    main()
