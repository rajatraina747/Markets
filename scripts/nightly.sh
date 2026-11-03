#!/bin/sh
# Install / remove / inspect the nightly update job (launchd, per-user).
#   scripts/nightly.sh install | uninstall | status | run-now | log
set -e
LABEL=com.rajatraina.markets.update
SRC="$(cd "$(dirname "$0")/.." && pwd)/launchd/$LABEL.plist"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/markets/update.log"
case "$1" in
  install)
    mkdir -p "$HOME/Library/Logs/markets" "$HOME/Library/LaunchAgents"
    cp "$SRC" "$DST"
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$DST"
    echo "installed: runs Tue–Sat 04:15 local · log: $LOG" ;;
  uninstall)
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$DST"; echo "removed" ;;
  status)
    launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null | grep -E "state|last exit|runs" || echo "not installed" ;;
  run-now)
    launchctl kickstart -p "gui/$(id -u)/$LABEL" ;;
  log)
    tail -n 60 "$LOG" ;;
  *) echo "usage: $0 install|uninstall|status|run-now|log"; exit 1 ;;
esac
