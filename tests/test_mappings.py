import bot.mapping as mapping
import databases


def test_returns_cached_map(monkeypatch):
    monkeypatch.setattr(databases, "is_channel_in_mappings", lambda cid: True)
    monkeypatch.setattr(databases, "get_channel_media_map", lambda cid: [7, 8])
    assert mapping.map_channel_messages(123, None) == [7, 8]


def test_missing_client(monkeypatch):
    monkeypatch.setattr(databases, "is_channel_in_mappings", lambda cid: False)
    monkeypatch.setattr(mapping.app_context, "telethon_loop", None)
    monkeypatch.setattr(mapping.app_context, "telethon_client", None)
    assert mapping.map_channel_messages(555, None) == []


def test_collects_and_persists(monkeypatch, dummy_threadsafe):
    monkeypatch.setattr(databases, "is_channel_in_mappings", lambda cid: False)
    saved = {}
    monkeypatch.setattr(
        databases,
        "save_channel_media_map",
        lambda cid, mids: saved.setdefault(cid, mids),
    )
    monkeypatch.setattr(mapping.app_context, "telethon_loop", object())
    monkeypatch.setattr(mapping.app_context, "telethon_client", object())

    async def fake_collect(channel_id):
        assert channel_id == 999
        return [10, 11]

    monkeypatch.setattr(mapping, "_collect_media_ids", fake_collect)
    dummy_threadsafe(mapping)

    assert mapping.map_channel_messages(999, None) == [10, 11]
    assert saved[999] == [10, 11]
