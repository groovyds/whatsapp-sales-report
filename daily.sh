#!/bin/zsh
# Daily run: export today's group chat from the WhatsApp Mac app, then build the Excel report.
# Scheduled at 18:40 by launchd; set up with ./launchd/install.sh (log: out/daily.log).
#
# If a run fails (most often: the WhatsApp Mac app hasn't synced today's messages yet), it
# opens WhatsApp and shows a dialog, then waits:
#   Retry   (or Return)  -> runs again; asks again if it still fails
#   Not now (or Escape)  -> stops for today; run ./daily.sh later by hand
#   no answer for 4 hours -> stops, so tomorrow's 18:40 run isn't blocked
#
# Needs: the Mac awake and logged in at 18:40, and the WhatsApp Mac app linked.
#
# WhatsApp's data is read only by tools/wa-snapshot, a small program with Full Disk Access that
# copies the databases into .wa_snapshot/. Everything else (uv, Python) reads that copy, which is
# deleted when the run ends. Why, and how to set it up: tools/README.md.
#
# Run by hand any time:  ./daily.sh             (today)
#                        ./daily.sh 2026-11-17  (another day)
cd "${0:A:h}" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

DAY=${1:-$(date +%F)}
export WA_DATA_DIR="$PWD/.wa_snapshot"              # fetch_chat.py reads the copy, not WhatsApp
trap 'rm -rf "$WA_DATA_DIR"' EXIT                   # never leave the chat copy lying around
WAIT_SECONDS=${WAIT_SECONDS:-14400}     # how long the dialog waits for an answer (4 hours)

notify() { osascript -e "display notification \"$1\" with title \"Sales Tracker\"" 2>/dev/null; }

# Ask Retry / Not now. Returns 0 for Retry, 1 for Not now or no answer.
ask_retry() {
    local answer
    answer=$(osascript \
        -e 'on run argv' \
        -e 'display dialog (item 1 of argv) with title "Sales Tracker" buttons {"Not now", "Retry"} default button "Retry" cancel button "Not now" with icon caution giving up after (item 2 of argv as integer)' \
        -e 'end run' "$1" "$WAIT_SECONDS" 2>/dev/null)
    case $answer in
        *"gave up:true"*) echo ">> No answer after $((WAIT_SECONDS / 60)) min; stopping for today."; return 1 ;;
        *Retry*)          echo ">> Retry chosen at $(date +%H:%M)."; return 0 ;;
        *)                echo ">> 'Not now' chosen at $(date +%H:%M); stopping for today."; return 1 ;;
    esac
}

# One attempt. On failure sets REASON (last line of the error) and HINT.
run_once() {
    local out rc
    out=$(tools/wa-snapshot 2>&1)                    # fresh copy of WhatsApp's data each attempt
    rc=$?
    print -r -- "$out"
    if (( rc )); then
        REASON=${out%%$'\n'*}                       # first line: the actual error
        if (( rc == 2 )); then
            HINT="Could not write the copy in the project folder. See out/daily.log, then click Retry."
        else
            HINT="If it says 'authorization denied', give tools/wa-snapshot Full Disk Access (steps in tools/README.md). Then click Retry."
        fi
        return 1
    fi
    out=$(uv run fetch_chat.py --date "$DAY" 2>&1)
    rc=$?
    print -r -- "$out"
    if (( rc )); then
        REASON=${out##*$'\n'}
        HINT="Open WhatsApp on this Mac and wait until today's messages show up in the group, then click Retry."
        open -g -a WhatsApp 2>/dev/null     # start it syncing in the background
        return 1
    fi
    out=$(uv run daily.py --date "$DAY" "inbox/chat_$DAY.txt" 2>&1)
    rc=$?
    print -r -- "$out"
    if (( rc )); then
        REASON=${out##*$'\n'}
        HINT="See out/daily.log for details. Click Retry after fixing it."
        return 1
    fi
}

echo "===== $(date '+%Y-%m-%d %H:%M:%S')  (report day: $DAY)"
attempt=1
until run_once; do
    echo ">> Attempt $attempt failed: $REASON"
    notify "Report for $DAY failed. Waiting for you to retry."
    ask_retry "The sales report for $DAY could not be made (attempt $attempt).

$REASON

$HINT" || exit 1
    (( attempt++ ))
    echo "----- attempt $attempt, $(date +%H:%M:%S)"
done
notify "Report for $DAY is ready in out/"
