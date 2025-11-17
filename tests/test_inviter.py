import asyncio
from types import SimpleNamespace

import bot.inviter as inviter
import app_context


def test_send_channel_message_with_deep_link(fake_bot):
    fake_bot.me.username = "randbot"
    inviter.send_channel_message_with_deep_link(fake_bot, -500)
    message = fake_bot.sent_messages[-1]
    assert "start=channel_-500" in message["reply_markup"].keyboard[0][0].url  # type: ignore[attr-defined]


def test_extract_invite_hash_variants():
    assert inviter._extract_invite_hash("https://t.me/+abcd") == "abcd"
    assert inviter._extract_invite_hash("https://t.me/joinchat/xyz") == "xyz"


def test_ensure_mapping_account_already_present(monkeypatch, fake_bot):
    class DummyClient:
        async def get_entity(self, channel_id):
            return True

    dummy_loop = object()
    app_context.telethon_client = DummyClient()
    app_context.telethon_loop = dummy_loop

    async def immediate_true():
        return True

    def fake_threadsafe(coro, loop):
        return SimpleNamespace(result=lambda: asyncio.run(coro))

    monkeypatch.setattr(inviter.asyncio, "run_coroutine_threadsafe", fake_threadsafe)
    assert inviter.ensure_mapping_account_added(-100, fake_bot) is True


def test_ensure_mapping_account_invites_helper(monkeypatch, fake_bot):
    class DummyClient:
        async def get_entity(self, channel_id):
            raise ValueError("not yet")
        async def __call__(self, request):
            return True
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False

    app_context.telethon_client = DummyClient()
    app_context.telethon_loop = object()

    async def run_coro(coro):
        return await coro

    def fake_threadsafe(coro, loop):
        return SimpleNamespace(result=lambda: asyncio.run(coro))

    monkeypatch.setattr(inviter.asyncio, "run_coroutine_threadsafe", fake_threadsafe)
    assert inviter.ensure_mapping_account_added(-50, fake_bot) is True
    assert fake_bot.invite_links
