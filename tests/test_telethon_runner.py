import types

import telethon_runner


def test_init_telethon_no_credentials(monkeypatch, capsys):
    monkeypatch.setattr(telethon_runner, "API_ID", 0)
    monkeypatch.setattr(telethon_runner, "API_HASH", "")
    telethon_runner.init_telethon()
    assert "Telethon credentials missing" in capsys.readouterr().out


def test_init_telethon_spawns_thread(monkeypatch):
    started = {}

    class DummyThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
        def start(self):
            started["called"] = True

    monkeypatch.setattr(telethon_runner, "API_ID", 1)
    monkeypatch.setattr(telethon_runner, "API_HASH", "hash")
    monkeypatch.setattr(telethon_runner, "threading", types.SimpleNamespace(Thread=DummyThread))
    telethon_runner.init_telethon()
    assert started.get("called") is True
