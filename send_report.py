"""Step 3: run the checks, then email the day's report with Mail.app. Nothing is sent if a check fails.

Usage:
    uv run send_report.py                     # today's report
    uv run send_report.py --date 2026-11-16

Who gets it (config.py / config_local.py):
    EMAIL_TEST_MODE = True   -> EMAIL_TEST_TO, subject starts with [TEST]
    EMAIL_TEST_MODE = False  -> EMAIL_TO (the team leader)

If this day's report was already sent to the same address, you're asked first: y/n in the
terminal, or a Send / Don't send dialog when it runs on the schedule.
Every send is logged in out/sent_log.csv.

Exit codes: 0 sent (or you chose not to re-send), 3 a check failed, 1 anything else.
"""
import argparse
import csv
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import checks
import config
import report

SENT_LOG = Path(config.OUT) / "sent_log.csv"
DIALOG_WAIT = 4 * 60 * 60        # an unanswered re-send dialog means "don't send"

MAIL_SCRIPT = """
on run argv
    set {theTo, theSubject, theBody, thePath} to argv
    set theFile to (POSIX file thePath) as alias
    tell application "Mail"
        set msg to make new outgoing message with properties {subject:theSubject, content:theBody & return & return, visible:false}
        tell msg
            make new to recipient at end of to recipients with properties {address:theTo}
            tell content
                make new attachment with properties {file name:theFile} at after the last paragraph
            end tell
        end tell
        delay 2
        send msg
    end tell
end run
"""

ASK_SCRIPT = """
on run argv
    display dialog (item 1 of argv) with title "Sales Tracker" buttons {"Don't send", "Send"} default button "Don't send" cancel button "Don't send" with icon caution giving up after (item 2 of argv as integer)
end run
"""


def recipient():
    if config.EMAIL_TEST_MODE:
        to, prefix = config.EMAIL_TEST_TO, "[TEST] "
        if not to:
            sys.exit("EMAIL_TEST_MODE is on but EMAIL_TEST_TO is empty. Set it in config_local.py.")
    else:
        to, prefix = config.EMAIL_TO, ""
        if not to:
            sys.exit("EMAIL_TO (the team leader) is empty. Set it in config_local.py, "
                     "or turn EMAIL_TEST_MODE back on.")
    return to, prefix


def body_text(day):
    latest, _ = report.build_report(list(report.load_messages(checks.csv_path(day))))
    lines = [f"{config.EMAIL_GREETING}", "",
             f"Daily sales report for {day:%d.%m.%Y} ({len(latest)} reps reported).", "",
             "Totals:"]
    for p in report.PRODUCT_NAMES:
        lines.append(f"  {p}: {sum(c.get(p, 0) for _, c in latest.values())}")
    lines += ["", "The full report is attached."]
    return "\n".join(lines)


def previous_sends(day, to):
    if not SENT_LOG.exists():
        return []
    with SENT_LOG.open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["day"] == day.isoformat() and r["to"] == to]


def confirm_resend(day, to, last):
    question = (f"The report for {day} was already sent to {to} at {last}. "
                f"This will send a new email.")
    if os.isatty(0):        # run by hand (also via daily.sh): ask in the terminal
        with open("/dev/tty", "r+") as tty:
            tty.write(f"\n{question}\nSend again? [y/n] ")
            tty.flush()
            return tty.readline().strip().lower() in ("y", "yes")
    result = subprocess.run(["osascript", "-e", ASK_SCRIPT, question, str(DIALOG_WAIT)],
                            capture_output=True, text=True)
    return "Send" in result.stdout and "gave up:true" not in result.stdout


def send_mail(to, subject, body, attachment):
    result = subprocess.run(["osascript", "-e", MAIL_SCRIPT, to, subject, body, str(attachment.resolve())],
                            capture_output=True, text=True)
    if result.returncode:
        sys.exit(f"Mail.app could not send the email: {result.stderr.strip()}\n"
                 "If it mentions 'Not authorized', allow control of Mail in System Settings > "
                 "Privacy & Security > Automation.")


def log_send(day, to):
    new = not SENT_LOG.exists()
    SENT_LOG.parent.mkdir(exist_ok=True)
    with SENT_LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["day", "sent_at", "to", "test"])
        w.writerow([day.isoformat(), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), to,
                    "yes" if config.EMAIL_TEST_MODE else "no"])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", help="report day as YYYY-MM-DD; default: today")
    args = ap.parse_args()
    day = date.fromisoformat(args.date) if args.date else date.today()

    problems = checks.run(day)
    if problems:
        print(f"Email NOT sent: {len(problems)} check(s) failed for {day}:")
        for p in problems:
            print(f"  ✗ {p}")
        sys.exit(3)
    print(f"All checks passed for {day}.")

    to, prefix = recipient()
    earlier = previous_sends(day, to)
    if earlier and not confirm_resend(day, to, earlier[-1]["sent_at"]):
        print(f"Not re-sent: the report for {day} already went to {to} at {earlier[-1]['sent_at']}.")
        return
    subject = prefix + config.EMAIL_SUBJECT.format(date=f"{day:%d.%m.%Y}")
    send_mail(to, subject, body_text(day), checks.xlsx_path(day))
    log_send(day, to)
    print(f"Emailed {checks.xlsx_path(day).name} to {to}" + (" (test mode)" if config.EMAIL_TEST_MODE else ""))


if __name__ == "__main__":
    main()
