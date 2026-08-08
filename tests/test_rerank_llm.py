"""Tests for src/rerank_llm.py (Tier 1: prompt builders + JSON parsing)."""

from __future__ import annotations

from src import rerank_llm


# --- extract_json_list -------------------------------------------------------

def test_extract_json_list_empty():
    assert rerank_llm.extract_json_list(None) is None
    assert rerank_llm.extract_json_list("") is None
    assert rerank_llm.extract_json_list("   ") is None


def test_extract_json_list_plain():
    assert rerank_llm.extract_json_list('[{"EID": 1}]') == [{"EID": 1}]


def test_extract_json_list_with_code_fence():
    response = '```json\n[{"EID": 1}, {"EID": 2}]\n```'
    assert rerank_llm.extract_json_list(response) == [{"EID": 1}, {"EID": 2}]


def test_extract_json_list_embedded_in_prose():
    response = 'Here are the picks:\n[{"EID": 7}]\n\nThat is all.'
    assert rerank_llm.extract_json_list(response) == [{"EID": 7}]


def test_extract_json_list_not_a_list():
    assert rerank_llm.extract_json_list('{"EID": 1}') is None
    assert rerank_llm.extract_json_list("no brackets here") is None


def test_extract_json_list_invalid_json():
    assert rerank_llm.extract_json_list("[{'EID': 1}") is None


# --- parse_eids_from_response ------------------------------------------------

def test_parse_eids_from_response_list():
    assert rerank_llm.parse_eids_from_response(
        '[{"EID": 12, "reason": "x"}, {"EID": 5, "reason": "y"}]'
    ) == [12, 5]


def test_parse_eids_from_response_skips_missing_eid():
    assert rerank_llm.parse_eids_from_response(
        '[{"EID": 3}, {"reason": "no eid"}]'
    ) == [3]


def test_parse_eids_from_response_prose_fallback():
    assert rerank_llm.parse_eids_from_response(
        "Selected EID 12 and EID 8 for the briefing."
    ) == [12, 8]


def test_parse_eids_from_response_empty():
    assert rerank_llm.parse_eids_from_response(None) == []
    assert rerank_llm.parse_eids_from_response("nothing here") == []


def test_parse_eids_from_response_string_eids():
    response = (
        '[{"EID": "titou_20260808_1430_0007", "reason": "x"}, '
        '{"EID": "titou_20260808_1430_0005", "reason": "y"}]'
    )
    assert rerank_llm.parse_eids_from_response(response) == [
        "titou_20260808_1430_0007",
        "titou_20260808_1430_0005",
    ]


def test_coerce_eid_keeps_types():
    assert rerank_llm._coerce_eid(12) == 12
    assert rerank_llm._coerce_eid(6.0) == 6
    assert rerank_llm._coerce_eid("titou_20260808_1430_0007") == "titou_20260808_1430_0007"


# --- build_candidate_prompt_block --------------------------------------------

def test_build_candidate_prompt_block_fields():
    block = rerank_llm.build_candidate_prompt_block(
        [{"EID": 3, "title": "Titre", "summary": "Résumé", "source": "SRC", "lang": "FR"}]
    )
    assert "[3] Titre" in block
    assert "Source: SRC | Language: FR" in block
    assert "Summary: Résumé" in block


def test_build_candidate_prompt_block_missing_fields_defaults():
    block = rerank_llm.build_candidate_prompt_block([{"EID": 9}])
    assert "[9] Untitled" in block
    assert "Source: Unknown | Language: ?" in block
    assert "Summary: " in block


def test_build_candidate_prompt_block_truncates_summary():
    block = rerank_llm.build_candidate_prompt_block(
        [{"EID": 1, "title": "T", "summary": "aaaa bbbb cccc dddd eeee", "source": "S", "lang": "FR"}],
        max_summary_length=20,
    )
    assert "Summary: aaaa bbbb cccc dddd…" in block


def test_build_candidate_prompt_block_short_summary_untouched():
    block = rerank_llm.build_candidate_prompt_block(
        [{"EID": 1, "title": "T", "summary": "short", "source": "S", "lang": "FR"}],
        max_summary_length=20,
    )
    assert "Summary: short" in block