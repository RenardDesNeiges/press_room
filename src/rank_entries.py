"""Rank filtered feed entries by similarity to readers_interests.md using WordLlama."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wordllama import WordLlama

from src.config import *


def load_interests(path: str | Path = DEFAULT_INTERESTS_PATH) -> str:
    """Load the readers' interests text from a Markdown file."""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def build_candidate_text(entry: dict[str, Any]) -> str:
    """Combine title and summary into a single candidate string."""
    title = entry.get("title") or ""
    summary = entry.get("summary") or ""
    parts = [part for part in (title, summary) if part]
    return "\n".join(parts)


def rank_entries(
    entries: list[dict[str, Any]],
    interests_path: str | Path = DEFAULT_INTERESTS_PATH,
) -> list[dict[str, Any]]:
    """Rank entries by semantic similarity to the readers' interests.

    Returns the entries sorted from highest to lowest match score, with a
    "similarity_score" field added to each entry.
    """
    if not entries:
        return []

    query = load_interests(interests_path)
    candidates = [build_candidate_text(entry) for entry in entries]

    wl = WordLlama.load()
    ranked = wl.rank(query, candidates)

    # Build a mapping from candidate text to score.
    score_by_text = {text: float(score) for text, score in ranked}

    scored_entries = []
    for entry in entries:
        candidate_text = build_candidate_text(entry)
        enriched = dict(entry)
        enriched["similarity_score"] = score_by_text.get(candidate_text, 0.0)
        scored_entries.append(enriched)

    scored_entries.sort(key=lambda e: e["similarity_score"], reverse=True)
    return scored_entries


def main() -> None:
    """CLI smoke test: load filtered_entries.yml, rank, and print top 10."""
    import yaml

    with open(DEFAULT_ENTRIES_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    ranked = rank_entries(data.get("entries", []))
    for entry in ranked[:10]:
        print(
            f"{entry['similarity_score']:.4f} · {entry.get('source', 'Unknown')} · "
            f"{entry.get('title', 'Untitled')}"
        )


if __name__ == "__main__":
    main()
