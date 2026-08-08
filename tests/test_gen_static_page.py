"""Tests for src/gen_static_page.py (Tier 1: pure URL/format/grouping helpers)."""

from __future__ import annotations

from datetime import datetime

from src import gen_static_page as g


# --- _domain_of --------------------------------------------------------------

def test_domain_of_variants():
    assert g._domain_of("https://mediapart.fr/article/1") == "mediapart.fr"
    assert g._domain_of("http://WWW.Example.COM:8080/x") == "example.com"
    assert g._domain_of("https://user@host.example/p") == "host.example"
    assert g._domain_of("example.com") == "example.com"
    assert g._domain_of("") == ""


# --- archive_url -------------------------------------------------------------

def test_archive_url_wraps_and_strips_scheme():
    assert g.archive_url("https://www.example.com/news/1") == (
        "https://archive.ph/www.example.com/news/1"
    )


def test_archive_url_leaves_excluded_domains():
    url = "https://www.mediapart.fr/x"
    assert g.archive_url(url, excluded_domains={"mediapart.fr"}) == url


def test_archive_url_defaults_to_config_exclusion():
    assert g.archive_url("https://mediapart.fr/x") == "https://mediapart.fr/x"


def test_archive_url_empty_and_hash():
    assert g.archive_url("") == ""
    assert g.archive_url(None) is None or g.archive_url(None) == ""
    assert g.archive_url("#") == "#"


# --- French date formatting --------------------------------------------------

def test_format_date_fr():
    dt = datetime(2026, 8, 6)
    assert g.format_date_fr(dt) == "jeudi 6 août 2026"


def test_format_datetime_fr():
    dt = datetime(2026, 8, 6, 14, 3)
    assert g.format_datetime_fr(dt) == "jeudi 6 août 2026 à 14h03"


# --- shorten_summary ---------------------------------------------------------

def test_shorten_summary_empty():
    assert g.shorten_summary("") == ""
    assert g.shorten_summary(None) == ""


def test_shorten_summary_short_unchanged():
    assert g.shorten_summary("Bonjour le monde") == "Bonjour le monde"


def test_shorten_summary_long_truncates_at_word_boundary():
    text = "un deux trois quatre cinq six sept huit neuf dix"
    out = g.shorten_summary(text, max_length=20)
    assert out == "un deux trois…"
    assert "dix" not in out


# --- normalize_country -------------------------------------------------------

def test_normalize_country_matches_canonical():
    assert g.normalize_country("FRANCE") == "france"
    assert g.normalize_country("allemagne") == "allemagne"


def test_normalize_country_unknown_returns_as_is():
    assert g.normalize_country("xyzabc") == "Xyzabc"


def test_normalize_country_empty():
    assert g.normalize_country(None) == "Divers"
    assert g.normalize_country("") == "Divers"


# --- top_counts --------------------------------------------------------------

def test_top_counts_sources():
    entries = [
        {"source": "Mediapart"}, {"source": "Mediapart"}, {"source": "NZZ"},
    ]
    assert g.top_counts(entries, "source")[0] == ("mediapart", 2)


def test_top_counts_split_and_order():
    entries = [
        {"country": "France, International"},
        {"country": "France"},
        {"country": "Suisse"},
    ]
    top = g.top_counts(entries, "country", limit=2, split=True)
    assert top[0] == ("france", 2)
    assert top[1] == ("international", 1)


# --- entry_tag_values --------------------------------------------------------

def test_entry_tag_values_lowercases_and_splits():
    entry = {"theme": "Politique, Ukraine", "country": "France"}
    assert g.entry_tag_values(entry) == ["politique", "ukraine", "france"]


def test_entry_tag_values_skips_empty():
    assert g.entry_tag_values({"theme": "", "country": None}) == []


# --- pick_feature_image ------------------------------------------------------

def test_pick_feature_image_picks_highest_similarity_with_media():
    entries = [
        {"title": "b", "media": "http://img/2", "similarity_score": 0.5},
        {"title": "a", "media": "http://img/1", "similarity_score": 0.9},
        {"title": "c"},  # no media
    ]
    assert g.pick_feature_image(entries)["title"] == "a"


def test_pick_feature_image_none_without_media():
    assert g.pick_feature_image([{"title": "x"}]) is None
    assert g.pick_feature_image([]) is None


# --- select_distinct_theme_leads --------------------------------------------

def test_leads_distinct_themes():
    entries = [
        {"title": "a", "theme": "Politique"},
        {"title": "b", "theme": "Économie"},
        {"title": "c", "theme": "Politique"},
    ]
    leads, remainder = g.select_distinct_theme_leads(entries, count=2)
    assert [e["title"] for e in leads] == ["a", "b"]
    assert [e["title"] for e in remainder] == ["c"]


def test_leads_fill_from_remainder():
    entries = [
        {"title": "a", "theme": "Politique"},
        {"title": "b", "theme": "Politique"},
        {"title": "c", "theme": "Politique"},
    ]
    leads, remainder = g.select_distinct_theme_leads(entries, count=3)
    assert [e["title"] for e in leads] == ["a", "b", "c"]
    assert remainder == []


# --- grouping ----------------------------------------------------------------

def test_group_entries_by_country():
    entries = [
        {"title": "a", "country": "France"},
        {"title": "b", "country": "france"},
        {"title": "c", "country": "France"},
        {"title": "d", "country": "Allemagne"},
        {"title": "e"},
    ]
    groups = g.group_entries_by_country(entries)
    assert groups[0][0] == "france"
    assert len(groups[0][1]) == 3
    assert groups[1][0] == "Autres"
    assert {e["title"] for e in groups[1][1]} == {"d", "e"}


def test_group_entries_by_section_first_appearance_order():
    entries = [
        {"title": "a", "section": "Ukraine"},
        {"title": "b", "section": "Économie"},
        {"title": "c", "section": "Ukraine"},
        {"title": "d", "section": ""},
    ]
    groups = g.group_entries_by_section(entries)
    assert [name for name, _ in groups] == ["Ukraine", "Économie", "Autres"]
    assert len(groups[0][1]) == 2