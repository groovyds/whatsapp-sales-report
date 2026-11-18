# WhatsApp Sales Report

Turns a sales team's WhatsApp group into a daily Excel report, automatically, on a Mac.

Reps post their numbers in a WhatsApp group (`2 up`, `1 ncst`, `1 online superbox` …). Every day at
18:40, this project reads the group from the WhatsApp Mac app and works out each rep's numbers per
product. It writes `out/sales_report_YYYY-MM-DD.xlsx`, checks it, and emails it to the team leader
with Mail.app.

> **Status (2026-11-17):** working end to end and running daily on one Mac. The automatic report
> matches one built from a manual WhatsApp export exactly. See [Current state](#current-state) for
> what's left, and [docs/HISTORY.md](docs/HISTORY.md) for how it got here.

## How it works

```
18:40  launchd (macOS scheduler) runs daily.sh
  │
  ├─ 1. tools/wa-snapshot     copies the WhatsApp Mac app's databases into .wa_snapshot/
  │                           (the only program with Full Disk Access; see tools/README.md)
  ├─ 2. fetch_chat.py         today's group messages → inbox/chat_YYYY-MM-DD.txt
  │                           (same line format as a WhatsApp "Export chat" file)
  ├─ 3. daily.py
  │      ├─ preprocess.py     split into messages, clean, keep today → processed/messages_YYYY-MM-DD.csv
  │      ├─ report.py         match products, total per rep, flag issues → out/sales_report_YYYY-MM-DD.xlsx
  │      └─ view.py           print the table (into out/daily.log)
  ├─ 4. send_report.py
  │      ├─ checks.py         Excel matches the posts? chat is for the report day? Any failure: no email
  │      └─ Mail.app          email with totals in the body and the .xlsx attached → out/sent_log.csv
  └─ 5. delete .wa_snapshot/, show a notification
         If anything fails: open WhatsApp and show a Retry / Not now dialog (waits up to 4 hours)
```

Everything a run prints goes to `out/daily.log`, one block per run, newest at the bottom.

### Reading the messages

- **One report per rep per day.** Each line is `number - product`, and the dash is optional:
  `45 - mobil kontrat`, `2 spbx`. If a rep posts more than once, the **latest** post replaces
  the earlier ones, and this is noted on the Issues sheet.
- **Spellings are flexible.** `config.py` maps the many ways reps write each product (`up`,
  `upcell`, `upsell` → Mobil kontrat; `online superbox`, `fiber` → SOL; …). Matching ignores
  capitals, Turkish letters, emojis and punctuation.
- **Rep names** come from your phone contacts as synced to the WhatsApp Mac app. Reps you haven't
  saved show as `Unknown <id>` until you save them or name them in `config_local.py`.

## Setup (macOS)

You need the [WhatsApp Mac app](https://www.whatsapp.com/download) linked to your phone,
[uv](https://docs.astral.sh/uv/), and Apple's command-line tools (`xcode-select --install`).

```bash
git clone https://github.com/<you>/whatsapp-sales-report.git && cd whatsapp-sales-report
uv sync
cp config_local.example.py config_local.py      # then set CHAT_NAME (and SELF_NAME)
uv run fetch_chat.py --list                     # shows your group names, to copy into CHAT_NAME
clang -O2 -Wall -o tools/wa-snapshot tools/wa_snapshot.c -lsqlite3
```

Next, give `tools/wa-snapshot` Full Disk Access (steps in [tools/README.md](tools/README.md)) and
turn on the schedule:

```bash
./launchd/install.sh
launchctl kickstart gui/$(id -u)/com.salestracker.daily     # test run now; then read out/daily.log
```

## Everyday use

| You want to… | Do this |
|---|---|
| Get today's report | Nothing: it's made, checked and emailed at 18:40, and lands in `out/` |
| Check a report without sending | `uv run checks.py --date 2026-11-17` |
| Send (or re-send) a report | `uv run send_report.py --date 2026-11-17` (asks before a re-send) |
| Go live after testing | In `config_local.py`: set `EMAIL_TO`, then `EMAIL_TEST_MODE = False` |
| See what a run did | Read the newest block at the bottom of `out/daily.log` |
| Re-run today (e.g. after "Not now") | `./daily.sh` |
| Make the report for another day | `./daily.sh 2026-11-17` |
| Use a manual phone export instead | Put the `.txt` in `inbox/`, then `uv run daily.py` |
| Add a product spelling | Add it to `PRODUCTS` in `config.py` |
| Change the time | Edit Hour/Minute in `launchd/com.salestracker.daily.plist.template`, run `./launchd/install.sh` |
| Turn the schedule off | `./launchd/install.sh --remove` |
| Run the tests | `uv run pytest` |

## Files

| File | Role |
|---|---|
| `daily.sh` | The scheduled job: snapshot → fetch → report, with retry dialog and notifications |
| `fetch_chat.py` | Reads one day of the group from the WhatsApp data, writes an export-style `.txt` |
| `daily.py` | One command for the report: runs the three steps below |
| `preprocess.py` | Step 1: raw export → clean CSV for one day |
| `report.py` | Step 2: CSV → Excel report (Summary + Issues sheets) |
| `view.py` | Prints a report in the terminal |
| `checks.py` | Pre-email checks: Excel matches the posts, chat is fresh |
| `send_report.py` | Step 3: checks, then email via Mail.app; logs to `out/sent_log.csv` |
| `config.py` | Products, spellings, folders (shared settings) |
| `config_local.py` | Your group name, your name, rep ids, email addresses (**not in git**; copy from `config_local.example.py`) |
| `tools/` | `wa-snapshot`, the WhatsApp data copier, and why it exists |
| `launchd/` | Schedule template and installer |
| `tests/` | Parser and counting tests (made-up data) |
| `docs/HISTORY.md` | Decisions and progress so far |

## Privacy

This repository contains **no chat data**. `inbox/`, `processed/`, `out/`, `.wa_snapshot/` and
`config_local.py` stay on your Mac (see `.gitignore`). The tests use invented names and messages.

WhatsApp's data is read only by `tools/wa-snapshot`, read-only and on your Mac. The only thing that
leaves the Mac is the report email, sent by your own Mail.app to the addresses in `config_local.py`.

## Current state

**Working**
- The daily 18:40 run, from WhatsApp to the Excel report, with no manual export and no permission
  pop-ups.
- A Retry / Not now dialog when WhatsApp hasn't synced, then a fresh attempt.
- Real-data check (2026-11-16): the report built from the WhatsApp database was identical to one
  built from a manual phone export of the same day.
- Email via Mail.app after two blocking checks (Excel matches the posts; chat is for the report day).
  In test mode (to yourself) until the team leader's address is added.
- 48 tests passing.

**Known limitations**
- **Reps still post each sale through the day.** The design expects one end-of-day message per
  rep, and with "latest post wins", today's totals undercount until reps switch. The Issues sheet
  shows who posted several times.
- **Mac-only, and the Mac must be awake** and logged in at 18:40. If it's asleep, macOS runs the
  job on wake.
- **WhatsApp's database format isn't documented.** An app update could change it; the run would
  then fail loudly instead of producing a wrong report.
- **Only text messages are read.** A number written only in a photo caption is skipped.

**Not done yet / ideas**
- Switching the email from test mode to the team leader (address not known yet).
- A limit for unusual numbers (above 100), parked: see `next-steps.md`.
- A rep roster (`ROSTER` in `config.py`) to list reps who didn't report.
- Extra cleaning rules for messages, deferred until real EOD-format data comes in.
