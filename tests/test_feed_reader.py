"""Tests for src/feed_reader.py (Tier 1: pure parsing/filtering, mocked fetch)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import src.feed_reader as fr


def _mk_entry(ts: datetime | None, link: str | None = None) -> dict:
    entry = {}
    if ts is not None:
        entry["published_parsed"] = (
            ts.year, ts.month, ts.day, ts.hour, ts.minute, ts.second, 0, 0, 0,
        )
    if link is not None:
        entry["link"] = link
    return entry


def _feeds_dict():
    ref = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    today_entry = _mk_entry(ref - timedelta(minutes=5), link="today")
    borderline = _mk_entry(ref - timedelta(hours=23), link="borderline")
    old = _mk_entry(ref - timedelta(hours=37), link="old")
    nodate = _mk_entry(None, link="nodated")
    meta = {"entries": [today_entry, borderline, old, nodate]}
    return {
        "a": {"feed": dict(meta), "today_only": True},
        "b": {"feed": dict(meta), "today_only": False},
        "c": {"feed": dict(meta), "today_only": None},
        "d": {"feed": dict(meta)},
    }, ref


def _links(filtered):
    return {url: [e["link"] for e in meta["entries"]] for url, meta in filtered.items()}


# --- parse_feed_date ---------------------------------------------------------

def test_parse_feed_date_published():
    dt = fr.parse_feed_date({"published_parsed": (2026, 8, 6, 9, 30, 0, 0, 0, 0)})
    assert dt == datetime(2026, 8, 6, 9, 30, tzinfo=timezone.utc)


def test_parse_feed_date_updated_fallback():
    dt = fr.parse_feed_date({"updated_parsed": (2026, 8, 6, 9, 30, 0, 0, 0, 0)})
    assert dt == datetime(2026, 8, 6, 9, 30, tzinfo=timezone.utc)


def test_parse_feed_date_published_wins_over_updated():
    entry = {
        "published_parsed": (2026, 8, 6, 9, 30, 0, 0, 0, 0),
        "updated_parsed": (2026, 8, 7, 1, 0, 0, 0, 0, 0),
    }
    assert fr.parse_feed_date(entry) == datetime(2026, 8, 6, 9, 30, tzinfo=timezone.utc)


def test_parse_feed_date_absent():
    assert fr.parse_feed_date({"title": "x"}) is None
    assert fr.parse_feed_date({"published_parsed": None}) is None


# --- strip_html --------------------------------------------------------------

def test_strip_html_removes_tags_and_decodes_entities():
    assert fr.strip_html("<p>Hello &amp; <b>bye</b></p>") == "Hello & bye"


def test_strip_html_none_empty():
    assert fr.strip_html(None) is None
    assert fr.strip_html("") is None
    assert fr.strip_html("<p></p>") is None


# --- filter_feeds_by_date ----------------------------------------------------

def test_filter_age_window_keeps_recent_only():
    feeds, ref = _feeds_dict()
    out = fr.filter_feeds_by_date(feeds, max_age=timedelta(days=1), reference_date=ref)
    # 37h-old and undated entries dropped; 23h-old (yesterday) kept.
    assert _links(out)["b"] == ["today", "borderline"]
    assert _links(out)["c"] == ["today", "borderline"]
    assert _links(out)["d"] == ["today", "borderline"]


def test_filter_today_only_keeps_same_calendar_day():
    feeds, ref = _feeds_dict()
    out = fr.filter_feeds_by_date(feeds, max_age=timedelta(days=1), reference_date=ref)
    assert _links(out)["a"] == ["today"]


def test_default_today_only_applies_when_flag_absent():
    feeds, ref = _feeds_dict()
    out = fr.filter_feeds_by_date(
        feeds, max_age=timedelta(days=1), reference_date=ref, default_today_only=True
    )
    assert _links(out)["a"] == ["today"]
    # explicit False still uses the age window even under default=today
    assert _links(out)["b"] == ["today", "borderline"]
    assert _links(out)["c"] == ["today"]
    assert _links(out)["d"] == ["today"]


def test_filter_empty_input():
    assert fr.filter_feeds_by_date({}, reference_date=datetime.now(timezone.utc)) == {}


# --- collect_all_feeds -------------------------------------------------------

def test_collect_all_feeds_structures(monkeypatch, feeds_config):
    def fake_query(url: str):
        return {"entries": [_mk_entry(datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc), url)]}

    monkeypatch.setattr(fr, "query_rss_feed", fake_query)
    results = fr.collect_all_feeds(feeds_config)
    assert set(results) == {
        "https://www.mediapart.fr/articles/feed",
        "https://www.nzz.ch/startseite.rss",
    }
    mediapart = results["https://www.mediapart.fr/articles/feed"]
    assert mediapart["source"] == "Mediapart"
    assert mediapart["lang"] == "FR"
    assert mediapart["today_only"] is None
    nzz = results["https://www.nzz.ch/startseite.rss"]
    assert nzz["source"] == "NZZ"
    assert nzz["today_only"] is True


def test_collect_all_feeds_skips_failed_fetch(monkeypatch, feeds_config):
    monkeypatch.setattr(fr, "query_rss_feed", lambda url: None)
    assert fr.collect_all_feeds(feeds_config) == {}


# --- flatten / export --------------------------------------------------------

def test_format_entry_shape():
    entry = {
        "title": "T",
        "summary": "<p>S</p>",
        "link": "https://x/y",
        "published_parsed": (2026, 8, 6, 9, 30, 0, 0, 0, 0),
    }
    out = fr.format_entry(entry, lang="FR", source="X")
    assert out["title"] == "T"
    assert out["summary"] == "S"
    assert out["url"] == "https://x/y"
    assert out["lang"] == "FR"
    assert out["source"] == "X"
    assert out["date"] == "2026-08-06T09:30:00+00:00"


def test_flatten_assigns_eids():
    ref = datetime(2026, 8, 6, 8, 0, tzinfo=timezone.utc)
    filtered = {
        "u1": {
            "entries": [_mk_entry(ref, "u1a"), _mk_entry(ref, "u1b")],
            "lang": "FR",
            "source": "One",
        },
        "u2": {"entries": [_mk_entry(ref, "u2a")], "lang": "DE", "source": "Two"},
    }
    entries = fr.flatten_filtered_entries(filtered)
    assert [e["EID"] for e in entries] == [1, 2, 3]
    assert [e["url"] for e in entries] == ["u1a", "u1b", "u2a"]


# --- scrape_feeds (mocked network + frozen clock) ----------------------------

def _freeze_clock(fr_module, monkeypatch, frozen):
    """Pin ``datetime.now`` inside feed_reader to the given UTC instant."""
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz == timezone.utc:
                return frozen
            return super().now(tz)

    monkeypatch.setattr(fr_module, "datetime", _FrozenDatetime)


def test_scrape_feeds_threads_today_only(monkeypatch, tmp_path):
    ref = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    _freeze_clock(fr, monkeypatch, ref)

    def fake_query(url: str):
        return {"entries": [
            _mk_entry(ref - timedelta(minutes=5), f"{url}#today"),
            _mk_entry(ref - timedelta(hours=23), f"{url}#23h"),
        ]}

    monkeypatch.setattr(fr, "query_rss_feed", fake_query)

    feeds = tmp_path / "feeds.yml"
    feeds.write_text(
        "publications:\n"
        "  - name: TodayFeed\n"
        "    lang: FR\n"
        "    today_only: true\n"
        "    feeds:\n"
        "      - 'http://a/rss'\n"
        "  - name: AgeFeed\n"
        "    lang: EN\n"
        "    feeds:\n"
        "      - 'http://b/rss'\n",
        encoding="utf-8",
    )

    entries = fr.scrape_feeds(feeds_path=feeds, output_path=tmp_path / "out.yml")
    assert sorted(e["url"] for e in entries) == [
        "http://a/rss#today",
        "http://b/rss#23h",
        "http://b/rss#today",
    ]

    # default_today_only threads through: AgeFeed now also keeps only "today"
    entries = fr.scrape_feeds(
        feeds_path=feeds, output_path=tmp_path / "out2.yml", default_today_only=True
    )
    assert sorted(e["url"] for e in entries) == [
        "http://a/rss#today",
        "http://b/rss#today",
    ]