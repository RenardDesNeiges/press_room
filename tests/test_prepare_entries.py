"""Tests for src/prepare_entries.py (Tier 1: word ranges + section logic)."""

from __future__ import annotations

import pytest

from src import prepare_entries


# --- minutes_to_word_range ---------------------------------------------------

def test_word_range_default_five():
    assert prepare_entries.minutes_to_word_range(5) == (850, 1150)


def test_word_range_clamps_low():
    assert prepare_entries.minutes_to_word_range(1) == (250, 550)


def test_word_range_clamps_high():
    assert prepare_entries.minutes_to_word_range(99) == (1850, 2150)


def test_word_range_accepts_string():
    assert prepare_entries.minutes_to_word_range("8") == (1450, 1750)


# --- parse_sections ----------------------------------------------------------

def test_parse_sections_empty():
    assert prepare_entries.parse_sections(None) == []
    assert prepare_entries.parse_sections("") == []


def test_parse_sections_valid():
    response = '[{"title": "Ukraine", "EIDs": [3, 9]}, {"title": "Économie", "EIDs": [1]}]'
    sections = prepare_entries.parse_sections(response)
    assert sections == [{"title": "Ukraine", "EIDs": [3, 9]}, {"title": "Économie", "EIDs": [1]}]


def test_parse_sections_single_int_eid():
    sections = prepare_entries.parse_sections('[{"title": "Climat", "EIDs": 4}]')
    assert sections == [{"title": "Climat", "EIDs": [4]}]


def test_parse_sections_skips_bad_items():
    response = (
        '[{"title": "Politique", "EIDs": [1]}, '
        '"not-an-object", '
        '{"title": "", "EIDs": [2]}, '
        '{"title": "  ", "EIDs": [3]}, '
        '{"EIDs": [4]}, '
        '{"title": "Mixte", "EIDs": ["a", 5, 6.0]}]'
    )
    sections = prepare_entries.parse_sections(response)
    assert sections == [
        {"title": "Politique", "EIDs": [1]},
        {"title": "Mixte", "EIDs": [5, 6]},
    ]


def test_parse_sections_string_eids():
    response = (
        '[{"title": "Ukraine", "EIDs": ["titou_20260808_1430_0007", "titou_20260808_1430_0005"]}, '
        '{"title": "Économie", "EIDs": ["titou_20260808_1430_0001"]}]'
    )
    sections = prepare_entries.parse_sections(response)
    assert sections == [
        {"title": "Ukraine", "EIDs": ["titou_20260808_1430_0007", "titou_20260808_1430_0005"]},
        {"title": "Économie", "EIDs": ["titou_20260808_1430_0001"]},
    ]


def test_parse_sections_quoted_numeric_strings_kept_as_strings():
    sections = prepare_entries.parse_sections('[{"title": "X", "EIDs": ["12", "5"]}]')
    assert sections == [{"title": "X", "EIDs": ["12", "5"]}]


# --- resolve_editorial_links --------------------------------------------------

def test_resolve_editorial_links_replaces_eids():
    editorial = "Selon [Le Monde](E1), puis [ailleurs](42)."
    entries = [{"EID": "E1", "url": "https://lemonde.fr/a"}, {"EID": 42, "url": "https://nzz.ch/b"}]
    out = prepare_entries.resolve_editorial_links(editorial, entries)
    assert out == "Selon [Le Monde](https://lemonde.fr/a), puis [ailleurs](https://nzz.ch/b)."


def test_resolve_editorial_links_leaves_unknown_eids():
    assert prepare_entries.resolve_editorial_links(
        "Une [citation](ouest)", [{"EID": 1, "url": "https://x.fr"}]
    ) == "Une [citation](ouest)"


def test_resolve_editorial_links_empty():
    assert prepare_entries.resolve_editorial_links("", []) == ""
    assert prepare_entries.resolve_editorial_links(None, []) is None


