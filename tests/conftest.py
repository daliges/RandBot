import asyncio
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from types import SimpleNamespace
import bot.private_handlers as private_handlers
import pytest
import app_context
import databases


class DummyFuture:
    def __init__(self, coro):
        self._coro = coro
    def result(self):
        return asyncio.run(self._coro)


class FakeBot:
    def __init__(self):
        self.deleted_scopes = []
        self.commands_set = []
        self.message_handlers = []
        self.member_handlers = []
        self.sent_messages = []
        self.forwarded_messages = []
        self.reply_markup = []
        self.invite_links = []
        self.chats: dict[int, SimpleNamespace] = {}
        self.me = SimpleNamespace(username="randbot")
        self.forward_should_fail = False

    def delete_my_commands(self, scope):
        self.deleted_scopes.append(scope)

    def set_my_commands(self, commands, scope):
        self.commands_set.append((commands, scope))

    def message_handler(self, commands=None, func=None):
        def decorator(fn):
            self.message_handlers.append(
                {"commands": commands or [], "func": func, "handler": fn}
            )
            return fn
        return decorator

    def my_chat_member_handler(self):
        def decorator(fn):
            self.member_handlers.append(fn)
            return fn
        return decorator

    def send_message(self, chat_id, text, reply_markup=None):
        self.sent_messages.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )

    def forward_message(self, chat_id, from_chat_id, message_id):
        if self.forward_should_fail:
            raise RuntimeError("forward failed")
        self.forwarded_messages.append(
            {"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": message_id}
        )

    def get_chat(self, chat_id):
        if chat_id not in self.chats:
            raise ValueError(f"Unknown chat {chat_id}")
        return self.chats[chat_id]

    def register_chat(self, chat_id, title):
        self.chats[chat_id] = SimpleNamespace(id=chat_id, title=title)

    def get_me(self):
        return self.me

    def create_chat_invite_link(self, channel_id, name, creates_join_request):
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
    databases.initialize()
    yield
    sqlite3.connect(db_path).close()


@pytest.fixture
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
    mock = RedisMock()
    monkeypatch.setattr(databases, "redis_client", mock)
    monkeypatch.setattr(private_handlers, "redis_client", mock)
    return mock


@pytest.fixture
def fake_bot():
    return FakeBot()


@pytest.fixture
def dummy_threadsafe(monkeypatch):
    """Patch asyncio.run_coroutine_threadsafe to execute synchronously."""
    def _runner(module):
        def _threadsafe(coro, loop):
            return DummyFuture(coro)
        monkeypatch.setattr(module.asyncio, "run_coroutine_threadsafe", _threadsafe)
    return _runner


def make_message(chat_id=10, user_id=20, text="/start"):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id),
        chat_id=chat_id,
        text=text,
        from_user=SimpleNamespace(id=user_id),
    )


def make_update(channel_id, status="administrator"):
    new_member = SimpleNamespace(status=status)
    chat = SimpleNamespace(id=channel_id)
    return SimpleNamespace(new_chat_member=new_member, chat=chat)
