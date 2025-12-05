from datetime import datetime, timedelta, timezone

import pytest

import check
from data import databases, pay_databases


@pytest.mark.asyncio
async def test_process_expired_bundles_marks_and_notifies(fake_bot):
    channel_id = 700
    databases.add_channel(channel_id, "Expired Channel", admin_id=12345)

    bundle_id = pay_databases.create_bundle(
        channel_id,
        stars_paid=30,
        purchased_quota=0,
        free_quota=0,
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )

    await check.process_expired_bundles(fake_bot)

    with databases._connect(databases.CHANNELS_DB) as conn:  # type: ignore[attr-defined]
        status = conn.execute("SELECT status FROM bundles WHERE id = ?", (bundle_id,)).fetchone()["status"]
        refunds = conn.execute("SELECT stars_refunded FROM refunds WHERE bundle_id = ?", (bundle_id,)).fetchall()

    expected_status = "refunded" if check.REFUND_METHOD == "refund" else "credited"
    assert status == expected_status
    assert refunds and refunds[0]["stars_refunded"] == 30
    assert any(str(channel_id) in msg["text"] for msg in fake_bot.sent_messages)


@pytest.mark.asyncio
async def test_process_pending_intents_updates_status(fake_bot):
    channel_id = 710
    other_channel = 711
    databases.add_channel(channel_id, "Mapped")
    databases.add_channel(other_channel, "Other")

    databases.save_subscription_intent(user_id=1, channel_id=channel_id)
    databases.save_subscription_intent(user_id=2, channel_id=other_channel)

    old_time = datetime.now(timezone.utc) - timedelta(days=2)
    with databases._connect(databases.CHANNELS_DB) as conn:  # type: ignore[attr-defined]
        conn.execute(
            "UPDATE subscription_intents SET clicked_at = ? WHERE user_id IN (?, ?)",
            (old_time.isoformat(), 1, 2)
        )
        conn.commit()

    fake_bot.set_chat_member(channel_id, 1, check.ChatMemberStatus.MEMBER)

    await check.process_pending_intents(fake_bot)

    with databases._connect(databases.CHANNELS_DB) as conn:  # type: ignore[attr-defined]
        statuses = {row["user_id"]: row["status"] for row in conn.execute("SELECT user_id, status FROM subscription_intents")}
        subscriptions = {row["user_id"] for row in conn.execute("SELECT user_id FROM subscriptions")}

    assert statuses[1] == "subscribed"
    assert statuses[2] == "not_subscribed"
    assert 1 in subscriptions
    assert 2 not in subscriptions