def test_editorial_prompt_entries_use_eid_not_url():
    entries = [{"EID": "titou_1", "title": "Titre", "url": "https://secret.fr/x", "source": "S", "summary": "Résumé"}]
    refs = prepare_entries._editorial_prompt_entries(entries)
    assert refs == [{
        "EID": "titou_1",
        "reference": "[*Titre*](titou_1)",
        "source": "S",
        "summary": "Résumé",
        "theme": "",
        "country": "",
        "date": "",
    }]
    assert "secret.fr" not in str(refs)


# --- assign_sections ---------------------------------------------------------

def _entries():
    return [
        {"EID": 1, "title": "a"},
        {"EID": 2, "title": "b"},
        {"EID": 3, "title": "c"},
        {"EID": 4, "title": "d"},
    ]


def test_assign_sections_attaches_and_preserves_props():
    entries = _entries()
    out = prepare_entries.assign_sections(entries, [{"title": "Ukraine", "EIDs": [3, 1]}])
    by_eid = {e["EID"]: e for e in out}
    assert by_eid[1]["section"] == "Ukraine"
    assert by_eid[3]["section"] == "Ukraine"
    assert by_eid[1]["title"] == "a"


def test_assign_sections_leftovers_become_autres():
    entries = _entries()
    out = prepare_entries.assign_sections(entries, [{"title": "Ukraine", "EIDs": [3]}])
    assert [e["EID"] for e in out] == [3, 1, 2, 4]  # assigned first, then leftovers
    assert out[0]["section"] == "Ukraine"
    assert all(e["section"] == "Autres" for e in out[1:])


def test_assign_sections_first_section_wins_on_duplicate_eid():
    entries = _entries()
    out = prepare_entries.assign_sections(
        entries,
        [{"title": "Premier", "EIDs": [1]}, {"title": "Second", "EIDs": [1, 2]}],
    )
    by_eid = {e["EID"]: e for e in out}
    assert by_eid[1]["section"] == "Premier"
    assert by_eid[2]["section"] == "Second"


def test_assign_sections_missing_eid_is_leftover():
    entries = [{"EID": 1, "title": "a"}, {"title": "no-eid"}]
    out = prepare_entries.assign_sections(entries, [{"title": "X", "EIDs": [1]}])
    assert out[0]["section"] == "X"
    assert out[1]["section"] == "Autres"


def test_assign_sections_string_eids():
    entries = [
        {"EID": "titou_20260808_1430_0007", "title": "a"},
        {"EID": "titou_20260808_1430_0003", "title": "b"},
    ]
    out = prepare_entries.assign_sections(
        entries, [{"title": "Ukraine", "EIDs": ["titou_20260808_1430_0003"]}]
    )
    assert out[0]["section"] == "Ukraine"
    assert out[0]["EID"] == "titou_20260808_1430_0003"
    assert out[1]["section"] == "Autres"


def test_assign_sections_empty():
    assert prepare_entries.assign_sections([], []) == []


# --- strip_yaml_code_fence ---------------------------------------------------

def test_strip_yaml_code_fence_removes_fence():
    assert prepare_entries.strip_yaml_code_fence(
        "```yaml\nRegions:\n  - France: []\n```"
    ) == "Regions:\n  - France: []"


def test_strip_yaml_code_fence_no_fence_unchanged():
    assert prepare_entries.strip_yaml_code_fence(
        "Regions:\n  - France: []"
    ) == "Regions:\n  - France: []"
    assert prepare_entries.strip_yaml_code_fence(
        "Du texte sans bloc de code."
    ) == "Du texte sans bloc de code."


def test_strip_yaml_code_fence_trailing_newline():
    assert prepare_entries.strip_yaml_code_fence(
        "```yaml\nRegions:\n  - France: []\n```\n"
    ) == "Regions:\n  - France: []"


