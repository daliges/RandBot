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
                channel_name TEXT NOT NULL
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
        conn.commit()


def load_channel_media_map() -> Dict[int, List[int]]:
    media_map: Dict[int, List[int]] = {}
    with _connect(CHANNELS_DB) as conn:
        rows = conn.execute(
            "SELECT channel_id, channel_media_map FROM mappings"
        ).fetchall()

    for row in rows:
        serialized = row["channel_media_map"]
        try:
            deserialized = json.loads(serialized) if serialized else []
        except json.JSONDecodeError:
            deserialized = []
        if not isinstance(deserialized, list):
            deserialized = []
        media_map[row["channel_id"]] = [int(media_id) for media_id in deserialized]

    return media_map


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


def add_channel(channel_id: int, channel_name: str) -> None:
    with _connect(CHANNELS_DB) as conn:
        conn.execute(
            """
            INSERT INTO channels (channel_id, channel_name)
            VALUES (?, ?)
            ON CONFLICT(channel_id) DO UPDATE
                SET channel_name = excluded.channel_name
            """,
            (channel_id, channel_name),
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