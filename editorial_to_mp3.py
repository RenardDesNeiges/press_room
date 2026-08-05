"""Convert the parsed editorial to an MP3 using OpenRouter's Kokoro TTS."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
import yaml

from config import API_KEY, DEFAULT_PARSED_ENTRIES_PATH


DEFAULT_OUTPUT_PATH = Path("data/editorial.mp3")
DEFAULT_MODEL = "hexgrad/kokoro-82m"
DEFAULT_VOICE = "ff_siwis"  # French female voice; Kokoro preset
DEFAULT_ENDPOINT = "https://openrouter.ai/api/v1/audio/speech"


def load_editorial(path: Path = DEFAULT_PARSED_ENTRIES_PATH) -> str | None:
    """Load the editorial text from the parsed entries YAML file."""
    with open(path, "r", encoding="utf-8") as fh:
        data: dict[str, Any] = yaml.safe_load(fh)
    return data.get("editorial")


def text_to_speech(
    text: str,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    model: str = DEFAULT_MODEL,
    voice: str = DEFAULT_VOICE,
    endpoint: str = DEFAULT_ENDPOINT,
    api_key: str = API_KEY,
) -> Path:
    """Synthesize text to speech via OpenRouter and save it as an MP3."""
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
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

    return output_path


def main() -> None:
    """Generate an MP3 from the parsed editorial."""
    editorial = load_editorial()
    if not editorial:
        print("No editorial found in parsed entries.")
        return

    print(f"Synthesizing editorial to MP3 using {DEFAULT_MODEL} (voice: {DEFAULT_VOICE})...")
    output_path = text_to_speech(editorial)
    print(f"Saved MP3 to {output_path}")


if __name__ == "__main__":
    main()
