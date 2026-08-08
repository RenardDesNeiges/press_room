"""Tests for the two-step editorial pipeline (plan -> editorial) in prepare_entries.

Tier 1: pure logic with ``query_model`` monkeypatched — no network, no DB.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src import prepare_entries


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_build_plan_edito_prompt_replaces_placeholders(tmp_path, monkeypatch):
    monkeypatch.setattr(
        prepare_entries, "DEFAULT_INTERESTS_PATH", tmp_path / "interests.md"
    )
    template = _write(
        tmp_path / "plan_edito.md",
        "Analyse le flux : { rss_feed_yaml }\nPréférences : { user_preferences.md }",
    )
    interests = _write(
        tmp_path / "interests.md",
        "En-tête avant séparateur\n-----\nJe veux lire le journal.",
    )
    entries = [
        {
            "EID": "T1",
            "title": "Titre secret",
            "url": "https://secret.fr/x",
            "source": "Mediapart",
            "summary": "Un résumé.",
        }
    ]
    prompt = prepare_entries.build_plan_edito_prompt(
        entries, plan_edito_path=template, interests_path=interests
    )
    assert "{ rss_feed_yaml }" not in prompt
    assert "{ user_preferences.md }" not in prompt
    assert "http" not in prompt
    assert "Titre secret" in prompt
    assert "Je veux lire le journal." in prompt


def test_build_plan_edito_prompt_without_separator(tmp_path: Path):
    template = _write(
        tmp_path / "plan_edito.md",
        "Flux : { rss_feed_yaml }\nPrefs : { user_preferences.md }",
    )
    interests = _write(tmp_path / "interests.md", "Pas de séparateur ici.")
    prompt = prepare_entries.build_plan_edito_prompt(
        [{"EID": "x1", "title": "A"}],
        plan_edito_path=template,
        interests_path=interests,
    )
    assert "Pas de séparateur ici." in prompt


def test_build_edito_from_plan_prompt_replaces_placeholders(tmp_path: Path):
    template = _write(
        tmp_path / "edito_from_plan.md",
        "Synthèse : { synthesis_yaml }\n"
        "Prefs : { user_preferences.md }\n"
        "Longueur : { word_min }-{ word_max }",
    )
    interests = _write(
        tmp_path / "interests.md",
        "En-tête\n-----\nTonalité analytique.",
    )
    prompt = prepare_entries.build_edito_from_plan_prompt(
        "Regions:\n  - France: []",
        edito_from_plan_path=template,
        interests_path=interests,
        word_min=850,
        word_max=1150,
    )
    assert "{ synthesis_yaml }" not in prompt
    assert "{ user_preferences.md }" not in prompt
    assert "{ word_min }" not in prompt
    assert "{ word_max }" not in prompt
    assert "Regions:" in prompt
    assert "Tonalité analytique." in prompt
    assert "850-1150" in prompt


def test_build_edito_from_plan_prompt_defaults_word_range(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare_entries, "DEFAULT_EDITORIAL_MINUTES", 5)
    template = _write(
        tmp_path / "edito_from_plan.md",
        "{ synthesis_yaml } | { word_min }-{ word_max }",
    )
    interests = _write(tmp_path / "interests.md", "-----\nprefs")
    prompt = prepare_entries.build_edito_from_plan_prompt(
        "s", edito_from_plan_path=template, interests_path=interests
    )
    assert "850-1150" in prompt


def test_generate_editorial_from_plan_resolves_links(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        prepare_entries,
        "query_model",
        lambda prompt, **kwargs: "Selon [Le Monde](E1).",
    )
    entries = [{"EID": "E1", "url": "https://lemonde.fr/a"}]
    editorial = prepare_entries.generate_editorial_from_plan(
        "Regions: []",
        entries,
        edito_from_plan_path=_write(
            tmp_path / "edito_from_plan.md", "{ synthesis_yaml }"
        ),
        interests_path=_write(tmp_path / "interests.md", "-----\nprefs"),
    )
    assert editorial == "Selon [Le Monde](https://lemonde.fr/a)."


def test_plan_and_export_writes_file(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        prepare_entries,
        "generate_news_summary",
        lambda *args, **kwargs: "Regions:\n  - France: []",
    )
    parsed = _write(
        tmp_path / "parsed_entries.yml",
        yaml.safe_dump({"entries": [{"EID": 1, "title": "A"}]}),
    )
    out = tmp_path / "news_summary.yml"
    result = prepare_entries.plan_and_export(
        entries_path=parsed,
        output_path=out,
        interests_path=_write(tmp_path / "interests.md", "-----\nprefs"),
    )
    assert result == "Regions:\n  - France: []"
    assert out.read_text(encoding="utf-8") == "Regions:\n  - France: []"


def test_editorial_from_plan_and_export_writes_yaml(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        prepare_entries,
        "generate_editorial_from_plan",
        lambda *args, **kwargs: "Le fil du jour.",
    )
    monkeypatch.setattr(
        prepare_entries,
        "extract_editorial_title",
        lambda editorial, **kwargs: "Le fil du jour",
    )
    news_summary = _write(tmp_path / "news_summary.yml", "Regions: []")
    parsed = _write(
        tmp_path / "parsed_entries.yml",
        yaml.safe_dump({"entries": [{"EID": 1, "url": "https://x.fr"}]}),
    )
    out = tmp_path / "editorial.yml"
    editorial, title = prepare_entries.editorial_from_plan_and_export(
        news_summary_path=news_summary,
        output_path=out,
        entries_path=parsed,
    )
    assert (editorial, title) == ("Le fil du jour.", "Le fil du jour")
    written = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert written["title"] == "Le fil du jour"
    assert written["editorial"] == "Le fil du jour."


def test_prepare_sections_and_export_no_editorial(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        prepare_entries,
        "prepare_entries",
        lambda entries, **kwargs: [{"EID": 1, "title": "A", "section": "Ukraine"}],
    )
    parsed = _write(
        tmp_path / "parsed_entries.yml",
        yaml.safe_dump({"entries": [{"EID": 1, "title": "A"}]}),
    )
    out = tmp_path / "prepared_entries.yml"
    result = prepare_entries.prepare_sections_and_export(
        parsed_entries_path=parsed, output_path=out
    )
    assert result == [{"EID": 1, "title": "A", "section": "Ukraine"}]
    written = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert written["entries"] == [{"EID": 1, "title": "A", "section": "Ukraine"}]
    assert "editorial" not in written


def test_generate_news_summary_empty_entries_raises(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("query_model must not be called for empty entries")

    monkeypatch.setattr(prepare_entries, "query_model", fail)
    try:
        prepare_entries.generate_news_summary([])
    except ValueError as exc:
        assert "at least one article" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_plan_and_export_empty_entries_raises(tmp_path: Path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("generate_news_summary must not be called for empty entries")

    monkeypatch.setattr(prepare_entries, "generate_news_summary", fail)
    parsed = _write(
        tmp_path / "parsed_entries.yml",
        yaml.safe_dump({"entries": []}),
    )
    try:
        prepare_entries.plan_and_export(
            entries_path=parsed,
            output_path=tmp_path / "news_summary.yml",
            interests_path=_write(tmp_path / "interests.md", "-----\nprefs"),
        )
    except ValueError as exc:
        assert "no articles to summarize" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_editorial_from_plan_and_export_blank_summary_raises(
    tmp_path: Path, monkeypatch
):
    def fail(*args, **kwargs):
        raise AssertionError("generate_editorial_from_plan must not be called on blank summary")

    monkeypatch.setattr(prepare_entries, "generate_editorial_from_plan", fail)
    news_summary = _write(tmp_path / "news_summary.yml", "   \n  ")
    parsed = _write(
        tmp_path / "parsed_entries.yml",
        yaml.safe_dump({"entries": [{"EID": 1, "url": "https://x.fr"}]}),
    )
    try:
        prepare_entries.editorial_from_plan_and_export(
            news_summary_path=news_summary,
            output_path=tmp_path / "editorial.yml",
            entries_path=parsed,
        )
    except ValueError as exc:
        assert "empty news_summary" in str(exc)
    else:
        raise AssertionError("expected ValueError")