from datetime import datetime, timedelta, timezone

import pytest

from data import databases


def test_save_and_get_channel_media_map():
    channel_id = 100
    media_ids = [1, 2, 3]
    databases.save_channel_media_map(channel_id, media_ids)
    assert databases.get_channel_media_map(channel_id) == media_ids


def test_is_channel_in_mappings():
    channel_id = 200
    assert databases.is_channel_in_mappings(channel_id) is False
    databases.save_channel_media_map(channel_id, [5])
    assert databases.is_channel_in_mappings(channel_id) is True


def test_link_user_to_channel_upserts():
    user_id = 123
    databases.link_user_to_channel(user_id, 1)
    assert databases.get_user_channel(user_id) == 1
    databases.link_user_to_channel(user_id, 2)
    assert databases.get_user_channel(user_id) == 2


def test_get_channel_users_returns_all():
    channel_id = 999
    databases.link_user_to_channel(1, channel_id)
    databases.link_user_to_channel(2, channel_id)
    databases.link_user_to_channel(3, 42)
    assert sorted(databases.get_channel_users(channel_id)) == [1, 2]


def test_admin_set_and_get():
    channel_id = 321
    databases.add_channel(channel_id, "chan321", admin_id=None)
    databases.set_channel_admin(channel_id, 77)
    assert databases.get_channel_admin(channel_id) == 77
    with pytest.raises(ValueError):
        databases.set_channel_admin(9999, 1)


def test_get_mapped_channel_ids_lists_all():
    databases.save_channel_media_map(10, [1])
    databases.save_channel_media_map(20, [2])
    mapped = set(databases.get_mapped_channel_ids())
    assert {10, 20}.issubset(mapped)


def test_subscription_intent_lifecycle():
    databases.save_subscription_intent(1, 100)
    databases.save_subscription_intent(2, 100)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    with databases._connect(databases.CHANNELS_DB) as conn:  # type: ignore[attr-defined]
        conn.execute(
            "UPDATE subscription_intents SET clicked_at = ? WHERE user_id = ?",
            ((cutoff - timedelta(hours=1)).isoformat(), 1),
        )
        conn.commit()
    pending = databases.list_pending_intents(cutoff)
    assert {row["user_id"] for row in pending} == {1}

    databases.mark_intent_status(pending[0]["id"], "subscribed")
    pending = databases.list_pending_intents(cutoff)
    assert pending == []

    with pytest.raises(ValueError):
        databases.mark_intent_status(99999, "invalid")
