"""Tier-1 tests for app._news_summary_tree / app._strip_code_fences.

Pure-logic parsing of the stored news_summary artifact into a JSON-safe tree:
markdown (and ```yaml) fence stripping, YAML→JSON normalization (dates become
strings), and the None fallbacks for empty / scalar / invalid content. No DB,
network or LLM involved.
"""

from __future__ import annotations

import json

from app import _news_summary_tree, _strip_code_fences


def test_plain_yaml_dict_preserves_keys():
    text = "Regions:\n  - France:\n      Topics: []\n"
    out = _news_summary_tree(text)
    assert isinstance(out, dict)
    assert list(out.keys()) == ["Regions"]


def test_markdown_fenced_block():
    text = "```markdown\nRegions:\n  - France:\n      Topics: []\n```\n"
    out = _news_summary_tree(text)
    assert isinstance(out, dict)
    assert out == {"Regions": [{"France": {"Topics": []}}]}


def test_yaml_fenced_block():
    text = "```yaml\nsummary:\n  headline: Un titre\n```\n"
    out = _news_summary_tree(text)
    assert out == {"summary": {"headline": "Un titre"}}


def test_plain_scalar_returns_none():
    assert _news_summary_tree("juste un texte") is None


def test_invalid_yaml_returns_none():
    assert _news_summary_tree("a: [unclosed") is None


def test_empty_and_whitespace_return_none():
    assert _news_summary_tree("") is None
    assert _news_summary_tree(None) is None
    assert _news_summary_tree("   \n  ") is None


def test_list_top_level_is_parsed():
    out = _news_summary_tree("- un\n- deux\n")
    assert out == ["un", "deux"]


def test_date_is_normalized_to_string():
    out = _news_summary_tree("date: 2026-08-08\n")
    assert out["date"] == "2026-08-08"
    assert json.loads(json.dumps(out))["date"] == "2026-08-08"


def test_strip_code_fences_basic():
    assert (
        _strip_code_fences("```markdown\nRegion: X\n```")
        == "Region: X"
    )
    assert _strip_code_fences("Region: X") == "Region: X"
    assert _strip_code_fences("") == ""
    assert _strip_code_fences(None) == ""


def test_strip_code_fences_only_outer_fence_info():
    assert _strip_code_fences("```python\na: 1\n```") == "a: 1"