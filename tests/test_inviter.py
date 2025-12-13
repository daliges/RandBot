import pytest

import app_context
import bot.inviter as inviter


@pytest.mark.asyncio
async def test_send_channel_message_with_deep_link(fake_bot):
    fake_bot.me.username = "randbot"
    await inviter.send_channel_message_with_deep_link(fake_bot, -500)
    message = fake_bot.sent_messages[-1]
    assert "start=channel_-500" in message["reply_markup"].inline_keyboard[0][0].url  # type: ignore[attr-defined]


def test_extract_invite_hash_variants():
    assert inviter._extract_invite_hash("https://t.me/+abcd") == "abcd"
    assert inviter._extract_invite_hash("https://t.me/joinchat/xyz") == "xyz"


@pytest.mark.asyncio
async def test_ensure_mapping_account_already_present(monkeypatch, fake_bot, dummy_threadsafe):
    class DummyClient:
        async def get_entity(self, channel_id):
            return True

    dummy_loop = object()
    app_context.telethon_client = DummyClient()
    app_context.telethon_loop = dummy_loop

    dummy_threadsafe(inviter)
    assert await inviter.ensure_mapping_account_added(-100, fake_bot) is True


@pytest.mark.asyncio
async def test_ensure_mapping_account_invites_helper(monkeypatch, fake_bot, dummy_threadsafe):
    class DummyClient:
        async def get_entity(self, channel_id):
            raise ValueError("not yet")

        async def __call__(self, request):
            return True

    app_context.telethon_client = DummyClient()
    app_context.telethon_loop = object()

    dummy_threadsafe(inviter)

    assert await inviter.ensure_mapping_account_added(-50, fake_bot) is True
    assert fake_bot.invite_links
