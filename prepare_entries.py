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
from pathlib import Path
from typing import Any

import yaml

from config import (
    DEFAULT_INTERESTS_PATH,
    DEFAULT_PARSED_ENTRIES_PATH,
    DEFAULT_PREPARED_ENTRIES_PATH,
    DEFAULT_SECTION_MODEL,
    DEFAULT_SECTION_SIZE,
    DEFAULT_TITLE_GUIDE_PATH,
    FANCY_MODEL,
)
from rerank_llm import extract_json_list, query_model


DEFAULT_EDITO_PATH = Path("data/edito.md")


def load_edito_prompt(
    edito_path: Path = DEFAULT_EDITO_PATH,
) -> str:
    """Load the editorial prompt template from a Markdown file."""
    with open(edito_path, "r", encoding="utf-8") as fh:
        return fh.read()


def build_edito_prompt(
    entries: list[dict[str, Any]],
    edito_path: Path = DEFAULT_EDITO_PATH,
    interests_path: Path = DEFAULT_INTERESTS_PATH,
) -> str:
    """Fill the editorial prompt template with the RSS feed and user preferences."""
    prompt_template = load_edito_prompt(edito_path)

    # Convert the selected entries to a clean YAML string.
    rss_feed_yaml = yaml.safe_dump(
        {"entries": entries},
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )

    with open(interests_path, "r", encoding="utf-8") as fh:
        user_preferences = fh.read()

    return (
        prompt_template.replace("{ rss_feed_yaml }", rss_feed_yaml)
        .replace("{ user_preferences.md }", user_preferences.split('-----')[1])
    )


def generate_editorial(
    entries: list[dict[str, Any]],
    edito_path: Path = DEFAULT_EDITO_PATH,
    interests_path: Path = DEFAULT_INTERESTS_PATH,
    model_name: str = FANCY_MODEL,
) -> str:
    """Generate an editorial from the selected entries using FANCY_MODEL."""
    prompt = build_edito_prompt(entries, edito_path, interests_path)
    print(f"Generating editorial with {model_name}...")
    editorial = query_model(prompt, model_name=model_name, temperature=0.7)
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
- "title": the section title (1-2 words, French)
- "EIDs": the list of integer EIDs assigned to this section

Example output format:
[
  {{"title": "Présidentielle", "EIDs": [12, 5, 7]}},
  {{"title": "Ukraine", "EIDs": [3, 9]}},
  {{"title": "Économie", "EIDs": [1, 4, 8, 11]}}
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
            eids = [int(e) for e in eids_raw if isinstance(e, (int, float))]
        else:
            eids = []
        sections.append({"title": title, "EIDs": eids})
    return sections


def assign_sections(
    entries: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach a "section" field to each entry, keeping LLM section order.

    Entries not mentioned in the LLM response are grouped under "Autres".
    """
    section_by_eid: dict[int, str] = {}
    for section in sections:
        for eid in section["EIDs"]:
            section_by_eid.setdefault(eid, section["title"])

    assigned: list[dict[str, Any]] = []
    leftover: list[dict[str, Any]] = []
    for entry in entries:
        section = section_by_eid.get(int(entry.get("EID") or -1))
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
        sections = [{"title": "Autres", "EIDs": [int(e.get("EID") or -1) for e in entries]}]

    prepared = assign_sections(entries, sections)
    print(f"Classified into {len(sections)} sections "
          f"(sizes: {[len(s['EIDs']) for s in sections]}).")
    return prepared


def prepare_and_export(
    parsed_entries_path: Path = DEFAULT_PARSED_ENTRIES_PATH,
    output_path: Path = DEFAULT_PREPARED_ENTRIES_PATH,
    section_size: int = DEFAULT_SECTION_SIZE,
    model_name: str = DEFAULT_SECTION_MODEL,
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Load parsed entries, classify into sections, and export prepared YAML."""
    with open(parsed_entries_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    entries = data.get("entries", [])
    prepared = prepare_entries(entries, section_size=section_size, model_name=model_name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"entries": prepared}
    if data.get("editorial") is not None:
        payload["editorial"] = data["editorial"]
    if data.get("title") is not None:
        payload["title"] = data["title"]
    with open(output_path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(
            payload,
            fh,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    print(f"Exported {len(prepared)} prepared entries to {output_path}")
    return prepared, payload.get("editorial"), payload.get("title")


def main() -> None:
    """Run the section-classification step."""
    prepare_and_export()


if __name__ == "__main__":
    main()
