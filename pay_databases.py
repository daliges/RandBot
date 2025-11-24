from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from databases import _connect
from pathlib import Path

import sqlite3
import os


load_dotenv()

CHANNELS_DB = Path(os.getenv("CHANNELS_DB_PATH"))

def create_bundle(channel_id: int, stars_paid: int, purchased_quota: int, free_quota: int = 10,
                expires_at: datetime | None = None, telegram_charge_id: str | None = None) -> int:
    expires = expires_at or (datetime.now(timezone.utc) + timedelta(days=30))
    with _connect(CHANNELS_DB) as conn:
        cur = conn.execute(
            """
            INSERT INTO bundles (channel_id, stars_paid, purchased_quota, free_quota, expires_at, telegram_charge_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (channel_id, stars_paid, purchased_quota, free_quota, expires.isoformat(), telegram_charge_id),
        )
        conn.commit()
        return cur.lastrowid

def record_subscription(user_id: int, channel_id: int, bundle_id: int | None = None) -> bool:
    # returns True if newly recorded, False if duplicate
    with _connect(CHANNELS_DB) as conn:
        cur = None
        try:
            cur = conn.execute(
                """
                INSERT INTO subscriptions (user_id, channel_id, bundle_id)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, channel_id) DO NOTHING
                """,
                (user_id, channel_id, bundle_id),
            )
        except sqlite3.OperationalError:
            # SQLite <3.24 may not support DO NOTHING; fallback to ignore
            cur = conn.execute(
                "INSERT OR IGNORE INTO subscriptions (user_id, channel_id, bundle_id) VALUES (?, ?, ?)",
                (user_id, channel_id, bundle_id),
            )
        if cur and cur.rowcount > 0:
            _increment_consumption(conn, bundle_id)
        conn.commit()
        return bool(cur and cur.rowcount > 0)


def _increment_consumption(conn: sqlite3.Connection, bundle_id: int | None) -> None:
    if not bundle_id:
        return
    conn.execute(
        """
        UPDATE bundles
            SET consumed_free = CASE
                    WHEN free_quota > consumed_free THEN consumed_free + 1
                    ELSE consumed_free
                END,
                consumed_paid = CASE
                    WHEN free_quota > consumed_free THEN consumed_paid
                ELSE consumed_paid + 1
            END
            WHERE id = ? AND status = 'active'
        """,
    (bundle_id,),
    )

def get_active_bundle(channel_id: int) -> dict | None:
    with _connect(CHANNELS_DB) as conn:
        row = conn.execute(
            """
            SELECT * FROM bundles
            WHERE channel_id = ? AND status = 'active' AND expires_at >= ?
            ORDER BY starts_at DESC LIMIT 1
            """,
            (channel_id, datetime.now(timezone.utc).isoformat()),
        ).fetchone()
    return dict(row) if row else None

def mark_bundle_status(bundle_id: int, status: str) -> None:
    with _connect(CHANNELS_DB) as conn:
        conn.execute("UPDATE bundles SET status = ? WHERE id = ?", (status, bundle_id))
        conn.commit()

def find_expired_bundles_pending_refund(now: datetime | None = None) -> list[dict]:
    now_iso = (now or datetime.now(timezone.utc)).isoformat()
    with _connect(CHANNELS_DB) as conn:
        rows = conn.execute(
            """
            SELECT * FROM bundles
            WHERE status = 'active' AND expires_at < ?
            """,
            (now_iso,),
        ).fetchall()
    return [dict(r) for r in rows]

def record_refund(bundle_id: int, stars_refunded: int, method: str) -> None:
    with _connect(CHANNELS_DB) as conn:
        conn.execute(
            "INSERT INTO refunds (bundle_id, stars_refunded, method) VALUES (?, ?, ?)",
            (bundle_id, stars_refunded, method),
        )
        conn.commit()

def bundle_consumption_summary(bundle_id: int) -> dict | None:
    with _connect(CHANNELS_DB) as conn:
        row = conn.execute(
            """
            SELECT id, channel_id, purchased_quota, free_quota, consumed_free, consumed_paid,
                expires_at, status, stars_paid
            FROM bundles WHERE id = ?
            """,
            (bundle_id,),
        ).fetchone()
    return dict(row) if row else None
