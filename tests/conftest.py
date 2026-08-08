"""Shared fixtures for the press-room Tier-1 test suite.

Tier 1 only exercises deterministic, pure (or lightly mocked) logic: no live
RSS fetches, LLM calls, WordLlama model downloads, TTS, or the SQLite database.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ``src/key.py`` holds the real (gitignored) OpenRouter API key. Modules that
# import it (rerank_llm → parse_feed, editorial_to_mp3) only need the name at
# import time — Tier-1 tests never call the API. On a fresh clone (no
# src/key.py) this stub keeps those imports (and so the suite) working.
if not (_PROJECT_ROOT / "src" / "key.py").exists() and "src.key" not in sys.modules:
    _key_stub = types.ModuleType("src.key")
    _key_stub.API_KEY = "test-only-openrouter-key"
    sys.modules["src.key"] = _key_stub


@pytest.fixture
def sample_entries():
    """A few realistic pipeline entries (the ``filtered_entries`` shape)."""
    return [
        {
            "EID": 1,
            "title": "Un article français",
            "summary": "Résumé en français.",
            "url": "https://mediapart.fr/articles/1",
            "date": "2026-08-06T08:00:00+00:00",
            "lang": "FR",
            "author": "A. Rédacteur",
            "source": "Mediapart",
        },
        {
            "EID": 2,
            "title": "A German report",
            "summary": "Summary about German politics.",
            "url": "https://www.nzz.ch/example",
            "date": "2026-08-06T09:30:00+00:00",
            "lang": "DE",
            "author": "B. Reporter",
            "source": "NZZ",
        },
        {
            "EID": 3,
            "title": "Another French piece",
            "summary": "Second Mediapart article.",
            "url": "https://mediapart.fr/articles/2",
            "date": "2026-08-06T10:00:00+00:00",
            "lang": "FR",
            "source": "Mediapart",
        },
    ]


@pytest.fixture
def feeds_config():
    """A publications-shaped feeds.yml payload."""

    return {
        "publications": [
            {
                "name": "Mediapart",
                "lang": "FR",
                "feeds": ["https://www.mediapart.fr/articles/feed"],
            },
            {
                "name": "NZZ",
                "lang": "DE",
                "today_only": True,
                "notes": "https://www.nzz.ch/startseite.rss",
            },
            {
                "name": "Sans Feeds",
                "lang": "FR",
                "notes": "pas une url",
            },
        ]
    }