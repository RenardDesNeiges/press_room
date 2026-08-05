"""Parse filtered entries by semantic similarity + LLM reranking.

This is step 2 of the pipeline. It reads data/filtered_entries.yml,
selects the top candidates by WordLlama similarity, reranks them with an LLM
for diversity and importance, and writes the result to data/parsed_entries.yml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from config import (
    DEFAULT_CANDIDATES_COUNT,
    DEFAULT_ENTRIES_PATH,
    DEFAULT_FINAL_COUNT,
    DEFAULT_MODEL,
    DEFAULT_INTERESTS_PATH,
    DEFAULT_PARSED_ENTRIES_PATH,
    FANCY_MODEL,
)
from rank_entries import rank_entries
from rerank_llm import query_model, rerank_with_llm


DEFAULT_EDITO_PATH = Path("data/edito.md")


def load_entries(path: Path = DEFAULT_ENTRIES_PATH) -> list[dict[str, Any]]:
    """Load filtered entries from a YAML file."""
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("entries", [])


def export_entries_yaml(
    entries: list[dict[str, Any]],
    editorial: str | None = None,
    path: Path = DEFAULT_PARSED_ENTRIES_PATH,
) -> None:
    """Export entries and an optional editorial to a YAML file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"entries": entries}
    if editorial is not None:
        payload["editorial"] = editorial
    with open(path, "w", encoding="utf-8") as fh:
        yaml.safe_dump(
            payload,
            fh,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )


def translate_to_french(text: str, model_name: str = DEFAULT_MODEL) -> str:
    """Translate a single text to French using an LLM."""
    if not text or not text.strip():
        return text

    prompt = (
        "Translate the following text into French. "
        "Preserve the original meaning, tone, and formatting. "
        "Do not add explanations, notes, or quotation marks around the output. "
        "Return only the translation.\n\n"
        f"Text:\n{text}"
    )

    translation = query_model(prompt, model_name=model_name, temperature=0.2)
    return translation.strip()


def translate_entry(
    entry: dict[str, Any], model_name: str = DEFAULT_MODEL
) -> dict[str, Any]:
    """Translate an entry's textual fields to French.

    Articles already in French are not re-translated, but the rerank reason
    (always generated in English) is still translated.
    """
    translated = dict(entry)
    already_french = str(translated.get("lang", "")).upper() == "FR"

    fields_to_translate = ["rerank_reason"]
    if not already_french:
        fields_to_translate.extend(["title", "summary"])

    for field in fields_to_translate:
        original = translated.get(field)
        if isinstance(original, str) and original.strip():
            translated[field] = translate_to_french(original, model_name=model_name)

    translated["lang"] = "FR"
    return translated


def translate_entries(
    entries: list[dict[str, Any]], model_name: str = DEFAULT_MODEL
) -> list[dict[str, Any]]:
    """Translate every entry's text fields to French."""
    translated_entries = []
    for index, entry in enumerate(entries, start=1):
        already_french = str(entry.get("lang", "")).upper() == "FR"
        if already_french:
            print(
                f"Translating entry {index}/{len(entries)} reason only "
                f"(already in French)..."
            )
        else:
            print(f"Translating entry {index}/{len(entries)} to French...")
        translated_entries.append(translate_entry(entry, model_name=model_name))
    return translated_entries


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
        .replace("{ user_preferences.md }", user_preferences)
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


def parse_feed(
    entries: list[dict[str, Any]] | None = None,
    candidates_count: int = DEFAULT_CANDIDATES_COUNT,
    final_count: int = DEFAULT_FINAL_COUNT,
    model_name: str = DEFAULT_MODEL,
    translate: bool = True,
) -> list[dict[str, Any]]:
    """Select, rerank, and optionally translate entries.

    1. Rank all entries by WordLlama similarity to readers_interests.md.
    2. Keep the top `candidates_count` candidates.
    3. Rerank those candidates with an LLM to select the `final_count` most
       important articles, ensuring diversity across countries and topics.
    4. Translate the selected articles' text fields into French.

    Returns the final selected entries in order of importance.
    """
    if entries is None:
        entries = load_entries()

    print(f"Ranking {len(entries)} entries by semantic similarity...")
    ranked = rank_entries(entries)
    candidates = ranked[:candidates_count]
    print(f"Selected top {len(candidates)} candidates for LLM reranking.")

    print(f"Reranking with LLM ({model_name}) to select {final_count} articles...")
    selected = rerank_with_llm(candidates, final_count=final_count, model_name=model_name)
    print(f"LLM selected {len(selected)} articles.")

    if translate:
        print("Translating selected entries to French...")
        selected = translate_entries(selected, model_name=model_name)

    return selected


def parse_and_export() -> tuple[list[dict[str, Any]], str]:
    """Run the full parsing step and export the result.

    Returns the selected entries and the generated editorial.
    """
    selected = parse_feed()
    editorial = generate_editorial(selected)
    export_entries_yaml(selected, editorial=editorial)
    print(
        f"Exported {len(selected)} parsed entries and editorial to "
        f"{DEFAULT_PARSED_ENTRIES_PATH}"
    )
    return selected, editorial


def main() -> None:
    """Run the parsing step."""
    parse_and_export()


if __name__ == "__main__":
    main()
