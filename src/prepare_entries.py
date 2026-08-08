"""Classify parsed entries into editorial sections and write the editorial.

This is step 3 of the pipeline. It reads data/parsed_entries.yml, writes the
editorial (using FANCY_MODEL) and headline, then groups the articles into
"sections" of approximately `section_size` articles each. Sections are titled
with 1-2 words. Only the title, themes, and countries are sent to the section
LLM (not the summaries) to keep costs low.

The result is written to data/prepared_entries.yml with each entry carrying a
"section" field.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from src.config import (
    DATA_DIR,
    DEFAULT_EDITORIAL_MINUTES,
    DEFAULT_INTERESTS_PATH,
    DEFAULT_PARSED_ENTRIES_PATH,
    DEFAULT_PREPARED_ENTRIES_PATH,
    DEFAULT_SECTION_MODEL,
    DEFAULT_SECTION_SIZE,
    DEFAULT_TITLE_GUIDE_PATH,
    FANCY_MODEL,
)
from src.rerank_llm import extract_json_list, query_model


DEFAULT_EDITO_PATH = DATA_DIR / "edito.md"


def minutes_to_word_range(minutes: int) -> tuple[int, int]:
    """Derive the editorial word range from the target read time in minutes.

    word_min / word_max = 200 * minutes - 150 / + 150, clamped to 2-10 minutes.
    """
    minutes = max(2, min(10, int(minutes)))
    center = 200 * minutes
    return center - 150, center + 150


def load_edito_prompt(
    edito_path: Path = DEFAULT_EDITO_PATH,
) -> str:
    """Load the editorial prompt template from a Markdown file."""
    with open(edito_path, "r", encoding="utf-8") as fh:
        return fh.read()


def _editorial_prompt_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip every URL from the entries sent to the editorial LLM.

    Each article is identified only by its EID, exposed as a markdown link of
    the form ``[*<title>*](EID)`` so the LLM can cite sources without seeing the
    actual article URLs. Those links are resolved back to URLs afterwards by
    ``resolve_editorial_links``.
    """
    refs: list[dict[str, Any]] = []
    for entry in entries:
        eid = entry.get("EID")
        title = entry.get("title") or "Untitled"
        refs.append(
            {
                "EID": eid,
                "reference": f"[*{title}*]({eid})",
                "source": entry.get("source") or "",
                "summary": (entry.get("summary") or "")[:300],
                "theme": entry.get("theme") or "",
                "country": entry.get("country") or "",
                "date": entry.get("date") or "",
            }
        )
    return refs


def resolve_editorial_links(
    editorial: str, entries: list[dict[str, Any]]
) -> str:
    """Replace EID-based markdown links with the articles' real URLs.

    The editorial LLM cites sources as ``[text](EID)`` (EID never leaks a URL).
    This maps each EID back to its article URL so the stored editorial carries
    working links. EIDs without a matching URL are left untouched.
    """
    if not editorial:
        return editorial
    url_by_eid = {
        str(entry.get("EID")): entry.get("url")
        for entry in entries
        if entry.get("url")
    }
    resolved = editorial
    for eid, url in url_by_eid.items():
        # Match both the plain ``](EID)`` form and a bracketed ``](<EID>)`` form.
        resolved = resolved.replace(f"]({eid})", f"]({url})")
        resolved = resolved.replace(f"](<{eid}>)", f"]({url})")
    return resolved


def build_edito_prompt(
    entries: list[dict[str, Any]],
    edito_path: Path = DEFAULT_EDITO_PATH,
    interests_path: Path = DEFAULT_INTERESTS_PATH,
    word_min: int | None = None,
    word_max: int | None = None,
) -> str:
    """Fill the editorial prompt template with the RSS feed and user preferences.

    ``word_min``/``word_max`` bound the requested editorial length (in words) and
    are substituted into the ``{ word_min }`` / ``{ word_max }`` placeholders.

    The entries are passed WITHOUT their URLs: each article is exposed under its
    EID, cited as ``[text](EID)`` (see ``resolve_editorial_links``).
    """
    prompt_template = load_edito_prompt(edito_path)

    if word_min is None or word_max is None:
        word_min, word_max = minutes_to_word_range(DEFAULT_EDITORIAL_MINUTES)

    # Convert the selected entries to a clean YAML string, dropping URLs.
    rss_feed_yaml = yaml.safe_dump(
        {"entries": _editorial_prompt_entries(entries)},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )

    with open(interests_path, "r", encoding="utf-8") as fh:
        user_preferences = fh.read()

    return (
        prompt_template.replace("{ rss_feed_yaml }", rss_feed_yaml)
        .replace("{ user_preferences.md }", user_preferences.split('-----')[1])
        .replace("{ word_min }", str(word_min))
        .replace("{ word_max }", str(word_max))
    )


