# How we got here

Progress and decisions, in order. Each entry says what was decided and **why**, so later changes
don't undo something on purpose without knowing it. Dates are when the work happened.

---

## Starting point: counting by hand

A sales team posts its numbers in a WhatsApp group through the day: `2 up`, `1 ncst`,
`1 online superbox` and so on. At the end of the day (EOD, about 18:30), someone has to add these
up per rep and per product and email the totals to the team leader (TL). Doing that by hand from
the chat is slow and error-prone.

## Early November: first parser

The first version read a WhatsApp "Export chat" `.txt` file and counted products.

**Lesson:** a handoff from an earlier session assumed one fixed line format, and that turned out
to be wrong. Real exports come in at least two header styles, depending on the phone's language
settings:

```
[11/8/26, 4:17:37 PM] Name: text        English settings: month/day/year, 12-hour clock
[27.08.2026, 10:35:25] Name: text       Turkish settings: day.month.year, 24-hour clock
```

The parser accepts both (and Android's style). A date with dots is always read day first, and
`DATE_ORDER` in `config.py` decides what a date with slashes means. Every new export gets checked
against both styles before the parsing changes.

## 2026-11-15: MVP scope decided

**One command → one Excel file; the user emails it by hand.**

- `uv run daily.py` runs three steps: `preprocess.py` (raw export → clean CSV for one day),
  `report.py` (CSV → Excel) and `view.py` (print the table).
- The report covers one calendar day, from start of day to when the run happens. It runs about
  10 minutes after EOD.
- Deliberately left out for now: a rep roster, sending email, a database. Each was extra work
  without a clear need yet.

**The message format going forward.** In the real chat, reps post each sale as it happens. The
plan is for reps to switch to **one EOD message each**, one product per line
(`number - product`). If a rep posts more than once, **the latest message replaces the earlier
ones**. That makes corrections easy: just post again. The Issues sheet lists every rep who posted
more than once, so nothing is silently dropped.

**Product mapping, agreed with the user:**
- "up / upcell / upsell" and their misspellings count as **Mobil kontrat**. There's no separate
  "UP" column.
- "online superbox / sbox / spbx" and "fiber" count as **SOL**.
- **Paycell POS** has its own column.
- "aktivite" lines are ignored on purpose.
- Matching ignores capitals, Turkish letters (ü=u, ş=s, ı=i …), emojis and punctuation, so
  "Süperbox Upsell 💞" equals "superbox upsell".

The tooling is [uv](https://docs.astral.sh/uv/) rather than pip, and tests use made-up data.

## 2026-11-16: removing the manual export

**Problem.** The WhatsApp desktop app has no "Export chat" option; only the phone apps do. Exporting
on the phone and moving the file to the Mac every day was the slowest part.

**Options considered:**
1. **Automating WhatsApp Web in Safari.** Rejected: Safari is hard to script, the web page changes
   often, and driving it automatically risks the WhatsApp account.
2. **Reading the WhatsApp Mac app's local database.** Chosen. The app keeps every message in a
   SQLite file on disk (`ChatStorage.sqlite`), so reading it is reliable, needs no browser, never
   talks to WhatsApp's servers, and changes nothing.

**Built: `fetch_chat.py`.** It finds the group by name and takes the day's text messages. It
writes them in the same line format as a phone export, with a year-first date so it's never
ambiguous. `daily.py` didn't need to change.

**Problem: rep names.** Most group members appear in the database only as anonymous ids
(`123…@lid`), not names. Only people saved in your contacts get a name.
- First fix: `SENDER_NAMES` plus `fetch_chat.py --learn-names <phone export>`, which matches the
  same message in a phone export and in the database by its exact time and text, then copies the
  name across. On a synthetic test it named 13 of 13 senders.
- What actually solved it: the user **saved the reps as phone contacts**. Those sync to the Mac
  app, and every rep now resolves automatically. `--learn-names` remains for the occasional new rep.

**Check against real data.** The same day was built two ways, from a manual phone export and from
the database. **The reports were identical**: same reps, same counts, same issues. The only
messages missing from the database version were images, stickers, deleted messages and
@mentions, none of them sales lines.

**Scheduling: `daily.sh` + launchd.** A macOS launchd job runs `daily.sh` at 18:40 every day.
launchd was chosen because it's built in and survives restarts, and if the Mac is asleep at
18:40 it runs the job on wake. Each run appends a block to `out/daily.log`, since nothing else
records what a background run did, and shows a notification when it finishes.

## 2026-11-17: making failures recoverable

**What happened.** The first real scheduled run (18:48, after the Mac woke) failed with "No text
messages … has the WhatsApp Mac app been opened and synced today?". The Mac app hadn't synced yet.

**Fix: a Retry dialog.** On failure, `daily.sh` now opens WhatsApp in the background (so it starts
syncing) and shows a dialog:
- **Retry** (or Return) runs again, and asks again if it still fails.
- **Not now** (or Escape) stops for today.
- **No answer for 4 hours** stops on its own, so a dialog left open overnight can't block the
  next day's run.

Every attempt and every answer is written to the log. `./daily.sh 2026-11-17` also builds a
specific day's report.

## 2026-11-17: macOS permission pop-ups

**Problem.** Every read of WhatsApp's data folder showed a macOS pop-up asking to "access data
from other apps". macOS gives this permission per program, not per folder, and clicking "Allow"
doesn't stick for this kind of request. The only lasting fix is **Full Disk Access** for the
program that reads.

**Options considered:**
1. **Full Disk Access for `uv`.** Rejected: uv also runs every Python package it downloads,
   including packages' install code. A bad or hijacked package would then silently get read access
   to Mail, Messages, Photos and the rest of the protected data. It removes the safety net for
   everything uv ever runs.
2. **A tiny single-purpose helper with Full Disk Access.** Chosen.

**Built: `tools/wa-snapshot`** (C, about 150 lines; see [tools/README.md](../tools/README.md)).
- It has no options. It copies exactly three WhatsApp databases (messages, contacts, id links)
  into `.wa_snapshot/` (readable only by your user), and `daily.sh` deletes the copy when the
  run ends.
- uv and Python only ever read the copy, so they never need Full Disk Access.
- macOS identifies the program by a fingerprint of its code, so a modified copy loses the access.
- It's written in C rather than as a script because macOS checks permissions per program. A script
  would be checked as `zsh` or `python`, and granting those would be as broad as granting uv.

**Bugs found in testing, before the real run.** It was tested on fake databases, so it never
touched real data or triggered pop-ups:
- **WhatsApp closed → the helper couldn't open the database.** When WhatsApp quits, SQLite merges
  its side files (`-wal`, `-shm`) into the main file and deletes them, and a read-only open then
  fails. Fix: if no `-wal` file exists, read the main file as-is ("immutable"). It's only done
  then, so unsaved changes can't be skipped.
- **The copy was unreadable too.** SQLite's backup copies the "WAL mode" setting, so Python hit
  the same error on the copy. Fix: each copy is converted to an ordinary single-file database.
- It uses SQLite's backup function, not a plain file copy, so a copy taken while WhatsApp is
  writing is still consistent. A test confirmed that a message still in the `-wal` file is
  included.

**Verified for real.** After the user gave Full Disk Access to `wa-snapshot` only, a launchd run
copied the data, produced the same 116 messages and 13 reps as the direct read, deleted the copy
and finished in seconds with no pop-up.

## 2026-11-17: published

The project went into a public GitHub repository. To keep it free of personal data:
- Chat exports, CSVs, reports and the log are ignored by git.
- The group name, the user's name and rep ids moved to `config_local.py`, which is not committed;
  `config_local.example.py` is the template.
- The launchd file became a template plus `launchd/install.sh`, with no personal folder paths.
  The template produces exactly the file that was installed.
- The compiled helper isn't committed; it's built from source.

## 2026-11-17: checks and email

Decided with the user: Mail.app sends the report automatically, but only after checks pass. A
failed check is a hard block (no "send anyway"); the Retry / Not now dialog is the only way on.
- **Blocking checks** (`checks.py`): the saved Excel file matches each rep's latest post and the
  posts add up to the TOTAL row; the chat is for the report day. (A "newest message after 18:00"
  check was tried and removed on 2026-11-18: the group can go quiet before 18:00 on a normal day.)
- **Not blocking:** unreadable lines stay warnings on the Issues sheet. The "above 100" limit is
  parked, because with no override a genuine big day could never be sent.
- **Counting rule confirmed:** one EOD post per rep, latest wins. Adding up per-sale posts was
  rejected, since reps don't reliably post every sale.
- **Re-sends** ask first (terminal y/n, or a dialog on the schedule); sends are logged in
  `out/sent_log.csv`.
- **Test mode** sends to the user only, subject marked `[TEST]`. Verified for real: a test email
  from a manual run and a full scheduled run both sent, and a stale chat was blocked (exit 3).

## Where it stands

See [Current state in the README](../README.md#current-state). In short: it works end to end every
day. The main open item is getting reps to post **one EOD message each**; until then, totals
undercount because only each rep's latest post is counted.
