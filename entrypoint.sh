#!/usr/bin/env bash
set -e

python scripts/migrate_sqlite.py
exec python main.py