def generate_editorial(
    entries: list[dict[str, Any]],
    edito_path: Path = DEFAULT_EDITO_PATH,
    interests_path: Path = DEFAULT_INTERESTS_PATH,
    model_name: str = FANCY_MODEL,
    word_min: int | None = None,
    word_max: int | None = None,
) -> str:
    """Generate an editorial from the selected entries using FANCY_MODEL."""
    prompt = build_edito_prompt(entries, edito_path, interests_path, word_min, word_max)
    print(f"Generating editorial with {model_name}...")
    editorial = query_model(prompt, model_name=model_name, temperature=0.7)
    editorial = resolve_editorial_links(editorial, entries)
    return editorial.strip()


def extract_editorial_title(
    editorial: str,
    model_name: str = DEFAULT_SECTION_MODEL,
    guide: str = DEFAULT_TITLE_GUIDE_PATH,
) -> str:
    """Extract a short headline from the editorial using a cheap LLM."""
    prompt = (
        "Voici un guide d'écriture d'éditorial"
        f"{guide}"
        "À partir de l'éditorial suivant, extrais un titre de journal percutant "
        "(maximum 10 mots) qui résume le thème principal."
        "Ne renvoie que le titre, sans guillemets ni explication.\n\n"
        f"Éditorial :\n{editorial}"
    )
    print(f"Extracting editorial title with {model_name}...")
    title = query_model(prompt, model_name=model_name, temperature=0.3)
    return title.strip().strip('"').strip("'")


def build_section_prompt(entries: list[dict[str, Any]], section_size: int = 5) -> str:
    """Build the prompt asking the LLM to group entries into sections."""
    lines = []
    for entry in entries:
        eid = entry.get("EID", "?")
        title = entry.get("title") or "Untitled"
        theme = entry.get("theme") or ""
        country = entry.get("country") or ""
        lines.append(f"[{eid}] {title}\n    Thèmes: {theme} | Pays: {country}")

    entries_block = "\n".join(lines)

    return f"""You are an editorial desk director organizing today's press review into thematic sections.

GROUP THE FOLLOWING ARTICLES into thematic sections of approximately {section_size} articles each ({section_size - 1} to {section_size + 1} per section is acceptable).

RULES:
- A section groups articles that belong together thematically (same story, same topic, same region or closely related subjects).
- The section title must be 1 or 2 words maximum, in French, concise and evocative (e.g. "Présidentielle", "Guerre en Ukraine", "Économie", "Climat", "Amériques").
- You must assign EVERY article to exactly one section. Do not drop any article.
- Create as many sections as needed to cover all articles.
- Order sections by importance, from most to least important.

ARTICLE LIST (EID, title, themes, countries):
{entries_block}

OUTPUT FORMAT:
Return ONLY a JSON array where each element is an object with:
- "title": the section title (1-2 words listed in French)
- "EIDs": the list of EIDs assigned to this section (copy each EID EXACTLY as shown, with no changes)

Example output format:
[
  {{"title": "Présidentielle", "EIDs": ["12", "5", "7"]}},
  {{"title": "Ukraine", "EIDs": ["3", "9"]}},
  {{"title": "Économie", "EIDs": ["1", "4", "8", "11"]}}
]

Return ONLY the JSON array, with no other text.
"""


