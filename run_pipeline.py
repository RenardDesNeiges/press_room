"""Run the full press-room pipeline end-to-end.

Steps:
  1. Scrape RSS feeds and write data/filtered_entries.yml
  2. Rank, rerank, translate and write data/parsed_entries.yml
  3. Classify entries into sections and write data/prepared_entries.yml
  4. Synthesize the editorial to data/editorial.mp3
  5. Generate press_room.html
"""

from __future__ import annotations

import time
from pathlib import Path

from config import (
    DEFAULT_ENTRIES_PATH,
    DEFAULT_MP3_PATH,
    DEFAULT_PARSED_ENTRIES_PATH,
    DEFAULT_PREPARED_ENTRIES_PATH,
)
from editorial_to_mp3 import generate_editorial_mp3
from feed_reader import scrape_feeds
from gen_static_page import generate_page
from parse_feed import parse_and_export
from prepare_entries import prepare_and_export


def timed_step(label: str, func: callable) -> None:
    """Run a pipeline step and print its duration."""
    print(f"\n>>> {label}")
    start = time.perf_counter()
    func()
    elapsed = time.perf_counter() - start
    print(f"    {label} completed in {elapsed:.1f}s")


def main() -> None:
    """Execute the complete pipeline."""
    overall_start = time.perf_counter()

    timed_step("Scrape RSS feeds", scrape_feeds)
    timed_step("Parse and rerank entries", parse_and_export)
    timed_step("Classify entries into sections", lambda: prepare_and_export(
        parsed_entries_path=DEFAULT_PARSED_ENTRIES_PATH,
        output_path=DEFAULT_PREPARED_ENTRIES_PATH,
    ))
    timed_step("Generate editorial audio", lambda: generate_editorial_mp3(
        parsed_entries_path=DEFAULT_PREPARED_ENTRIES_PATH,
        output_path=DEFAULT_MP3_PATH,
    ))
    timed_step("Generate static page", lambda: generate_page(
        parsed_entries_path=DEFAULT_PREPARED_ENTRIES_PATH,
        output_path=Path("press_room.html"),
    ))

    total = time.perf_counter() - overall_start
    print("\n=== Pipeline complete ===")
    print(f"Total time: {total:.1f}s")
    print("Generated files:")
    print(f"  - {DEFAULT_ENTRIES_PATH}")
    print(f"  - {DEFAULT_PARSED_ENTRIES_PATH}")
    print(f"  - {DEFAULT_PREPARED_ENTRIES_PATH}")
    print(f"  - {DEFAULT_MP3_PATH}")
    print(f"  - {Path('press_room.html').resolve()}")


if __name__ == "__main__":
    main()
