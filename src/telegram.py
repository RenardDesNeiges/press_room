"""Minimal client for the Telegram Bot HTTP API.

Callers pass the bot token + chat id explicitly (no DB access here); the
corresponding per-user storage lives in ``src/db.py``. Every ``send_*`` helper
silently returns None when the bot is not configured (token == "none" or
missing chat id).

CLI for debugging/checking the module::

    python -m src.telegram --token <TOKEN> --chat-id <ID> --text "Hello"
    python -m src.telegram --token <TOKEN> --chat-id <ID> --audio path/to/editorial.mp3

The JSON API result is printed to stdout; the process exits 0 on success.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests


DEFAULT_TOKEN = "none"
API_BASE = "https://api.telegram.org/bot{token}"


def _is_configured(token: str, chat_id: str) -> bool:
    """Return True when token and chat_id are set and the token is real."""
    return bool(token) and bool(chat_id) and token != DEFAULT_TOKEN


def _post(token: str, method: str, *, json: dict | None = None,
          data: dict | None = None, files: dict | None = None, timeout: int = 30) -> dict:
    """POST to a bot API method and return the JSON result, raising on failure."""
    url = f"{API_BASE.format(token=token)}/{method}"
    response = requests.post(url, json=json, data=data, files=files, timeout=timeout)
    payload = response.json()
    if not payload.get("ok"):
        description = payload.get("description") or "unknown error"
        raise RuntimeError(f"Telegram API error: {description}")
    return payload


def send_text(token: str, chat_id: str, text: str) -> dict | None:
    """Send a text message. Returns the API result dict, or None when the bot is not configured."""
    if not _is_configured(token, chat_id):
        return None
    return _post(
        token,
        "sendMessage",
        json={"chat_id": chat_id, "text": text},
    )


def send_audio(
    token: str,
    chat_id: str,
    audio_bytes: bytes,
    filename: str = "editorial.mp3",
    caption: str = "",
    link: dict | None = None,
    media: str | None = None,
) -> dict | None:
    """Send an audio file (raw bytes) with an optional caption. Returns the API
    result dict, or None when the bot is not configured."""
    if not _is_configured(token, chat_id):
        return None
    data: dict = {"chat_id": chat_id, "parse_mode": "MarkdownV2"}
    if caption:
        data["caption"] = caption

    if link:
        # Build the keyboard dict, then serialize it to a JSON string
        keyboard = {
            "inline_keyboard": [
                [{"text": link['text'], "url": link['url']}]
            ]
        }
        data["reply_markup"] = json.dumps(keyboard)  

    if media:
        data["photo"] = media

    return _post(
        token,
        "sendAudio",
        data=data,
        files={"audio": (filename, audio_bytes, "audio/mpeg")},
        timeout=60,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: send a text and/or audio message to a chat.

    ``--token`` and ``--chat-id`` are required; at least one of ``--text`` or
    ``--audio`` must be given. Prints the JSON result to stdout.
    """
    parser = argparse.ArgumentParser(prog="python -m src.telegram")
    parser.add_argument("--token", required=True, help="Telegram bot token")
    parser.add_argument("--chat-id", required=True, help="Target chat id")
    parser.add_argument("--text", help="Text message to send")
    parser.add_argument("--audio", help="Path to an audio file (e.g. editorial.mp3)")
    args = parser.parse_args(argv)

    if not args.text and not args.audio:
        parser.error("at least one of --text or --audio is required")

    if args.text:
        result = send_text(args.token, args.chat_id, args.text)
        print(json.dumps(result, ensure_ascii=False))
    if args.audio:
        path = Path(args.audio)
        audio_bytes = path.read_bytes()
        result = send_audio(args.token, args.chat_id, audio_bytes, filename=path.name)
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())