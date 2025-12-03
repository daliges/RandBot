import pytest
from aiogram.enums import ChatMemberStatus

import bot.channel_handlers as channel_handlers
from data import databases
from tests.conftest import DummyMessage, make_update


@pytest.mark.asyncio
async def test_handle_admin_promotion_flow(monkeypatch, fake_bot):
    private_map_called = {"count": 0}
    channel_id = -100
    fake_bot.register_chat(channel_id, "Channel Name")
    monkeypatch.setattr(databases, "add_channel", lambda cid, name, admin_id=None: None)
    monkeypatch.setattr(databases, "set_channel_admin", lambda cid, aid: None)
    monkeypatch.setattr(
        channel_handlers.mapping, "map_channel_messages", lambda cid, bot: private_map_called.__setitem__("count", cid)
    )
    async def ensure_added(channel_id, bot):
        return True

    async def send_deeplink(bot, channel_id):
        return None

    monkeypatch.setattr(channel_handlers, "ensure_mapping_account_added", ensure_added)
    monkeypatch.setattr(channel_handlers, "send_channel_message_with_deep_link", send_deeplink)
    monkeypatch.setattr(channel_handlers.pay_databases, "get_active_bundle", lambda cid: None)
    monkeypatch.setattr(
        channel_handlers.pay_databases,
        "create_bundle",
        lambda channel_id, stars, purchased_quota, free_quota, expires_at, charge_id: 1,
    )

    update = make_update(channel_id, status=ChatMemberStatus.ADMINISTRATOR)
    await channel_handlers.handle_admin_promotion(update, fake_bot)
    assert private_map_called["count"] == channel_id


@pytest.mark.asyncio
async def test_ignore_non_admin(fake_bot):
    update = make_update(-200, status=ChatMemberStatus.MEMBER)
    await channel_handlers.handle_admin_promotion(update, fake_bot)
    assert fake_bot.sent_messages == []
