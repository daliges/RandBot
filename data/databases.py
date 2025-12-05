from datetime import datetime
import json
import sqlite3
from pathlib import Path
from typing import Dict, List
from dotenv import load_dotenv
import os
import redis

load_dotenv()

CHANNELS_DB = Path(os.getenv("CHANNELS_DB_PATH"))

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT)

def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize() -> None:
    with _connect(CHANNELS_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS channels (
                channel_id INTEGER PRIMARY KEY,
                channel_name TEXT NOT NULL,
                admin_id INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mappings (
                channel_id INTEGER PRIMARY KEY,
                channel_media_map TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS channel_users (
                user_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                linked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE
        );
        """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_channel_users_channel 
                ON channel_users(channel_id);
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bundles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                stars_paid INTEGER NOT NULL,
                purchased_quota INTEGER NOT NULL,
                free_quota INTEGER NOT NULL DEFAULT 0,
                consumed_free INTEGER NOT NULL DEFAULT 0,
                consumed_paid INTEGER NOT NULL DEFAULT 0,
                starts_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'expired', 'refunded', 'credited')),
                telegram_charge_id TEXT,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE
                );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS 
                idx_bundles_channel_status ON bundles(channel_id, status);
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                bundle_id INTEGER,
                status TEXT NOT NULL DEFAULT 'subscribed' CHECK(status IN ('subscribed', 'left', 'duplicate')),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, channel_id),
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE,
                FOREIGN KEY (bundle_id) REFERENCES bundles(id) ON DELETE SET NULL
                );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS 
                idx_subscriptions_channel ON subscriptions(channel_id);
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS refunds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bundle_id INTEGER NOT NULL,
                stars_refunded INTEGER NOT NULL,
                method TEXT NOT NULL CHECK(method IN ('refund', 'credit')),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (bundle_id) REFERENCES bundles(id) ON DELETE CASCADE
                );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS 
                idx_refunds_bundle ON refunds(bundle_id);
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscription_intents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                clicked_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'subscribed', 'not_subscribed')),
                UNIQUE(user_id, channel_id),
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()


def get_channel_media_map(channel_id: int) -> list[int]:
    with _connect(CHANNELS_DB) as conn:
        row = conn.execute(
            "SELECT channel_media_map FROM mappings WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
    if not row or not row["channel_media_map"]:
        return []
    try:
        return [int(mid) for mid in json.loads(row["channel_media_map"])]
    except json.JSONDecodeError:
        return []


def save_channel_media_map(channel_id: int, media_ids: List[int]) -> None:
    serialized = json.dumps([int(media_id) for media_id in media_ids])
    with _connect(CHANNELS_DB) as conn:
        conn.execute(
            """
            INSERT INTO mappings (channel_id, channel_media_map)
            VALUES (?, ?)
            ON CONFLICT(channel_id) DO UPDATE
                SET channel_media_map = excluded.channel_media_map
            """,
            (channel_id, serialized),
        )
        conn.commit()


def add_channel(channel_id: int, channel_name: str, admin_id: int | None = None) -> None:
    with _connect(CHANNELS_DB) as conn:
        conn.execute(
            """
            INSERT INTO channels (channel_id, channel_name, admin_id)
            VALUES (?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE
                SET channel_name = excluded.channel_name,
                admin_id = COALESCE(excluded.admin_id, admin_id)
            """,
            (channel_id, channel_name, admin_id),
        )
        conn.commit()

def link_user_to_channel(user_id: int, channel_id: int) -> None:
    with _connect(CHANNELS_DB) as conn:
        conn.execute(
            """
            INSERT INTO channel_users (user_id, channel_id, linked_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE
            SET channel_id = excluded.channel_id,
                linked_at = excluded.linked_at
            """,
            (user_id, channel_id),
        )
        conn.commit()

def is_channel_in_mappings(channel_id: int) -> bool:
    with _connect(CHANNELS_DB) as conn:
        row = conn.execute(
            "SELECT 1 FROM mappings WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()
    return row is not None

def get_user_channel(user_id: int) -> int | None:
    with _connect(CHANNELS_DB) as conn:
        row = conn.execute(
            "SELECT channel_id FROM channel_users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return row["channel_id"] if row else None

def get_channel_users(channel_id: int) -> list[int]:
    with _connect(CHANNELS_DB) as conn:
        rows = conn.execute(
            "SELECT user_id FROM channel_users WHERE channel_id = ?",
            (channel_id,),
        ).fetchall()
    return [row["user_id"] for row in rows]


def get_mapped_channel_ids() -> list[int]:
    with _connect(CHANNELS_DB) as conn:
        rows = conn.execute("SELECT channel_id FROM mappings").fetchall()
    return [row["channel_id"] for row in rows]


def set_channel_admin(channel_id: int, admin_id: int) -> None:
    with _connect(CHANNELS_DB) as conn:
        cursor = conn.execute(
            "UPDATE channels SET admin_id = ? WHERE channel_id = ?",
            (admin_id, channel_id)
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Channel {channel_id} not found")
        conn.commit()

def get_channel_admin(channel_id: int) -> int | None:
    with _connect(CHANNELS_DB) as conn:
        row = conn.execute("SELECT admin_id FROM channels WHERE channel_id = ?", (channel_id,)).fetchone()
    return row["admin_id"] if row else None


def list_admin_channel_ids(admin_id: int) -> list[int]:
    with _connect(CHANNELS_DB) as conn:
        rows = conn.execute("SELECT channel_id FROM channels WHERE admin_id = ?", (admin_id,)).fetchall()
    return [row["channel_id"] for row in rows]



def delete_subs():
    with _connect(CHANNELS_DB) as conn:
        conn.execute(
            """
            DELETE FROM subscription_intents
            WHERE status IN ('subscribed', 'not_subscribed')
            """
        )
        conn.commit()


def save_subscription_intent(user_id: int, channel_id: int) -> None:
    with _connect(CHANNELS_DB) as conn:
        conn.execute(
            """
            INSERT INTO subscription_intents (user_id, channel_id)
            VALUES (?, ?)
            ON CONFLICT(user_id, channel_id) DO UPDATE
                SET clicked_at = excluded.clicked_at,
                    status = 'pending'
            """,
            (user_id, channel_id),
        )
        conn.commit()


def mark_intent_status(intent_id: int, status: str) -> None:
    allowed_statuses = ('pending', 'subscribed', 'not_subscribed')
    if status not in allowed_statuses:
        raise ValueError(f"Invalid status: {status}. Must be one of {allowed_statuses}")
    with _connect(CHANNELS_DB) as conn:
        cursor = conn.execute(
            "UPDATE subscription_intents SET status = ? WHERE id = ?",
            (status, intent_id),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Subscription intent {intent_id} not found")
        conn.commit()

def list_pending_intents(cutoff: datetime) -> list[sqlite3.Row]:
    cutoff_str = cutoff.isoformat()
    with _connect(CHANNELS_DB) as conn:
        return conn.execute(
            """
            SELECT * FROM subscription_intents
            WHERE status = 'pending' AND datetime(clicked_at) <= datetime(?)
            """,
            (cutoff_str,),
        ).fetchall()
