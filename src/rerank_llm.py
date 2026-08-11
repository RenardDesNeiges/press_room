"""Rerank candidate articles using an LLM via OpenRouter."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from openrouter import OpenRouter

from src.key import API_KEY
from src.config import *
from src.rank_entries import load_interests


def build_candidate_prompt_block(
    entries: list[dict[str, Any]], max_summary_length: int = 200
) -> str:
    """Build a numbered prompt block describing each candidate article."""
    lines = []
    for entry in entries:
        eid = entry.get("EID", "?")
        title = entry.get("title") or "Untitled"
        summary = entry.get("summary") or ""
        source = entry.get("source") or "Unknown"
        lang = entry.get("lang") or "?"

        if len(summary) > max_summary_length:
            summary = summary[:max_summary_length].rsplit(" ", 1)[0] + "…"

        lines.append(
            f"[{eid}] {title}\n"
            f"    Source: {source} | Language: {lang}\n"
            f"    Summary: {summary}\n"
        )
    return "\n".join(lines)


def load_additional_prompt(path: str | Path = DEFAULT_ARRANK_PROMPT_PATH) -> str:
    """Load additional reranking instructions from a Markdown file."""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def build_rerank_prompt(
    entries: list[dict[str, Any]],
    final_count: int = 20,
    interests_path: str | Path = DEFAULT_INTERESTS_PATH,
    additional_prompt_path: str | Path = DEFAULT_ARRANK_PROMPT_PATH,
) -> str:
    """Build the full prompt for the LLM reranking step."""
    interests = load_interests(interests_path).split('-----')[0]  # first section is Français (French-first file)
    additional_prompt = load_additional_prompt(additional_prompt_path)
    candidates_block = build_candidate_prompt_block(entries)

    return f"""You are a careful editorial assistant selecting articles for a left-wing reader.

READER PROFILE:
{interests}
{additional_prompt}

TASK:
From the {len(entries)} candidate articles below, select exactly {final_count} articles that are most important and relevant to the reader profile above.

SELECTION CRITERIA:
1. Relevance to the reader's political interests (left-wing perspective, geopolitics, far-right/far-left movements, social movements, capitalism crises, etc.).
2. DIVERSITY: ensure a diverse selection across countries (France, Switzerland, Germany, Spain, USA, etc.) and across topics. Do not pick many articles on the same event or from the same source.
3. Importance: prioritize significant political, economic, or social developments over minor news.

CANDIDATE ARTICLES (numbered by EID):
{candidates_block}

OUTPUT FORMAT:
Return ONLY a JSON array of exactly {final_count} objects, ordered from most to least important. Each object must have:
- "EID": the EID of the selected article (copy it EXACTLY as shown, with no changes)
- "reason": a one-sentence explanation of why it was selected
- "theme": between one and thee theme tag in French describing the article's main topic (e.g., "politique", "économie", "société", "environnement", "géopolitique", "droits humains", "médias", "culture", "technologie")
- "country": one country tag in French indicating the primary country or region concerned. Add a second "international" tag if the article concerns diplomacy or other interactions between countries. Separate tags with commas.

