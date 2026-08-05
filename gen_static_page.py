"""Generate a static newspaper-style page from filtered_entries.yml."""

from __future__ import annotations

import html
import random
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any

import yaml


DEFAULT_TEMPLATE_DIR = Path(__file__).parent / "templates"


def load_entries(path: str | Path = "filtered_entries.yml") -> list[dict[str, Any]]:
    """Load filtered entries from a YAML file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("entries", [])


def shorten_summary(text: str | None, max_length: int = 280) -> str:
    """Return a shortened plain-text summary."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    truncated = text[:max_length].rsplit(" ", 1)[0]
    return truncated + "…"


def format_date(date_value: str | None) -> str:
    """Format an ISO date string for display."""
    if not date_value:
        return ""
    try:
        dt = datetime.fromisoformat(date_value)
        return dt.strftime("%d %B %Y")
    except ValueError:
        return date_value


def select_entries(
    entries: list[dict[str, Any]], count: int = 20
) -> list[dict[str, Any]]:
    """Randomly select a given number of entries."""
    if len(entries) <= count:
        return entries
    return random.sample(entries, count)


def render_article(entry: dict[str, Any], article_template: Template) -> str:
    """Render a single article using the article template."""
    title = html.escape(entry.get("title") or "Untitled", quote=False)
    summary = html.escape(shorten_summary(entry.get("summary")), quote=False)
    author = html.escape(entry.get("author") or "", quote=False)
    source = html.escape(entry.get("source") or "", quote=False)
    date = html.escape(format_date(entry.get("date")), quote=False)
    media_url = entry.get("media")
    article_url = html.escape(entry.get("url") or "#")

    media_html = ""
    if media_url:
        media_html = f'<img src="{html.escape(media_url)}" alt="" loading="lazy">'

    byline = " · ".join(part for part in [source, author, date] if part)
    byline_html = f'<p class="article-byline">{byline}</p>' if byline else ""

    return article_template.substitute(
        title=title,
        summary=summary,
        byline_html=byline_html,
        media_html=media_html,
        article_url=article_url,
    )


def load_template(name: str, template_dir: Path = DEFAULT_TEMPLATE_DIR) -> Template:
    """Load a string template from the templates directory."""
    template_path = template_dir / name
    with open(template_path, "r", encoding="utf-8") as fh:
        return Template(fh.read())


def build_html(
    entries: list[dict[str, Any]],
    site_title: str = "press-room",
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
) -> str:
    """Build a black-and-white newspaper-style HTML page from templates."""
    article_template = load_template("article.html", template_dir)
    page_template = load_template("page.html", template_dir)

    articles_html = "\n".join(
        render_article(entry, article_template) for entry in entries
    )

    return page_template.substitute(
        site_title=html.escape(site_title, quote=False),
        articles=articles_html,
        article_count=len(entries),
    )


def main() -> None:
    """Generate the static page."""
    entries = load_entries()
    selected = select_entries(entries, count=20)
    html_content = build_html(selected)

    output_path = Path("press_room.html")
    output_path.write_text(html_content, encoding="utf-8")
    print(f"Generated {output_path} with {len(selected)} articles.")


if __name__ == "__main__":
    main()
