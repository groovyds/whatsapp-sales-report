#!/bin/zsh
# Install (or update) the daily 18:40 schedule for this project.
#
#   ./launchd/install.sh             install or reinstall (safe to run again, e.g. after moving the folder)
#   ./launchd/install.sh --remove    turn the schedule off
#
# What it does: fills this project's folder into com.salestracker.daily.plist.template, saves the
# result in ~/Library/LaunchAgents/ (where macOS looks for per-user scheduled jobs) and loads it.
# To change the time, edit Hour/Minute in the template and run this again.
set -e
LABEL=com.salestracker.daily
HERE=${0:A:h}
PROJECT=${HERE:h}
TARGET=~/Library/LaunchAgents/$LABEL.plist
DOMAIN=gui/$(id -u)

launchctl bootout $DOMAIN/$LABEL 2>/dev/null || true

if [[ $1 == --remove ]]; then
    rm -f $TARGET
    echo "Schedule removed."
    exit 0
fi

mkdir -p ~/Library/LaunchAgents "$PROJECT/out"
sed "s|__PROJECT_DIR__|$PROJECT|g" "$HERE/$LABEL.plist.template" > $TARGET
plutil -lint $TARGET >/dev/null
launchctl bootstrap $DOMAIN $TARGET
echo "Installed: daily.sh runs every day at the time set in $TARGET (log: out/daily.log)."
echo "Test it now with:  launchctl kickstart $DOMAIN/$LABEL"
