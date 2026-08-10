"""Central translation helper for the press-room pipeline.

Single home for every LLM-based translation in the app: entries, editorials, and
the multilingual ``readers_interests.md`` document all route through this module
(``translate_to_french`` in parse_feed.py is a thin wrapper over ``translate``).

The LLM used is configurable via the ``models.translation`` key in
``config.yml``, exposed here as ``TRANSLATION_MODEL``
(default ``meta-llama/llama-3.1-8b-instruct``). Swapping the translation model
is done centrally, in this module, and affects every translation in the app.
"""

from __future__ import annotations

from src.config import TRANSLATION_MODEL
from src.rerank_llm import query_model

SUPPORTED_LANGUAGES = ("fr", "en", "es", "de")

LANGUAGE_ALIASES = {
    "fr": "fr",
    "francais": "fr",
    "français": "fr",
    "french": "fr",
    "en": "en",
    "anglais": "en",
    "english": "en",
    "es": "es",
    "espagnol": "es",
    "español": "es",
    "spanish": "es",
    "de": "de",
    "allemand": "de",
    "deutsch": "de",
    "german": "de",
}

LANGUAGE_HEADERS = {"fr": "Français", "en": "English", "es": "Español", "de": "Deutsch"}

# The non-French languages the readers_interests.md file is generated into.
INTERESTS_TARGET_LANGUAGES = ("en", "es", "de")


def normalize_language(lang) -> str:
    """Normalize a language string to a canonical code.

    Matching is case- and whitespace-insensitive; aliases such as "français",
    "espagnol" or "german" map to the canonical code. Unknown languages raise a
    ValueError listing the supported codes.
    """
    normalized = str(lang).strip().lower()
    try:
        return LANGUAGE_ALIASES[normalized]
    except KeyError:
        supported = ", ".join(SUPPORTED_LANGUAGES)
        raise ValueError(
            f"Unsupported language {lang!r}. Supported languages: {supported}."
        ) from None


def translate(text, target_language, model_name=TRANSLATION_MODEL, temperature=0.2) -> str:
    """Translate ``text`` (any source language) into ``target_language``.

    Falsy or whitespace-only input is returned unchanged. The prompt is built
    from the target language's display header and sent to ``query_model``; the
    stripped response is returned.
    """
    if not text or not str(text).strip():
        return text

    target = normalize_language(target_language)
    header = LANGUAGE_HEADERS[target]
    prompt = (
        f"Translate the following text into {header}. This is text written for a "
        "journal. Preserve the original meaning, tone, and formatting. Do not add "
        "explanations, notes, or quotation marks around the output. Return only the "
        "translation.\n\n"
        f"Text:\n{text}"
    )

    response = query_model(prompt, model_name=model_name, temperature=temperature)
    return response.strip()


def build_readers_interests(french_text, model_name=TRANSLATION_MODEL) -> str:
    """Generate the multilingual readers_interests.md document, FRENCH FIRST.

    Returns the canonical layout (matching data/readers_interests.md), with
    sections separated by ``\n\n-----\n\n``: Français, English, Español, Deutsch.
    Only the first section of ``french_text`` (everything before the first
    "-----") is used as the French source; an empty source returns ``""``.
    """
    source = french_text.split("-----")[0].strip()
    if not source:
        return ""

    sections = [f"Français\n\n{source}"]
    for lang in INTERESTS_TARGET_LANGUAGES:
        header = LANGUAGE_HEADERS[lang]
        translated = translate(source, lang, model_name=model_name)
        sections.append(f"{header}\n\n{translated}")

    return "\n\n-----\n\n".join(sections)