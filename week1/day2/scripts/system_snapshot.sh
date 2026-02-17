#!/bin/bash
# system_snapshot.sh — Logs disk usage and date every time it runs

LOGFILE="/tmp/system_snapshot.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

echo "=== Snapshot at $TIMESTAMP ===" >> "$LOGFILE"
echo "--- Disk Usage ---" >> "$LOGFILE"
df -h / >> "$LOGFILE"
echo "--- Memory ---" >> "$LOGFILE"
free -m >> "$LOGFILE"
echo "" >> "$LOGFILE"
