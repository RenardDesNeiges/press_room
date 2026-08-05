"""Generate a static newspaper-style page from parsed_entries.yml."""

from __future__ import annotations

import re
import html
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any

import yaml

from config import DEFAULT_PARSED_ENTRIES_PATH, DEFAULT_TEMPLATE_DIR


def load_parsed_data(
    path: str | Path = DEFAULT_PARSED_ENTRIES_PATH,
) -> tuple[list[dict[str, Any]], str | None]:
    """Load parsed entries and optional editorial from a YAML file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("entries", []), data.get("editorial")


def format_inline(text: str) -> str:
    """Escape HTML entities and convert bold/italic Markdown to HTML tags."""
    escaped = html.escape(text, quote=False)

    # Bold: **text** or __text__
    escaped = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: f"<strong>{html.escape(m.group(1), quote=False)}</strong>",
        escaped,
    )
    escaped = re.sub(
        r"__(.+?)__",
        lambda m: f"<strong>{html.escape(m.group(1), quote=False)}</strong>",
        escaped,
    )

    # Italic: *text* or _text_
    escaped = re.sub(
        r"\*(.+?)\*",
        lambda m: f"<em>{html.escape(m.group(1), quote=False)}</em>",
        escaped,
    )
    escaped = re.sub(
        r"_(.+?)_",
        lambda m: f"<em>{html.escape(m.group(1), quote=False)}</em>",
        escaped,
    )

    return escaped


def render_markdown(markdown_text: str) -> str:
    """Convert simple Markdown to HTML (headers, paragraphs, bold, italic)."""
    lines = markdown_text.splitlines()
    html_lines: list[str] = []
    paragraph_buffer: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_buffer:
            content = " ".join(paragraph_buffer).strip()
            if content:
                html_lines.append(f"<p>{format_inline(content)}</p>")
            paragraph_buffer.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue

        if stripped.startswith("# "):
            flush_paragraph()
            html_lines.append(f"<h1>{format_inline(stripped[2:])}</h1>")
        elif stripped.startswith("## "):
            flush_paragraph()
            html_lines.append(f"<h2>{format_inline(stripped[3:])}</h2>")
        elif stripped.startswith("### "):
            flush_paragraph()
            html_lines.append(f"<h3>{format_inline(stripped[4:])}</h3>")
        else:
            paragraph_buffer.append(stripped)

    flush_paragraph()
    return "\n".join(html_lines)


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
    editorial: str | None = None,
    site_title: str = "press-room",
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
) -> str:
    """Build a black-and-white newspaper-style HTML page from templates."""
    article_template = load_template("article.html", template_dir)
    page_template = load_template("page.html", template_dir)

    lead_entries = entries[:4]
    grid_entries = entries[4:]

    lead_articles_html = "\n".join(
        render_article(entry, article_template) for entry in lead_entries
    )

    articles_html = "\n".join(
        render_article(entry, article_template) for entry in grid_entries
    )

    editorial_html = ""
    if editorial:
        editorial_html = f'<div class="editorial">\n{render_markdown(editorial)}\n</div>'

    return page_template.substitute(
        site_title=html.escape(site_title, quote=False),
        lead_articles=lead_articles_html,
        editorial=editorial_html,
        articles=articles_html,
        article_count=len(entries),
    )


def main() -> None:
    """Generate the static page from parsed entries."""
    entries, editorial = load_parsed_data()
    html_content = build_html(entries, editorial=editorial)

    output_path = Path("press_room.html")
    output_path.write_text(html_content, encoding="utf-8")
    print(f"Generated {output_path} with {len(entries)} articles.")


if __name__ == "__main__":
    main()
