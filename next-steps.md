# Sales Tracker: Next Steps

_Last updated: 17 Nov 2026_

## Parser
- [x] Accept one product per line, e.g. `45 - mobil kontrat`
- [x] Also accept several products on one line, separated by commas, e.g. `45 - mobil kontrat, 4 - spbx, 2 - sol`

## Email to the TL
Mail.app sends it automatically after the checks pass (`send_report.py`). Test mode is on:
emails go to your own address, marked `[TEST]`.
- [x] Send with Mail.app, Excel attached, totals in the body
- [x] Test mode (sends to you only)
- [x] Re-sending the same day asks first (y/n in the terminal, a dialog on the schedule)
- [ ] Add the TL's address (`EMAIL_TO` in `config_local.py`) and set `EMAIL_TEST_MODE = False`

## Checks before the email goes to the TL
If any check fails, don't send the email. Show what's wrong instead (hard block, Retry / Not now only).

- [x] **Totals match:** each rep's total in the saved Excel file matches the numbers in their WhatsApp post
- [x] **Export date:** the chat export is today's, not an old file

## Privacy: delete the WhatsApp copy sooner (noted 19 Nov 2026, not started)
`tools/wa-snapshot` copies WhatsApp's **whole** databases (all chats, not just the sales group) into
`.wa_snapshot/`. `daily.sh` only deletes them when the script exits (`trap … EXIT`), so while the
Retry / Not now dialog or the "send again?" dialog is open (up to 4 hours each), all chats sit there.
- [ ] Delete `.wa_snapshot/` in `daily.sh` right after `fetch_chat.py` has written
  `inbox/chat_YYYY-MM-DD.txt` (nothing after that step reads it; each Retry makes a fresh copy anyway)
- [ ] Also delete any leftover `.wa_snapshot/` at the start of a run (covers a force quit or power loss,
  when the exit trap never runs)
- [ ] Shorten the 4-hour dialog wait (`WAIT_SECONDS` in `daily.sh`, `DIALOG_WAIT` in `send_report.py`)

## Ideas for later
- **Unusual numbers:** flag any product above 100 for one rep in one day (parked: unclear whether it
  should block, since a real day above 100 could then never be sent)
- Leftover lines check: flag any line in a post that the parser couldn't read
  (already listed as a warning on the Issues sheet; it doesn't block the email)
- Missing reps: list reps who didn't post that day (needs `ROSTER` filled in)