def test_strip_yaml_code_fence_leading_and_trailing_blank_lines():
    assert prepare_entries.strip_yaml_code_fence(
        "\n```yaml\nRegions: []\n```\n\n"
    ) == "Regions: []"


def test_strip_yaml_code_fence_fence_without_lang():
    assert prepare_entries.strip_yaml_code_fence("```\nRegions: []\n```") == "Regions: []"


# --- is_valid_yaml -----------------------------------------------------------

def test_is_valid_yaml_valid_mapping():
    assert prepare_entries.is_valid_yaml("Regions:\n  - France:\n      Topics: []\n")


def test_is_valid_yaml_rejects_prose():
    assert not prepare_entries.is_valid_yaml(
        "L'actualité du jour, en bref:\n  - un article important\n  et la suite sans indentation"
    )


def test_is_valid_yaml_rejects_empty_and_whitespace():
    assert not prepare_entries.is_valid_yaml("")
    assert not prepare_entries.is_valid_yaml("   \n\t ")


def test_is_valid_yaml_rejects_invalid_mapping():
    assert not prepare_entries.is_valid_yaml("a: b\n: c\n")


# --- generate_news_summary ---------------------------------------------------

def _write_prompt_files(tmp_path):
    plan_edito_path = tmp_path / "plan_edito.md"
    interests_path = tmp_path / "readers_interests.md"
    plan_edito_path.write_text("{ rss_feed_yaml }\n{ user_preferences.md }", encoding="utf-8")
    interests_path.write_text("Intérêts du lecteur", encoding="utf-8")
    return plan_edito_path, interests_path


def _news_summary_entries():
    return [{"EID": 1, "title": "Titre", "url": "https://mediapart.fr/1", "summary": "Résumé"}]


VALID_SUMMARY = "Regions:\n  - France:\n      Topics: []"
INVALID_SUMMARY = "L'actualité du jour, en bref:\n  - un article important\n  et la suite sans indentation"


def test_generate_news_summary_valid_first_try(tmp_path, monkeypatch):
    plan_edito_path, interests_path = _write_prompt_files(tmp_path)
    calls = []

    def fake_query(prompt, **kwargs):
        calls.append(kwargs)
        return "\n" + VALID_SUMMARY + "\n"

    monkeypatch.setattr(prepare_entries, "query_model", fake_query)
    out = prepare_entries.generate_news_summary(
        _news_summary_entries(),
        plan_edito_path=plan_edito_path,
        interests_path=interests_path,
    )
    assert out == VALID_SUMMARY
    assert len(calls) == 1


def test_generate_news_summary_accepts_fenced_yaml(tmp_path, monkeypatch):
    plan_edito_path, interests_path = _write_prompt_files(tmp_path)
    calls = []

    def fake_query(prompt, **kwargs):
        calls.append(kwargs)
        return "```yaml\nRegions: []\n```"

    monkeypatch.setattr(prepare_entries, "query_model", fake_query)
    out = prepare_entries.generate_news_summary(
        _news_summary_entries(),
        plan_edito_path=plan_edito_path,
        interests_path=interests_path,
        model_name="m",
    )
    assert out == "Regions: []"
    assert len(calls) == 1
    assert prepare_entries.is_valid_yaml(out) is True


def test_generate_news_summary_plain_text_when_invalid(tmp_path, monkeypatch):
    plan_edito_path, interests_path = _write_prompt_files(tmp_path)
    calls = {"count": 0}

    def fake_query(prompt, **kwargs):
        calls["count"] += 1
        return INVALID_SUMMARY

    monkeypatch.setattr(prepare_entries, "query_model", fake_query)
    out = prepare_entries.generate_news_summary(
        _news_summary_entries(),
        plan_edito_path=plan_edito_path,
        interests_path=interests_path,
    )
    assert out == INVALID_SUMMARY
    assert calls["count"] == 1
    assert prepare_entries.is_valid_yaml(out) is False