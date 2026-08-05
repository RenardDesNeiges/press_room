"""Rerank candidate articles using an LLM via OpenRouter."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from openrouter import OpenRouter

from config import *
from rank_entries import load_interests


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


def build_rerank_prompt(
    entries: list[dict[str, Any]],
    interests_path: str | Path = DEFAULT_INTERESTS_PATH,
    additional_rerank_proompt: str | Path = DEFAULT_ARRANK_PROMPT_PATH,
) -> str:
    """Build the full prompt for the LLM reranking step."""
    interests = load_interests(interests_path).split('-----')[0] # ignore the mutlilingual nature of the prompt for reranking
    candidates_block = build_candidate_prompt_block(entries)

    return f"""You are a careful editorial assistant selecting articles for a left-wing activist reader.

READER PROFILE:
{interests}
{additional_rerank_proompt}

TASK:
From the {len(entries)} candidate articles below, select exactly 20 articles that are most important and relevant to the reader profile above.

SELECTION CRITERIA:
1. Relevance to the reader's political interests (left-wing perspective, geopolitics, far-right/far-left movements, social movements, capitalism crises, etc.).
2. DIVERSITY: ensure a diverse selection across countries (France, Switzerland, Germany, Spain, USA, etc.) and across topics. Do not pick many articles on the same event or from the same source.
3. Importance: prioritize significant political, economic, or social developments over minor news.

CANDIDATE ARTICLES (numbered by EID):
{candidates_block}

OUTPUT FORMAT:
Return ONLY a JSON array of exactly 20 objects, ordered from most to least important. Each object must have:
- "EID": the integer EID of the selected article
- "reason": a one-sentence explanation of why it was selected

Example output format:
[
  {{"EID": 12, "reason": "Directly covers AfD gains in Germany, matching reader interest in far-right rise."}},
  {{"EID": 5, "reason": "Major social movement in France with geopolitical implications."}}
]
"""


def parse_eids_from_response(response_text: str) -> list[int]:
    """Extract an ordered list of EIDs from the LLM response."""
    # Try to parse as JSON first.
    try:
        data = json.loads(response_text)
        if isinstance(data, list):
            return [int(item["EID"]) for item in data if isinstance(item, dict) and "EID" in item]
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Fallback: look for EID numbers in the text.
    eids = [int(m) for m in re.findall(r"\bEID\D+(\d+)", response_text, re.IGNORECASE)]
    return eids


def query_model(
    prompt: str,
    model_name: str = DEFAULT_MODEL,
    temperature: float = 0.3,
) -> str:
    """Query an LLM via OpenRouter."""
    with OpenRouter(api_key=API_KEY) as client:
        response = client.chat.send(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return response.choices[0].message.content


def rerank_with_llm(
    entries: list[dict[str, Any]],
    model_name: str = DEFAULT_MODEL,
    interests_path: str | Path = DEFAULT_INTERESTS_PATH,
) -> list[dict[str, Any]]:
    """Rerank candidate entries into 20 articles using an LLM.

    The LLM is asked to ensure diversity across countries and topics.
    Returns the selected entries in the order chosen by the LLM, with a
    "rerank_reason" field added.
    """
    if not entries:
        return []

    prompt = build_rerank_prompt(entries, interests_path)
    response_text = query_model(prompt, model_name=model_name)

    eids = parse_eids_from_response(response_text)

    # Build a lookup by EID.
    entry_by_eid = {entry.get("EID"): entry for entry in entries}

    # Try to attach reasons if JSON parsing succeeded.
    reasons: dict[int, str] = {}
    try:
        data = json.loads(response_text)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "EID" in item:
                    reasons[int(item["EID"])] = item.get("reason", "")
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    selected = []
    for eid in eids:
        entry = entry_by_eid.get(eid)
        if entry is None:
            continue
        enriched = dict(entry)
        enriched["rerank_reason"] = reasons.get(eid, "")
        selected.append(enriched)

    return selected[:20]


def main() -> None:
    """CLI smoke test: load filtered entries, get top 80, rerank to 20."""
    import yaml
    from rank_entries import rank_entries

    with open(DEFAULT_ENTRIES_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    top80 = rank_entries(data.get("entries", []))[:80]
    top20 = rerank_with_llm(top80)

    print(f"Selected {len(top20)} articles:\n")
    for entry in top20:
        print(
            f"[{entry.get('EID')}] {entry.get('source', 'Unknown')} · "
            f"{entry.get('title', 'Untitled')}"
        )


if __name__ == "__main__":
    main()
