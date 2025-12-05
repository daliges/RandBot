import asyncio
import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("CHANNELS_DB_PATH", str(ROOT / "channels.db"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app_context
from data import databases, pay_databases
import bot.private_handlers as private_handlers


class DummyFuture:
    def __init__(self, coro):
        self._coro = coro

    def result(self):
        return asyncio.run(self._coro)


class DummySession:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class FakeBot:
    def __init__(self):
        self.deleted_scopes = []
        self.commands_set = []
        self.sent_messages = []
        self.copied_messages = []
        self.edited_messages = []
        self.invite_links = []
        self.chats: dict[int, SimpleNamespace] = {}
        self.chat_members: dict[int, dict[int, SimpleNamespace]] = {}
        self.me = SimpleNamespace(username="randbot")
        self.invoices = []
        self.pre_checkout_answers = []
        self.session = DummySession()

    async def delete_my_commands(self, scope):
        self.deleted_scopes.append(scope)

    async def set_my_commands(self, commands, scope):
        self.commands_set.append((commands, scope))

    async def send_message(self, chat_id, text, reply_markup=None):
        self.sent_messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return SimpleNamespace(message_id=len(self.sent_messages))

    async def copy_message(self, chat_id, from_chat_id, message_id, reply_markup=None):
        self.copied_messages.append(
            {"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": message_id, "reply_markup": reply_markup}
        )
        return SimpleNamespace(message_id=len(self.copied_messages))

    async def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None):
        self.edited_messages.append({"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup})

    async def get_chat(self, chat_id):
        if chat_id not in self.chats:
            raise ValueError(f"Unknown chat {chat_id}")
        return self.chats[chat_id]

    def register_chat(self, chat_id, title, username=None):
        self.chats[chat_id] = SimpleNamespace(id=chat_id, title=title, username=username)

    def set_chat_member(self, chat_id, user_id, status):
        self.chat_members.setdefault(chat_id, {})[user_id] = SimpleNamespace(
            status=status, user=SimpleNamespace(id=user_id)
        )

    async def get_chat_member(self, chat_id, user_id):
        members = self.chat_members.get(chat_id, {})
        if user_id not in members:
            return SimpleNamespace(status=None, user=SimpleNamespace(id=user_id))
        return members[user_id]

    async def create_chat_invite_link(self, channel_id, name=None, creates_join_request=False):
        link = SimpleNamespace(invite_link=f"https://t.me/+invite{channel_id}")
        self.invite_links.append(
            {
                "channel_id": channel_id,
                "name": name,
                "creates_join_request": creates_join_request,
                "link": link,
            }
        )
        return link

    async def get_me(self):
        return self.me

    async def send_invoice(self, chat_id, title, description, payload, provider_token, currency, prices):
        self.invoices.append(
            {
                "chat_id": chat_id,
                "title": title,
                "description": description,
                "payload": payload,
                "provider_token": provider_token,
                "currency": currency,
                "prices": prices,
            }
        )

    async def answer_pre_checkout_query(self, query_id, ok=True):
        self.pre_checkout_answers.append({"query_id": query_id, "ok": ok})


class DummyMessage(SimpleNamespace):
    def __init__(self, chat_id=10, user_id=20, text="/start", successful_payment=None):
        super().__init__(
            chat=SimpleNamespace(id=chat_id),
            chat_id=chat_id,
            text=text,
            from_user=SimpleNamespace(id=user_id),
            message_id=1,
            successful_payment=successful_payment,
        )
        self.replies = []

    async def answer(self, text, reply_markup=None):
        self.replies.append({"text": text, "reply_markup": reply_markup})
        return SimpleNamespace(message_id=len(self.replies))

    async def reply(self, text, reply_markup=None):
        return await self.answer(text, reply_markup)


class DummyCallback(SimpleNamespace):
    def __init__(self, data, from_user=1, message=None):
        super().__init__(data=data, from_user=SimpleNamespace(id=from_user), message=message)
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append({"text": text, "show_alert": show_alert})


@pytest.fixture(autouse=True)
def reset_app_context():
    app_context.bot = None
    app_context.telethon_client = None
    app_context.telethon_loop = None
    yield
    app_context.bot = None
    app_context.telethon_client = None
    app_context.telethon_loop = None


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "channels.db"
    monkeypatch.setattr(databases, "CHANNELS_DB", db_path)
    monkeypatch.setattr(pay_databases, "CHANNELS_DB", db_path)
    monkeypatch.setenv("CHANNELS_DB_PATH", str(db_path))
    databases.initialize()
    yield
    sqlite3.connect(db_path).close()


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    class RedisMock:
        def __init__(self):
            self.data = {}

        def hget(self, name, key):
            bucket = self.data.get(name)
            if not bucket:
                return None
            return bucket.get(key)

        def hset(self, name, key, value):
            bucket = self.data.setdefault(name, {})
            bucket[key] = value
            return 1

        def hdel(self, name, key):
            bucket = self.data.get(name)
            if not bucket or key not in bucket:
                return 0
            del bucket[key]
            return 1

        def get(self, key):
            return self.data.get(key)

        def setex(self, key, ttl, value):
            self.data[key] = value

        def delete(self, key):
            self.data.pop(key, None)

    mock = RedisMock()
    monkeypatch.setattr(databases, "redis_client", mock)
    monkeypatch.setattr(private_handlers, "redis_client", mock, raising=False)
    return mock


@pytest.fixture
def fake_bot():
    return FakeBot()


@pytest.fixture
def dummy_threadsafe(monkeypatch):
    def _runner(module):
        def _threadsafe(coro, loop):
            return DummyFuture(coro)

        monkeypatch.setattr(module.asyncio, "run_coroutine_threadsafe", _threadsafe)

    return _runner


def make_message(chat_id=10, user_id=20, text="/start"):
    return DummyMessage(chat_id=chat_id, user_id=user_id, text=text)


def make_update(channel_id, status="administrator"):
    new_member = SimpleNamespace(status=status, user=SimpleNamespace(id=123))
    chat = SimpleNamespace(id=channel_id)
    return SimpleNamespace(new_chat_member=new_member, chat=chat, from_user=SimpleNamespace(id=123))