def parse_sections(response_text: str | None) -> list[dict[str, Any]]:
    """Parse the LLM response into a list of {title, EIDs} dicts."""
    if not response_text:
        return []
    data = extract_json_list(response_text)
    if data is None:
        return []
    sections: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        eids_raw = item.get("EIDs")
        if isinstance(eids_raw, int):
            eids = [eids_raw]
        elif isinstance(eids_raw, list):
            eids = []
            for e in eids_raw:
                if isinstance(e, bool):
                    continue
                if isinstance(e, int):
                    eids.append(e)
                elif isinstance(e, float) and e.is_integer():
                    eids.append(int(e))
                elif isinstance(e, str) and re.search(r"[0-9]", e):
                    eids.append(e)
        else:
            eids = []
        sections.append({"title": title, "EIDs": eids})
    return sections


def _normalise_eid(value: Any) -> str | None:
    """Normalise an EID for comparison (int and string forms both match)."""
    if value is None:
        return None
    return str(value).strip()


def assign_sections(
    entries: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach a "section" field to each entry, keeping LLM section order.

    Entries not mentioned in the LLM response are grouped under "Autres".
    """
    section_by_eid: dict[str, str] = {}
    for section in sections:
        for eid in section["EIDs"]:
            key = _normalise_eid(eid)
            if key:
                section_by_eid.setdefault(key, section["title"])

    assigned: list[dict[str, Any]] = []
    leftover: list[dict[str, Any]] = []
    for entry in entries:
        key = _normalise_eid(entry.get("EID"))
        section = section_by_eid.get(key) if key else None
        if section:
            enriched = dict(entry)
            enriched["section"] = section
            assigned.append(enriched)
        else:
            leftover.append(dict(entry))

    if leftover:
        for entry in leftover:
            entry["section"] = "Autres"
            assigned.append(entry)

    return assigned


def prepare_entries(
    entries: list[dict[str, Any]],
    section_size: int = DEFAULT_SECTION_SIZE,
    model_name: str = DEFAULT_SECTION_MODEL,
) -> list[dict[str, Any]]:
    """Classify entries into sections using an LLM."""
    if not entries:
        return []

    prompt = build_section_prompt(entries, section_size=section_size)
    print(f"Classifying {len(entries)} entries into sections with {model_name}...")
    response_text = query_model(prompt, model_name=model_name, max_tokens=32000)
    sections = parse_sections(response_text)

    if not sections:
        print("WARNING: no valid sections returned by LLM; grouping all under 'Autres'.")
        sections = [{"title": "Autres", "EIDs": [e.get("EID") for e in entries]}]

    prepared = assign_sections(entries, sections)
    print(f"Classified into {len(sections)} sections "
          f"(sizes: {[len(s['EIDs']) for s in sections]}).")
    return prepared


def prepare_and_export(
    parsed_entries_path: Path = DEFAULT_PARSED_ENTRIES_PATH,
    output_path: Path = DEFAULT_PREPARED_ENTRIES_PATH,
    section_size: int = DEFAULT_SECTION_SIZE,
    model_name: str = DEFAULT_SECTION_MODEL,
    interests_path: Path = DEFAULT_INTERESTS_PATH,
    edito_path: Path = DEFAULT_EDITO_PATH,
    editorial_minutes: int | None = None,
) -> tuple[list[dict[str, Any]], str, str]:
    """Load parsed entries, write the editorial + headline, classify into sections, and export.

    Generates the editorial and headline from the parsed entries, then groups
    them into sections. Returns the prepared entries, the editorial, and the
    headline.
    """
    with open(parsed_entries_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    entries = data.get("entries", [])
    prepared = prepare_entries(entries, section_size=section_size, model_name=model_name)

    word_min = word_max = None
    if editorial_minutes is not None:
        word_min, word_max = minutes_to_word_range(editorial_minutes)

    editorial = generate_editorial(
        entries,
        edito_path=edito_path,
        interests_path=interests_path,
        word_min=word_min,
        word_max=word_max,
    )
    title = extract_editorial_title(editorial)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"entries": prepared}
    if editorial is not None:
        payload["editorial"] = editorial
    if title is not None:
        payload["title"] = title
    with open(output_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(
            payload,
            fh,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    print(f"Exported {len(prepared)} prepared entries to {output_path}")
    return prepared, editorial, title


def main() -> None:
    """Run the section-classification step."""
    prepare_and_export()


if __name__ == "__main__":
    main()
