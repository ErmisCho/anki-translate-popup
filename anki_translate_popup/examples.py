"""Example sentences from Tatoeba.

Tatoeba is an open corpus of sentences with human translations, released under
CC-BY 2.0 FR. It is used here rather than a translation provider because none
of them expose usage examples any more: Google's `dt=ex` parameter now returns
nothing, and DeepL and LibreTranslate never offered examples at all.

Examples are a learning aid, never load-bearing: every failure here is
swallowed by the caller so a lookup still returns its translation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

import requests

from .translation.base import USER_AGENT

TATOEBA_ENDPOINT = "https://tatoeba.org/en/api_v0/search"

#: Tatoeba speaks ISO 639-3; the add-on's config uses ISO 639-1.
ISO_639_1_TO_3 = {
    "ar": "ara", "cs": "ces", "da": "dan", "de": "deu", "el": "ell",
    "en": "eng", "es": "spa", "fa": "pes", "fi": "fin", "fr": "fra",
    "he": "heb", "hi": "hin", "hu": "hun", "id": "ind", "it": "ita",
    "ja": "jpn", "ko": "kor", "nl": "nld", "no": "nor", "pl": "pol",
    "pt": "por", "ro": "ron", "ru": "rus", "sv": "swe", "tr": "tur",
    "uk": "ukr", "vi": "vie", "zh": "cmn",
}

#: Examples are only meaningful for a word or short phrase. Searching Tatoeba
#: for a whole sentence returns nothing useful and wastes a request.
MAX_QUERY_CHARS = 40
MAX_QUERY_WORDS = 3
#: Chinese does not separate words with spaces; eight characters is roughly
#: the same short-phrase ceiling as three space-separated words.
MAX_UNSPACED_QUERY_CHARS = 8


@dataclass(frozen=True)
class Example:
    text: str  # sentence in the source language
    translation: str  # its translation in the target language


def is_example_worthy(text: str, source_lang: str = "") -> bool:
    """True when ``text`` is short enough for examples to make sense."""
    stripped = text.strip()
    if not stripped or len(stripped) > MAX_QUERY_CHARS:
        return False
    if source_lang.strip().replace("_", "-").split("-")[0].lower() == "zh":
        return len(stripped) <= MAX_UNSPACED_QUERY_CHARS
    return len(stripped.split()) <= MAX_QUERY_WORDS


def to_iso3(lang: str) -> Optional[str]:
    base = lang.strip().replace("_", "-").split("-")[0].lower()
    return ISO_639_1_TO_3.get(base)


class TatoebaExamples:
    """Fetches example sentences. Safe to call from a worker thread."""

    attribution = "Tatoeba (CC-BY 2.0 FR)"

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    def fetch(
        self, text: str, source_lang: str, target_lang: str, limit: int = 3
    ) -> List[Example]:
        """Return up to ``limit`` examples, or an empty list.

        Returns empty rather than raising for every expected condition: an
        unsupported language, a selection too long to look up, or no matches.
        Network and parsing failures do raise, so the caller can log them.
        """
        if not is_example_worthy(text, source_lang):
            return []

        source = to_iso3(source_lang)
        target = to_iso3(target_lang)
        if not source or not target:
            return []

        response = requests.get(
            TATOEBA_ENDPOINT,
            params={
                "from": source,
                "to": target,
                "query": text.strip(),
                "sort": "relevance",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            return []

        return self._parse(response.json(), target, limit)

    def _parse(self, payload: Any, target_iso3: str, limit: int) -> List[Example]:
        if not isinstance(payload, dict):
            return []
        results = payload.get("results")
        if not isinstance(results, list):
            return []

        examples: List[Example] = []
        for entry in results:
            if len(examples) >= limit:
                break
            if not isinstance(entry, dict):
                continue
            sentence = entry.get("text")
            if not isinstance(sentence, str) or not sentence.strip():
                continue
            translation = self._first_translation(entry.get("translations"), target_iso3)
            if translation:
                examples.append(Example(text=sentence.strip(), translation=translation))
        return examples

    def _first_translation(self, groups: Any, target_iso3: str) -> Optional[str]:
        """Tatoeba nests translations one level deeper than you would expect."""
        if not isinstance(groups, list):
            return None
        for group in groups:
            candidates = group if isinstance(group, list) else [group]
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                if candidate.get("lang") != target_iso3:
                    continue
                text = candidate.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
        return None
