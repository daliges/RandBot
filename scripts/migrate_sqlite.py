import os
import sqlite3
from pathlib import Path

DB_PATH = os.environ.get("DB_PATH", "/app/channels.db")
MIGRATIONS_DIR = Path("/app/migrations")

def main():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = path.name
            row = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = ?",
                (version,)
            ).fetchone()
            if row:
                continue

            sql = path.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
            conn.commit()
            print(f"Applied migration: {version}")

        print("Migrations complete.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
