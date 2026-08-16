"""Tier-1 tests for app._news_summary_tree / app._strip_code_fences.

Pure-logic parsing of the stored news_summary artifact into a JSON-safe tree:
markdown (and ```yaml) fence stripping, YAML→JSON normalization (dates become
strings), the plan_edito schema shape check (top-level dict with a "Regions"
list of single-key region dicts, each with a "Topics" list), and the None
fallbacks for empty / scalar / invalid / mismatched content, which make the
caller fall back to the raw <pre> display. No DB, network or LLM involved.
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
    assert out is None


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
    assert out is None


def test_date_is_normalized_to_string():
    out = _news_summary_tree("date: 2026-08-08\n")
    assert out is None


def test_no_regions_key_returns_none():
    assert _news_summary_tree("hello: world\n") is None


def test_regions_not_a_list_returns_none():
    assert _news_summary_tree("Regions: France\n") is None


def test_region_item_not_a_dict_returns_none():
    assert _news_summary_tree("Regions:\n  - France\n") is None


def test_region_dict_with_multiple_keys_returns_none():
    assert (
        _news_summary_tree(
            "Regions:\n  - France:\n      Topics: []\n      Other: x\n"
        )
        is None
    )


def test_region_missing_topics_returns_none():
    assert _news_summary_tree("Regions:\n  - France:\n      Other: x\n") is None


def test_region_topics_not_a_list_returns_none():
    assert _news_summary_tree("Regions:\n  - France:\n      Topics: notalist\n") is None


def test_multi_region_with_topics_is_parsed():
    text = (
        "Regions:\n"
        "  - France:\n"
        "      Topics:\n"
        '        - "Un sujet":\n'
        "            Importance: 1\n"
        "  - Suisse:\n"
        "      Topics: []\n"
    )
    out = _news_summary_tree(text)
    assert out == {
        "Regions": [
            {"France": {"Topics": [{"Un sujet": {"Importance": 1}}]}},
            {"Suisse": {"Topics": []}},
        ]
    }


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