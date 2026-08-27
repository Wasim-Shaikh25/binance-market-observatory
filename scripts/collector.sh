#!/usr/bin/env bash
# Run the collector detached from the terminal, and stop/check it later.
#
# Usage:
#   scripts/collector.sh start    # launch in the background, return immediately
#   scripts/collector.sh stop     # graceful shutdown (SIGTERM), waits up to 30s
#   scripts/collector.sh status   # is it running right now?
#   scripts/collector.sh tail     # follow the current run's log (Ctrl-C to stop watching)
#
# Each "start" gets its own log file and, per config/settings.yaml's
# database.path pattern, its own database file -- see
# docs/requirements/2026-08-27-per-run-db-and-background-run-scripts/.
set -euo pipefail
cd "$(dirname "$0")/.."

PID_FILE="data/collector.pid"
PYTHON="${PYTHON:-.venv/bin/python}"
mkdir -p data/logs

is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

case "${1:-}" in
    start)
        if is_running; then
            echo "Already running (PID $(cat "$PID_FILE"))."
            exit 1
        fi
        RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
        LOG_FILE="data/logs/run_${RUN_ID}.log"
        RUN_ID="$RUN_ID" nohup "$PYTHON" -m src.main >"$LOG_FILE" 2>&1 &
        echo $! >"$PID_FILE"
        disown
        echo "Started run $RUN_ID (PID $(cat "$PID_FILE"))."
        echo "Log: $LOG_FILE"
        sleep 1
        grep -m1 "Writing to database" "$LOG_FILE" 2>/dev/null || true
        ;;
    stop)
        if ! is_running; then
            echo "Not running."
            rm -f "$PID_FILE"
            exit 1
        fi
        PID="$(cat "$PID_FILE")"
        kill -TERM "$PID"
        echo "Sent SIGTERM to PID $PID -- draining writes and closing the database..."
        for _ in $(seq 1 30); do
            if ! kill -0 "$PID" 2>/dev/null; then
                echo "Stopped cleanly."
                rm -f "$PID_FILE"
                exit 0
            fi
            sleep 1
        done
        echo "Still running after 30s -- check $PID_FILE and the log for what's stuck."
        exit 1
        ;;
    status)
        if is_running; then
            echo "Running (PID $(cat "$PID_FILE"))."
        else
            echo "Not running."
        fi
        ;;
    tail)
        LATEST="$(ls -t data/logs/run_*.log 2>/dev/null | head -1)"
        if [ -z "$LATEST" ]; then
            echo "No logs yet -- has it been started?"
            exit 1
        fi
        tail -f "$LATEST"
        ;;
    *)
        echo "Usage: $0 {start|stop|status|tail}"
        exit 2
        ;;
esac
