import json
import sqlite3
from pathlib import Path
from typing import Dict, List
from dotenv import load_dotenv
import os

load_dotenv()

CHANNELS_DB = Path(os.getenv("CHANNELS_DB_PATH"))

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
        conn.commit()

    with _connect(CHANNELS_DB) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mappings (
                channel_id INTEGER PRIMARY KEY,
                channel_media_map TEXT NOT NULL
            )
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