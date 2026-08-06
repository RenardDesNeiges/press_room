"""Convert the parsed editorial to an MP3 using OpenRouter's Kokoro TTS."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import re

import requests
import yaml

from key import API_KEY
from config import DEFAULT_MP3_PATH, DEFAULT_PREPARED_ENTRIES_PATH


DEFAULT_OUTPUT_PATH = DEFAULT_MP3_PATH
DEFAULT_MODEL = "mistralai/voxtral-mini-tts-2603:nitro"
DEFAULT_VOICE = "fr_marie_curious"  # French female voice for Mistral TTS
DEFAULT_ENDPOINT = "https://openrouter.ai/api/v1/audio/speech"
DEFAULT_HTTP_REFERER = "https://pressroom.local"
DEFAULT_APP_TITLE = "Pressroom"


def load_editorial(path: Path = DEFAULT_PREPARED_ENTRIES_PATH) -> str | None:
    """Load the editorial text from the prepared entries YAML file."""
    with open(path, "r", encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    return data.get("editorial")


def strip_markdown(text: str) -> str:
    """Remove common Markdown syntax and return plain text suitable for TTS."""
    # Headers: # text, ## text, ### text
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Links: [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)

    # Bold and italic markers: **text**, *text*, __text__, _text_ -> text
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    text = re.sub(r"_(.+?)_", r"\1", text)

    # Blockquotes and list markers at line start
    text = re.sub(r"^[>\-\*+]\s+", "", text, flags=re.MULTILINE)

    # Horizontal rules
    text = re.sub(r"^\s*[-=*]{3,}\s*$", "", text, flags=re.MULTILINE)

    # Collapse multiple blank lines
    text = re.sub(r"\n\s*\n+", "\n\n", text)

    return text.strip()


def text_to_speech(
    text: str,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    model: str = DEFAULT_MODEL,
    voice: str = DEFAULT_VOICE,
    endpoint: str = DEFAULT_ENDPOINT,
    api_key: str = API_KEY,
    http_referer: str = DEFAULT_HTTP_REFERER,
    app_title: str = DEFAULT_APP_TITLE,
) -> Path:
    """Synthesize text to speech via OpenRouter and save it as an MP3."""
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": http_referer,
            "X-OpenRouter-Title": app_title,
        },
        json={
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": "mp3",
        },
        timeout=120,
    )
    response.raise_for_status()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as fh:
        fh.write(response.content)

    generation_id = response.headers.get("X-Generation-Id")
    if generation_id:
        print(f"Generation ID: {generation_id}")

    return output_path


def generate_editorial_mp3(
    parsed_entries_path: Path = DEFAULT_PREPARED_ENTRIES_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
) -> Path | None:
    """Generate an MP3 from the parsed editorial.

    Returns the path to the generated MP3, or None if no editorial exists.
    """
    editorial = load_editorial(parsed_entries_path)
    if not editorial:
        print("No editorial found in parsed entries.")
        return None

    plain_text = strip_markdown(editorial)
    print(
        f"Synthesizing editorial to MP3 using {DEFAULT_MODEL} (voice: {DEFAULT_VOICE})..."
    )
    generated_path = text_to_speech(plain_text, output_path=output_path)
    print(f"Saved MP3 to {generated_path}")
    return generated_path


def main() -> None:
    """Generate an MP3 from the parsed editorial."""
    generate_editorial_mp3()


if __name__ == "__main__":
    main()
