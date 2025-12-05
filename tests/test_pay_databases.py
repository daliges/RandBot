from datetime import datetime, timedelta, timezone

from data import databases, pay_databases


def _add_channel(channel_id: int) -> None:
    databases.add_channel(channel_id, f"Channel {channel_id}", admin_id=1)


def test_create_bundle_and_summary():
    channel_id = 10
    _add_channel(channel_id)
    expires = datetime.now(timezone.utc) + timedelta(days=5)

    bundle_id = pay_databases.create_bundle(
        channel_id,
        stars_paid=25,
        purchased_quota=5,
        free_quota=2,
        expires_at=expires,
    )
    summary = pay_databases.bundle_consumption_summary(bundle_id)

    assert summary is not None
    assert summary["channel_id"] == channel_id
    assert summary["purchased_quota"] == 5
    assert summary["free_quota"] == 2
    assert summary["status"] == "active"


def test_record_subscription_increments_free_then_paid():
    channel_id = 20
    _add_channel(channel_id)
    bundle_id = pay_databases.create_bundle(
        channel_id,
        stars_paid=50,
        purchased_quota=1,
        free_quota=1,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )

    assert pay_databases.record_subscription(1, channel_id, bundle_id) is True
    summary = pay_databases.bundle_consumption_summary(bundle_id)
    assert summary["consumed_free"] == 1
    assert summary["consumed_paid"] == 0

    # duplicate subscription does not increment counts
    assert pay_databases.record_subscription(1, channel_id, bundle_id) is False
    summary = pay_databases.bundle_consumption_summary(bundle_id)
    assert summary["consumed_free"] == 1
    assert summary["consumed_paid"] == 0

    assert pay_databases.record_subscription(2, channel_id, bundle_id) is True
    summary = pay_databases.bundle_consumption_summary(bundle_id)
    assert summary["consumed_free"] == 1
    assert summary["consumed_paid"] == 1


def test_get_active_bundle_prefers_latest_active():
    channel_id = 30
    _add_channel(channel_id)
    first = pay_databases.create_bundle(
        channel_id,
        stars_paid=0,
        purchased_quota=0,
        free_quota=0,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    second = pay_databases.create_bundle(
        channel_id,
        stars_paid=5,
        purchased_quota=5,
        free_quota=1,
        expires_at=datetime.now(timezone.utc) + timedelta(days=2),
    )

    active = pay_databases.get_active_bundle(channel_id)
    assert active is not None and active["id"] == second

    pay_databases.mark_bundle_status(second, "expired")
    active = pay_databases.get_active_bundle(channel_id)
    assert active is not None and active["id"] == first


def test_expired_queries_and_refunds():
    channel_id = 40
    _add_channel(channel_id)
    now = datetime.now(timezone.utc)

    zero_bundle = pay_databases.create_bundle(
        channel_id,
        stars_paid=15,
        purchased_quota=0,
        free_quota=0,
        expires_at=now - timedelta(days=1),
    )
    consumed_bundle = pay_databases.create_bundle(
        channel_id,
        stars_paid=10,
        purchased_quota=1,
        free_quota=0,
        expires_at=now - timedelta(days=1),
    )
    pay_databases.record_subscription(99, channel_id, consumed_bundle)
    active_bundle = pay_databases.create_bundle(
        channel_id,
        stars_paid=5,
        purchased_quota=1,
        free_quota=0,
        expires_at=now + timedelta(days=1),
    )

    expired = {b["id"] for b in pay_databases.find_expired_bundles_pending_refund(now=now)}
    assert expired == {zero_bundle, consumed_bundle}

    zero_consumption = {b["id"] for b in pay_databases.find_expired_zero_consumption(now=now)}
    assert zero_consumption == {zero_bundle}
    assert active_bundle not in expired

    pay_databases.record_refund(zero_bundle, stars_refunded=15, method="refund")
    with databases._connect(databases.CHANNELS_DB) as conn:  # type: ignore[attr-defined]
        refund_row = conn.execute("SELECT stars_refunded FROM refunds WHERE bundle_id = ?", (zero_bundle,)).fetchone()
    assert refund_row["stars_refunded"] == 15


def test_list_active_channel_ids_requires_mapping():
    mapped_channel = 50
    other_channel = 51
    _add_channel(mapped_channel)
    _add_channel(other_channel)

    pay_databases.create_bundle(
        mapped_channel,
        stars_paid=0,
        purchased_quota=1,
        free_quota=0,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    pay_databases.create_bundle(
        other_channel,
        stars_paid=0,
        purchased_quota=1,
        free_quota=0,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    databases.save_channel_media_map(mapped_channel, [1, 2, 3])

    active_ids = pay_databases.list_active_channel_ids()
    assert mapped_channel in active_ids
    assert other_channel not in active_ids
