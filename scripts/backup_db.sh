#!/usr/bin/env bash
#
# SQLite database backup script for bug_report_bot.
# Creates a timestamped copy using SQLite's online backup API (safe during writes).
#
# Usage:
#   ./scripts/backup_db.sh                        # uses defaults
#   ./scripts/backup_db.sh /path/to/db.sqlite     # custom source
#   BACKUP_DIR=/mnt/backups ./scripts/backup_db.sh # custom destination
#
# Environment variables:
#   DB_PATH    – path to SQLite database (default: /app/data/bug_reports.db)
#   BACKUP_DIR – directory for backups  (default: /app/data/backups)
#   KEEP_DAYS  – delete backups older than N days (default: 30)
#
set -euo pipefail

DB_PATH="${1:-${DB_PATH:-/app/data/bug_reports.db}}"
BACKUP_DIR="${BACKUP_DIR:-/app/data/backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"

if [ ! -f "$DB_PATH" ]; then
    echo "ERROR: Database file not found: $DB_PATH" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/bug_reports_${TIMESTAMP}.db"

# Use SQLite .backup command for a consistent snapshot
sqlite3 "$DB_PATH" ".backup '${BACKUP_FILE}'"

# Verify the backup is a valid SQLite database
if sqlite3 "$BACKUP_FILE" "PRAGMA integrity_check;" | grep -q "^ok$"; then
    SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
    echo "OK: Backup created: $BACKUP_FILE ($SIZE)"
else
    echo "ERROR: Backup integrity check failed!" >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Prune old backups
DELETED=$(find "$BACKUP_DIR" -name "bug_reports_*.db" -mtime "+${KEEP_DAYS}" -delete -print | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "Pruned $DELETED backup(s) older than $KEEP_DAYS days"
fi
