#!/bin/sh
# Install / remove / inspect the nightly update job (launchd, per-user).
#   scripts/nightly.sh install | uninstall | status | run-now | log
# The plist in launchd/ is a template: install fills in this checkout's path, the
# Python on PATH (override with MARKETS_PYTHON=/path/to/python3) and the log folder.
set -e
LABEL=com.rajatraina.markets.update
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO/launchd/$LABEL.plist"
DST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGDIR="$HOME/Library/Logs/markets"
LOG="$LOGDIR/update.log"
case "$1" in
  install)
    PY="${MARKETS_PYTHON:-$(command -v python3)}"
    mkdir -p "$LOGDIR" "$HOME/Library/LaunchAgents"
    sed -e "s|__REPO__|$REPO|g" -e "s|__PYTHON__|$PY|g" -e "s|__LOG__|$LOG|g" "$SRC" > "$DST"
    plutil -lint "$DST" >/dev/null
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
