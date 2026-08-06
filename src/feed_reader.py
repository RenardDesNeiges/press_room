"""RSS feed reader for feeds listed in feeds.yml."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import feedparser
import yaml

from config import *


class HTMLStripper(HTMLParser):
    """Collect text content while ignoring HTML tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []

    def handle_data(self, data: str) -> None:
        self.text.append(data)

    def get_text(self) -> str:
        return "".join(self.text).strip()


def strip_html(value: str | None) -> str | None:
    """Remove HTML tags and decode entities from a string."""
    if not value:
        return None
    stripper = HTMLStripper()
    stripper.feed(value)
    return stripper.get_text() or None


def read_feeds_yaml(path: str | Path = DEFAULT_FEEDS_PATH) -> dict[str, Any]:
    """Read the feeds YAML file and return its contents as a dictionary."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def query_rss_feed(url: str) -> dict[str, Any] | None:
    """Query an RSS feed by URL and return its parsed data.

    Returns None if the feed cannot be parsed or the request fails.
    """
    parsed = feedparser.parse(url)
    if parsed.get("bozo_exception") and not parsed.get("entries"):
        return None
    return dict(parsed)


def parse_feed_date(entry: dict[str, Any]) -> datetime | None:
    """Extract and normalize the published/updated date from a feed entry."""
    for key in ("published_parsed", "updated_parsed"):
        if key in entry:
            dt = entry[key]
            if dt is not None:
                return datetime(*dt[:6], tzinfo=timezone.utc)
    return None


def collect_all_feeds(
    feeds_config: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Query all RSS feeds referenced in the configuration and return a dict.

    The returned structure maps feed URL -> {"feed": parsed_feed_data, "lang": lang, "source": source}.
    Feeds that fail to load are omitted.
    """
    if feeds_config is None:
        feeds_config = read_feeds_yaml()

    results: dict[str, dict[str, Any]] = {}
    for publication in feeds_config.get("publications", []):
        urls = publication.get("feeds", [])
        if not urls and "notes" in publication:
            note = publication["notes"]
            if note.startswith("http"):
                urls = [note]

        lang = publication.get("lang")
        source = publication.get("name")
        for url in urls:
            feed_data = query_rss_feed(url)
            if feed_data is not None:
                results[url] = {"feed": feed_data, "lang": lang, "source": source}

    return results


def filter_feeds_by_date(
    feeds: dict[str, dict[str, Any]],
    max_age: timedelta = timedelta(days=2),
    reference_date: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    """Filter feed entries by date.

    Returns a dict mapping feed URL -> {"entries": [...], "lang": lang, "source": source}
    for entries whose publication date is within `max_age` of `reference_date`
    (defaulting to UTC now).
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)

    filtered: dict[str, dict[str, Any]] = {}
    for url, meta in feeds.items():
        recent_entries = []
        for entry in meta["feed"].get("entries", []):
            entry_date = parse_feed_date(entry)
            if entry_date is not None and (reference_date - entry_date) <= max_age:
                recent_entries.append(entry)
        if recent_entries:
            filtered[url] = {
                "entries": recent_entries,
                "lang": meta.get("lang"),
                "source": meta.get("source"),
            }

    return filtered


def extract_media_url(entry: dict[str, Any]) -> str | None:
    """Try to extract a media URL from a feed entry."""
    if "media_content" in entry:
        for media in entry["media_content"]:
            url = media.get("url")
            if url:
                return url

    if "enclosures" in entry:
        for enclosure in entry["enclosures"]:
            url = enclosure.get("href")
            if url:
                return url

    for link in entry.get("links", []):
        if link.get("rel") == "enclosure":
            url = link.get("href")
            if url:
                return url

    return None


def extract_author(entry: dict[str, Any]) -> str | None:
    """Try to extract the author name from a feed entry."""
    author_detail = entry.get("author_detail")
    if isinstance(author_detail, dict):
        name = author_detail.get("name")
        if name:
            return name

    authors = entry.get("authors")
    if isinstance(authors, list):
        for author in authors:
            if isinstance(author, dict):
                name = author.get("name")
                if name:
                    return name
            elif isinstance(author, str):
                return author

    return entry.get("author")


def format_entry(
    entry: dict[str, Any],
    lang: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Convert a feedparser entry into the export schema."""
    entry_date = parse_feed_date(entry)
    return {
        "title": entry.get("title"),
        "summary": strip_html(entry.get("summary") or entry.get("description")),
        "media": extract_media_url(entry),
        "url": entry.get("link"),
        "date": entry_date.isoformat() if entry_date else None,
        "lang": lang,
        "author": extract_author(entry),
        "source": source,
    }


def flatten_filtered_entries(
    filtered: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flatten filtered entries grouped by feed URL into a single list."""
    entries: list[dict[str, Any]] = []
    eid = 1
    for meta in filtered.values():
        lang = meta.get("lang")
        source = meta.get("source")
        for entry in meta["entries"]:
            formatted = format_entry(entry, lang=lang, source=source)
            formatted["EID"] = eid
            entries.append(formatted)
            eid += 1
    return entries


def export_entries_yaml(
    entries: list[dict[str, Any]],
    path: str | Path = DEFAULT_ENTRIES_PATH,
) -> None:
    """Export a list of entries to a YAML file in the requested schema."""
    payload = {"entries": entries}
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(
            payload,
            fh,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


def scrape_feeds(
    feeds_path: str | Path = DEFAULT_FEEDS_PATH,
    output_path: str | Path = DEFAULT_ENTRIES_PATH,
) -> list[dict[str, Any]]:
    """Scrape all configured feeds and export the recent entries.

    Returns the list of exported entries.
    """
    feeds = collect_all_feeds(read_feeds_yaml(feeds_path))

    print("Successfully loaded feeds:")
    for url in feeds:
        print(f"  - {url}")

    recent = filter_feeds_by_date(feeds, max_age=timedelta(days=1))

    export_entries = flatten_filtered_entries(recent)
    export_entries_yaml(export_entries, path=output_path)
    print(f"\nExported {len(export_entries)} entries to {output_path}")
    return export_entries


def main() -> None:
    """Provisional main: load all feeds and export recent entries."""
    scrape_feeds()


if __name__ == "__main__":
    main()
