"""Tier-1 tests for src/telegram.py (pure client, no network, no DB)."""

from __future__ import annotations

import json

import pytest

from src import telegram


def test_send_text_none_when_token_disabled(monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("no HTTP call expected")

    monkeypatch.setattr(telegram.requests, "post", _fail)
    assert telegram.send_text("none", "123", "hi") is None
    assert telegram.send_text("", "123", "hi") is None


def test_send_text_none_when_chat_id_empty(monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("no HTTP call expected")

    monkeypatch.setattr(telegram.requests, "post", _fail)
    assert telegram.send_text("token", "", "hi") is None


def test_send_audio_none_when_not_configured(monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("no HTTP call expected")

    monkeypatch.setattr(telegram.requests, "post", _fail)
    assert telegram.send_audio("none", "123", b"audio") is None
    assert telegram.send_audio("token", "", b"audio") is None


def test_send_text_posts_to_send_message_and_returns_result(monkeypatch):
    captured = {}

    def fake_post(url, json=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return _FakeResponse({"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    result = telegram.send_text("tok123", "456", "Bonjour")
    assert captured["url"] == "https://api.telegram.org/bottok123/sendMessage"
    assert captured["json"] == {"chat_id": "456", "text": "Bonjour"}
    assert result["ok"] is True
    assert result["result"]["message_id"] == 1


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


def test_send_text_raises_runtime_error_on_api_failure(monkeypatch):
    monkeypatch.setattr(
        telegram.requests,
        "post",
        lambda *a, **kw: _FakeResponse({"ok": False, "description": "Unauthorized"}),
    )
    with pytest.raises(RuntimeError) as excinfo:
        telegram.send_text("tok", "456", "hi")
    assert "Unauthorized" in str(excinfo.value)


def test_escape_markdown_v2_escapes_reserved():
    assert telegram.escape_markdown_v2("a-b_c.d!e[f]") == "a\\-b\\_c\\.d\\!e\\[f\\]"
    assert telegram.escape_markdown_v2("Titre: 1+2=3") == "Titre: 1\\+2\\=3"


def test_escape_markdown_v2_preserves_links():
    s = "Contexte [selon la NZZ](https://nzz.ch/abc-def_1) point final."
    out = telegram.escape_markdown_v2(s)
    assert "[selon la NZZ](https://nzz.ch/abc-def_1)" in out
    assert out == "Contexte [selon la NZZ](https://nzz.ch/abc-def_1) point final\\."


def test_escape_markdown_v2_escapes_reserved_around_links():
    s = "(avant) [lien](https://x.ch/a-b) (après)"
    assert telegram.escape_markdown_v2(s) == "\\(avant\\) [lien](https://x.ch/a-b) \\(après\\)"


def test_send_audio_bolds_title_and_escapes_caption(monkeypatch):
    captured = {}

    def fake_post(url, data=None, files=None, **kwargs):
        captured["data"] = data
        return _FakeResponse({"ok": True, "result": {}})

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    telegram.send_audio(
        "tok",
        "456",
        b"x",
        caption="L'édition 1-2 est prête.",
        title="Premier Titre",
    )
    assert captured["data"]["caption"] == "*Premier Titre*\n\nL'édition 1\\-2 est prête\\."
    assert captured["data"]["parse_mode"] == "MarkdownV2"


def test_send_audio_no_parse_mode_without_caption_or_title(monkeypatch):
    captured = {}

    def fake_post(url, data=None, files=None, **kwargs):
        captured["data"] = data
        return _FakeResponse({"ok": True, "result": {}})

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    telegram.send_audio("tok", "456", b"x")
    assert "parse_mode" not in captured["data"]
    assert "caption" not in captured["data"]


def test_send_audio_posts_with_files(monkeypatch):
    captured = {}
    audio_bytes = b"\x00\xffmp3data"

    def fake_post(url, data=None, files=None, **kwargs):
        captured["url"] = url
        captured["data"] = data
        captured["files"] = files
        return _FakeResponse({"ok": True, "result": {"audio": {"file_id": "x"}}})

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    result = telegram.send_audio(
        "tok", "456", audio_bytes, filename="editorial.mp3", caption="Le journal"
    )
    assert captured["url"] == "https://api.telegram.org/bottok/sendAudio"
    assert captured["data"]["chat_id"] == "456"
    assert captured["data"]["caption"] == "Le journal"
    assert captured["files"]["audio"][0] == "editorial.mp3"
    assert captured["files"]["audio"][1] == audio_bytes
    assert captured["files"]["audio"][2] == "audio/mpeg"
    assert result["ok"] is True


def test_main_returns_zero_on_happy_path(monkeypatch):
    calls = {}

    def fake_send_text(token, chat_id, text):
        calls["token"] = token
        calls["chat_id"] = chat_id
        calls["text"] = text
        return {"ok": True, "result": {"message_id": 1}}

    monkeypatch.setattr(telegram, "send_text", fake_send_text)
    assert telegram.main(["--token", "t", "--chat-id", "1", "--text", "hi"]) == 0
    assert calls == {"token": "t", "chat_id": "1", "text": "hi"}


def test_main_without_args_returns_nonzero(monkeypatch):
    monkeypatch.setattr(telegram, "send_text", lambda *a, **kw: None)
    with pytest.raises(SystemExit) as excinfo:
        telegram.main(["--token", "t", "--chat-id", "1"])
    assert excinfo.value.code != 0


def test_main_prints_json_result(monkeypatch, capsys):
    monkeypatch.setattr(
        telegram, "send_text", lambda *a, **kw: {"ok": True, "result": {}}
    )
    assert telegram.main(["--token", "t", "--chat-id", "1", "--text", "hi"]) == 0
    out = capsys.readouterr().out.strip()
    assert json.loads(out) == {"ok": True, "result": {}}