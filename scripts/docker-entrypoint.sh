#!/bin/sh
set -eu

DATA_DIR="${RAB_DATA_DIR:-/app/data}"
EXPORT_DIR="${RAB_EXPORT_DIR:-$DATA_DIR/exports}"

mkdir -p "$DATA_DIR" "$EXPORT_DIR"

if [ -f /app/seed-data/sbm-cache.xlsx ] && [ ! -f "$DATA_DIR/sbm-cache.xlsx" ]; then
  cp /app/seed-data/sbm-cache.xlsx "$DATA_DIR/sbm-cache.xlsx"
fi

python scripts/seed.py

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
