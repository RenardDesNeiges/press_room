"""Generate a static newspaper-style page from parsed_entries.yml."""

from __future__ import annotations

import re
import html
import difflib
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any

import yaml

from config import DEFAULT_PARSED_ENTRIES_PATH, DEFAULT_TEMPLATE_DIR


def load_parsed_data(
    path: str | Path = DEFAULT_PARSED_ENTRIES_PATH,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Load parsed entries, editorial, and title from a YAML file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return (
        data.get("entries", []),
        data.get("editorial"),
        data.get("title"),
    )


def get_french_weekday() -> str:
    """Return the current day of the week in French."""
    weekdays = [
        "lundi",
        "mardi",
        "mercredi",
        "jeudi",
        "vendredi",
        "samedi",
        "dimanche",
    ]
    return weekdays[datetime.now().weekday()]


def get_generated_at() -> str:
    """Return the current date and time in French."""
    months = [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    now = datetime.now()
    month = months[now.month - 1]
    return (
        f"{get_french_weekday()} {now.day} {month} {now.year} "
        f"à {now.hour:02d}h{now.minute:02d}"
    )


def format_inline(text: str) -> str:
    """Escape HTML entities and convert Markdown inline formatting to HTML."""
    # Protect Markdown links by replacing them with placeholders.
    links: list[str] = []

    def save_link(match: re.Match) -> str:
        link_text = html.escape(match.group(1), quote=False)
        url = html.escape(match.group(2), quote=True)
        links.append(
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">{link_text}</a>'
        )
        return f"\x00LINK{len(links) - 1}\x00"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", save_link, text)

    # Escape remaining HTML entities.
    text = html.escape(text, quote=False)

    # Bold: **text** or __text__
    text = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: f"<strong>{html.escape(m.group(1), quote=False)}</strong>",
        text,
    )
    text = re.sub(
        r"__(.+?)__",
        lambda m: f"<strong>{html.escape(m.group(1), quote=False)}</strong>",
        text,
    )

    # Italic: *text* or _text_
    text = re.sub(
        r"\*(.+?)\*",
        lambda m: f"<em>{html.escape(m.group(1), quote=False)}</em>",
        text,
    )
    text = re.sub(
        r"_(.+?)_",
        lambda m: f"<em>{html.escape(m.group(1), quote=False)}</em>",
        text,
    )

    # Restore Markdown links as HTML links.
    for index, link_html in enumerate(links):
        text = text.replace(f"\x00LINK{index}\x00", link_html)

    return text


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


def pick_feature_image(entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the article with a media image and the highest similarity_score."""
    candidates = [e for e in entries if e.get("media")]
    if not candidates:
        return None
    return max(candidates, key=lambda e: e.get("similarity_score") or 0)


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

    tags: list[str] = []
    for tag in ["theme", "country"]:
        value = entry.get(tag)
        if value:
            tags.append(f'<span class="article-tag">{html.escape(str(value), quote=False)}</span>')
    tags_html = f'<div class="article-tags">{" ".join(tags)}</div>' if tags else ""

    article_html = article_template.substitute(
        title=title,
        summary=summary,
        byline_html=byline_html,
        media_html=media_html,
        article_url=article_url,
        tags_html=tags_html,
    )
    source_key = re.sub(r"[\s]+", "-", (entry.get("source") or "").strip().lower())
    source_key = re.sub(r"[^a-z0-9\-]", "", source_key)
    if source_key:
        article_html = article_html.replace(
            '<article class="article">',
            f'<article class="article" data-source="{source_key}">',
            1,
        )
    return article_html


def top_counts(
    entries: list[dict[str, Any]], key: str, limit: int = 5
) -> list[tuple[str, int]]:
    """Return the top `limit` (label, count) pairs for a given entry field.

    All entries are considered (not just the remainder). Empty/None values are
    skipped. Ties are broken by raw value for deterministic ordering.
    """
    counts: dict[str, int] = {}
    for entry in entries:
        value = str(entry.get(key) or "").strip().lower()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ranked[:limit]


def render_stats_widget(entries: list[dict[str, Any]], limit: int = 8) -> str:
    """Render a headline-style widget with bar graphs.

    Shows the top journals by number of cited articles, and the top countries.
    Uses plain inline blocks sized via style width so no JS is required.
    """
    sources = top_counts(entries, "source", limit)
    countries = top_counts(entries, "country", limit)

    kept_countries = {
        label for label, _ in group_entries_by_country(entries) if label != "Autres"
    }
    kept_countries = {
        re.sub(r"[^a-z0-9\-]+", "-", label.lower()).strip("-")
        for label in kept_countries
    }

    distinct_sources = len({str(e.get("source") or "").strip().lower() for e in entries if (e.get("source") or "").strip()})
    distinct_themes = len({str(e.get("theme") or "").strip().lower() for e in entries if (e.get("theme") or "").strip()})
    distinct_countries = len(top_counts(entries, "country", limit=None))

    def bars(items: list[tuple[str, int]], kind: str) -> str:
        lines: list[str] = []
        if not items:
            return ""
        max_count = items[0][1]
        for label, count in items:
            width = 100.0 * count / max_count if max_count else 0.0
            label_clean = html.escape(label.capitalize(), quote=False)
            if kind == "source":
                key = re.sub(r"[\s]+", "-", label.strip().lower())
                key = re.sub(r"[^a-z0-9\-]", "", key)
                label_html = (
                    f'<span class="stats-bar-label">'
                    f'<a class="stats-bar-link" href="#" data-scroll-source="{key}">'
                    f"{label_clean}"
                    f"</a></span>"
                )
            else:
                key = normalize_country(label)
                section_id = re.sub(r"[^a-z0-9\-]+", "-", key.lower()).strip("-")
                if section_id not in kept_countries:
                    section_id = "autres"
                label_html = (
                    f'<span class="stats-bar-label">'
                    f'<a class="stats-bar-link" href="#section-{section_id}">'
                    f"{label_clean}"
                    f"</a></span>"
                )
            lines.append(
                '<div class="stats-bar-row">'
                f"{label_html}"
                '<div class="stats-bar-track">'
                f'<div class="stats-bar-fill anim" data-width="{width:.1f}" style="width: 0%"></div>'
                "</div>"
                f'<span class="stats-bar-value">{count}</span>'
                "</div>"
            )
        return "\n".join(lines)

    sources_html = bars(sources, "source")
    countries_html = bars(countries, "country")

    return (
        '<article class="article stats-widget">'
        '<h2 class="stats-widget-title">Édition en chiffres</h2>'
        '<h3 class="stats-widget-label">Journaux les plus cités</h3>'
        '<div class="stats-bars">'
        f"{sources_html}"
        "</div>"
        '<h3 class="stats-widget-label">Pays les plus cités</h3>'
        '<div class="stats-bars">'
        f"{countries_html}"
        "</div>"
        '<div class="stats-totals">'
        f"<span><strong>{len(entries)}</strong> articles</span>"
        f"<span><strong>{distinct_sources}</strong> sources</span>"
        f"<span><strong>{distinct_countries}</strong> pays</span>"
        f"<span><strong>{distinct_themes}</strong> thèmes</span>"
        "</div>"
        "</article>"
    )


def select_distinct_theme_leads(
    entries: list[dict[str, Any]], count: int = 2
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Pick up to `count` lead articles with distinct theme tags.

    Iterates over `entries` (already ordered by importance) and selects the
    first article for each distinct theme. Returns the selected leads and the
    remaining entries.
    """
    leads: list[dict[str, Any]] = []
    remainder: list[dict[str, Any]] = []
    seen_themes: set[str] = set()

    for entry in entries:
        theme = str(entry.get("theme") or "").strip().lower()
        if not theme or theme in seen_themes:
            remainder.append(entry)
            continue
        if len(leads) >= count:
            remainder.append(entry)
            continue
        leads.append(entry)
        seen_themes.add(theme)

    remaining_needed = count - len(leads)
    if remaining_needed > 0 and remainder:
        for entry in list(remainder):
            if remaining_needed <= 0:
                break
            leads.append(entry)
            remainder.remove(entry)
            remaining_needed -= 1

    return leads, remainder


CANONICAL_COUNTRIES = [
    "france", "suisse", "allemagne", "espagne", "italie", "royaume-uni",
    "etats-unis", "usa", "chine", "russie", "ukraine", "belgique", "luxembourg",
    "canada", "japon", "inde", "bresil", "argentine", "mexique", "cuba",
    "israel", "palestine", "maroc", "algerie", "tunisie", "turquie", "iran",
    "syrie", "afghanistan", "congo", "somalie", "autriche", "norvege",
    "suede", "finlande", "pologne", "portugal", "grece", "pays-bas",
    "allemand", "canadien",
]


def normalize_country(tag: str, cutoff: float = 0.78) -> str:
    """Fuzzy-match a country tag to a canonical name using difflib."""
    cleaned = (tag or "").strip().lower()
    if not cleaned:
        return "Divers"
    try:
        matches = difflib.get_close_matches(cleaned, CANONICAL_COUNTRIES, n=1, cutoff=cutoff)
    except TypeError:
        matches = []
    return matches[0] if matches else cleaned.capitalize()


def group_entries_by_country(entries: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Group entries into sections by country tag, ordered by descending count.

    Country tags are fuzzy-normalized to canonical names before grouping.
    Sections with the most articles are listed first. Entries without a country
    are grouped under "Divers".
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        country = normalize_country(entry.get("country"))
        groups.setdefault(country, []).append(entry)

    grouped = sorted(
        groups.items(),
        key=lambda item: len(item[1]),
        reverse=True,
    )

    keep: list[tuple[str, list[dict[str, Any]]]] = []
    others: list[dict[str, Any]] = []
    for label, country_entries in grouped:
        if len(country_entries) <= 2:
            others.extend(country_entries)
        else:
            keep.append((label, country_entries))

    if others:
        keep.append(("Autres", others))
    return keep


def load_template(name: str, template_dir: Path = DEFAULT_TEMPLATE_DIR) -> Template:
    """Load a string template from the templates directory."""
    template_path = template_dir / name
    with open(template_path, "r", encoding="utf-8") as fh:
        return Template(fh.read())


GRID_COLUMNS = 4


def build_country_flow(
    groups: list[tuple[str, list[dict[str, Any]]]],
    article_template: Template,
    columns: int = GRID_COLUMNS,
) -> str:
    """Render country groups as one continuous grid without breaking rows.

    Each section starts a fresh row with its title in the left cell and its
    articles flowing to the right, so the title always sits left of its own
    articles. Sections are assumed ordered by descending article count.
    """
    items: list[str] = []
    col_index = 0  # 0-based index of the next free cell in the current row

    def place(content: str, start: int, end: int) -> str:
        return (
            f'<div class="grid-item" style="grid-column: {start} / {end}">'
            f"{content}</div>"
        )

    for theme_title, theme_entries in groups:
        col_index = 0
        title = html.escape(theme_title, quote=False)
        section_id = re.sub(r"[^a-z0-9\-]+", "-", theme_title.lower()).strip("-")
        items.append(
            place(
                f'<h2 class="tag-section-title" id="section-{section_id}">{title}</h2>',
                col_index + 1,
                col_index + 2,
            )
        )
        col_index = 1

        for entry in theme_entries:
            items.append(
                place(render_article(entry, article_template), col_index + 1, col_index + 2)
            )
            col_index += 1
            if col_index >= columns:
                col_index = 0

    return "\n".join(items)


def build_html(
    entries: list[dict[str, Any]],
    editorial: str | None = None,
    headline: str | None = None,
    weekday: str | None = None,
    generated_at: str | None = None,
    site_title: str = "Pressroom",
    template_dir: Path = DEFAULT_TEMPLATE_DIR,
) -> str:
    """Build a black-and-white newspaper-style HTML page from templates."""
    article_template = load_template("article.html", template_dir)
    page_template = load_template("page.html", template_dir)

    lead_entries, remainder = select_distinct_theme_leads(entries, count=2)

    lead_articles_html = "\n".join(
        render_article(entry, article_template) for entry in lead_entries
    ) + "\n" + render_stats_widget(entries)

    groups = group_entries_by_country(remainder)
    articles_html = build_country_flow(groups, article_template)

    audio_player_html = ""
    editorial_content_html = ""
    if editorial:
        audio_player_html = (
            '<div class="audio-player">'
            '<audio preload="metadata">'
            '<source src="data/editorial.mp3" type="audio/mpeg">'
            "</audio>"
            '<button class="audio-play-button" type="button">▶ Écouter l\'édito</button>'
            '<span class="audio-time">0:00 / 0:00</span>'
            "</div>"
        )
        editorial_content_html = render_markdown(editorial)

    feature_image_html = ""
    featured = pick_feature_image(entries)
    if featured:
        image_url = html.escape(str(featured.get("media") or ""), quote=True)
        article_url = html.escape(str(featured.get("url") or "#"), quote=True)
        title = html.escape(str(featured.get("title") or "Untitled"), quote=False)
        source = html.escape(str(featured.get("source") or ""), quote=False)
        feature_image_html = (
            f'<figure class="feature-image">'
            f'<a href="{article_url}" target="_blank" rel="noopener noreferrer">'
            f'<img src="{image_url}" alt="{title}" loading="lazy">'
            f'</a>'
            f'<figcaption class="feature-caption">'
            f'<a href="{article_url}" target="_blank" rel="noopener noreferrer">'
            f"{title} · {source}"
            f"</a>"
            f"</figcaption>"
            f"</figure>"
        )

    headline_html = ""
    if headline:
        headline_html = (
            f'<div class="headline">'
            f'<p class="headline-day">{html.escape("Aggrégateur d'informations" or "", quote=False)}</p>'
            f'<a class="headline-link" href="#editorial">'
            f'<h1 class="headline-title">{html.escape(headline, quote=False)}</h1>'
            f'</a>'
            f'</div>'
        )

    return page_template.substitute(
        site_title=html.escape(site_title, quote=False),
        generated_at=html.escape(generated_at or "", quote=False),
        headline=headline_html,
        feature_image=feature_image_html,
        lead_articles=lead_articles_html,
        audio_player=audio_player_html,
        editorial_content=editorial_content_html,
        articles=articles_html,
        article_count=len(entries),
    )


def generate_page(
    parsed_entries_path: Path = DEFAULT_PARSED_ENTRIES_PATH,
    output_path: Path = Path("press_room.html"),
) -> Path:
    """Generate the static page from parsed entries.

    Copies the stylesheet alongside the generated HTML so relative references
    to ``page.css`` resolve. Returns the path to the generated HTML file.
    """
    css_src = DEFAULT_TEMPLATE_DIR / "page.css"
    if css_src.exists():
        css_dest = output_path.parent / "page.css"
        css_dest.write_text(css_src.read_text(encoding="utf-8"), encoding="utf-8")

    entries, editorial, title = load_parsed_data(parsed_entries_path)
    html_content = build_html(
        entries,
        editorial=editorial,
        headline=title,
        weekday=get_french_weekday(),
        generated_at=get_generated_at(),
    )

    output_path.write_text(html_content, encoding="utf-8")
    print(f"Generated {output_path} with {len(entries)} articles.")
    return output_path


def main() -> None:
    """Generate the static page from parsed entries."""
    generate_page()


if __name__ == "__main__":
    main()
