"""Tests for src/editorial_to_mp3.py (Tier 1: Markdown->plain text)."""

from __future__ import annotations

from src import editorial_to_mp3 as em


def test_strip_markdown_headers():
    text = "# Titre\n\n## Sous-titre\n"
    assert em.strip_markdown(text) == "Titre\n\nSous-titre"


def test_strip_markdown_links():
    assert em.strip_markdown("[Pressroom](https://example.com)") == "Pressroom"


def test_strip_markdown_bold_italic_underline():
    assert em.strip_markdown("**gras** et *italique* et _souligne_ et __fort__") == (
        "gras et italique et souligne et fort"
    )


def test_strip_markdown_block_same_line():
    assert em.strip_markdown("**a** *b*") == "a b"


def test_strip_markdown_lists_and_quotes():
    text = "> Une citation\n- un point\n+ autre point\n1. numéroté\n"
    assert em.strip_markdown(text) == "Une citation\nun point\nautre point\n1. numéroté"


def test_strip_markdown_horizontal_rule():
    assert em.strip_markdown("Avant\n\n---\n\nAprès") == "Avant\n\nAprès"


def test_strip_markdown_collapses_blank_lines():
    assert em.strip_markdown("a\n\n\n\n\nb") == "a\n\nb"


def test_strip_markdown_leaves_plain_text():
    assert em.strip_markdown("  Bonjour   ") == "Bonjour"