Example output format:
[
  {{"EID": 12, "reason": "Directly covers AfD gains in Germany, matching reader interest in far-right rise.", "theme": "politique", "country": "allemagne"}},
  {{"EID": 5, "reason": "Major social movement in France with geopolitical implications.", "theme": "société", "country": "france"}},
  {{"EID": 7, "reason": "Global climate summit commitments with geopolitical consequences.", "theme": "environnement", "country": "international"}}
]
"""


def extract_json_list(response_text: str | None) -> list[Any] | None:
    """Extract a JSON array from an LLM response, tolerating code fences and prose.

    Returns the parsed list, or None if no valid JSON array can be found.
    """
    if not response_text or not response_text.strip():
        return None
    text = response_text.strip()

    # Trim surrounding Markdown code fences (e.g. ```json ... ```).
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Try the whole text as JSON.
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Fallback: locate the outermost [...] array and parse it.
    start = text.find("[")
    if start != -1:
        end = text.rfind("]")
        if end > start:
            try:
                data = json.loads(text[start : end + 1])
                if isinstance(data, list):
                    return data
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    return None


def _coerce_eid(value: Any) -> Any:
    """Normalize an EID: keep ints as ints, strings as-is (new EID format)."""
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return str(value)


def parse_eids_from_response(response_text: str | None) -> list[Any]:
    """Extract an ordered list of EIDs from the LLM response.

    Works with the legacy integer EIDs and the new ``<user>_<date>_<time>_<seq>``
    string EIDs. Returns the EIDs in the order chosen by the LLM.
    """
    if not response_text:
        return []
    data = extract_json_list(response_text)
    if data is not None:
        return [
            _coerce_eid(item["EID"])
            for item in data
            if isinstance(item, dict) and "EID" in item
        ]

    # Fallback: look for EID numbers in the text.
    return [
        int(m)
        for m in re.findall(r"\bEID\D+(\d+)", response_text, re.IGNORECASE)
    ]


def query_model(
    prompt: str,
    model_name: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_tokens: int | None = None,
) -> str:
    """Query an LLM via OpenRouter."""
    with OpenRouter(api_key=API_KEY) as client:
        kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        response = client.chat.send(**kwargs)
        content = response.choices[0].message.content
        if content is None:
            content = (
                getattr(response.choices[0].message, "reasoning", None)
                or ""
            )
        if not content or not content.strip():
            print(f"WARNING: model {model_name} returned empty content.")
            return ""
        return content


def _clean_tag(value: Any) -> str:
    """Normalize a tag string: strip whitespace and surrounding quotes."""
    if not isinstance(value, str):
        return ""
    return value.strip().strip('"').strip("'")


def rerank_with_llm(
    entries: list[dict[str, Any]],
    final_count: int = 20,
    model_name: str = FANCY_MODEL,
    interests_path: str | Path = DEFAULT_INTERESTS_PATH,
) -> list[dict[str, Any]]:
    """Rerank candidate entries into `final_count` articles using an LLM.

    The LLM is asked to ensure diversity across countries and topics, and to
    assign exactly one theme tag and one country tag to each selected article.
    Returns the selected entries in the order chosen by the LLM, with
    "rerank_reason", "theme", and "country" fields added.
    """
    if not entries:
        return []

    prompt = build_rerank_prompt(entries, final_count=final_count, interests_path=interests_path)
    response_text = query_model(prompt, model_name=model_name, max_tokens=32000)

    eids = parse_eids_from_response(response_text)

    # Guard: the LLM may echo a candidate EID twice; select each EID once or the
    # (issue_id, eid) UNIQUE key in prepared_entries will be violated downstream.
    seen_eids: set[str] = set()
    unique_eids = []
    for eid in eids:
        key = str(eid)
        if key in seen_eids:
            continue
        seen_eids.add(key)
        unique_eids.append(eid)
    eids = unique_eids

    # Build a lookup by EID.
    entry_by_eid = {entry.get("EID"): entry for entry in entries}

    # Attach reasons and tags from the parsed JSON (if any).
    reasons: dict[Any, str] = {}
    tags: dict[Any, dict[str, str]] = {}
    data = extract_json_list(response_text)
    if data is not None:
        for item in data:
            if isinstance(item, dict) and "EID" in item:
                eid = _coerce_eid(item["EID"])
                reasons[eid] = _clean_tag(item.get("reason", ""))
                tags[eid] = {
                    "theme": _clean_tag(item.get("theme", "")),
                    "country": _clean_tag(item.get("country", "")),
                }

    selected = []
    for eid in eids:
        entry = entry_by_eid.get(eid)
        if entry is None:
            continue
        enriched = dict(entry)
        enriched["rerank_reason"] = reasons.get(eid, "")
        enriched["theme"] = tags.get(eid, {}).get("theme", "")
        enriched["country"] = tags.get(eid, {}).get("country", "")
        selected.append(enriched)

    return selected[:final_count]


def main() -> None:
    """CLI smoke test: load filtered entries, get top candidates, rerank to final."""
    import yaml
    from src.config import DEFAULT_CANDIDATES_COUNT, DEFAULT_ENTRIES_PATH, DEFAULT_FINAL_COUNT
    from src.rank_entries import rank_entries

    with open(DEFAULT_ENTRIES_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    candidates = rank_entries(data.get("entries", []))[:DEFAULT_CANDIDATES_COUNT]
    selected = rerank_with_llm(candidates, final_count=DEFAULT_FINAL_COUNT)

    print(f"Selected {len(selected)} articles:\n")
    for entry in selected:
        print(
            f"[{entry.get('EID')}] {entry.get('source', 'Unknown')} · "
            f"{entry.get('title', 'Untitled')}"
        )


if __name__ == "__main__":
    main()
