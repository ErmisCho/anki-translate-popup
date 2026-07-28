"""Online text-to-speech, for languages Windows has no usable voice for.

Windows exposes two unrelated kinds of voice. Classic SAPI5/OneCore voices are
visible to every application. Narrator "natural voices" (the ones Settings
offers most prominently on Windows 11) are reserved for Narrator and are never
registered as voice tokens, so Chromium — and therefore Anki's webview — cannot
see them. A user can have German speech installed and still have no German
voice available to this add-on.

This module sidesteps that by fetching audio over the network instead.
"""

from __future__ import annotations

import abc
from typing import List

import requests

from .translation.base import USER_AGENT, normalise_two_letter

#: The endpoint rejects long inputs, so text is spoken in segments.
MAX_CHUNK_CHARS = 180
#: Guard against a huge selection turning into dozens of requests.
MAX_SPEECH_CHARS = 600

GOOGLE_TTS_ENDPOINT = "https://translate.google.com/translate_tts"


class SpeechError(Exception):
    """Raised for any failure the user should be shown."""


class TextToSpeech(abc.ABC):
    """A speech backend that turns text into playable audio bytes."""

    name: str = ""
    privacy_note: str = ""

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    @abc.abstractmethod
    def synthesize(self, text: str, lang: str) -> bytes:
        """Return audio data, or raise :class:`SpeechError`."""


def split_for_speech(text: str, limit: int = MAX_CHUNK_CHARS) -> List[str]:
    """Split ``text`` into segments of at most ``limit`` characters.

    Splits on word boundaries so the speech does not break mid-word. A single
    word longer than the limit is hard-split, since it cannot fit otherwise.
    """
    chunks: List[str] = []
    current = ""

    for word in text.split():
        while len(word) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(word[:limit])
            word = word[limit:]

        candidate = f"{current} {word}".strip()
        if len(candidate) > limit and current:
            chunks.append(current)
            current = word
        else:
            current = candidate

    if current:
        chunks.append(current)
    return chunks


class GoogleTextToSpeech(TextToSpeech):
    """Google's translate_tts endpoint.

    Unofficial, exactly like the matching translation provider: undocumented,
    unversioned, and usable only at Google's discretion.
    """

    name = "google_unofficial"
    privacy_note = (
        "UNOFFICIAL. The selected text is sent to an undocumented Google "
        "endpoint each time you press Pronounce (results are cached on disk, "
        "so repeats are silent). No service agreement, no stated retention "
        "policy, and use may breach Google's Terms of Service."
    )

    def synthesize(self, text: str, lang: str) -> bytes:
        text = text.strip()
        if not text:
            raise SpeechError("Nothing to pronounce.")
        if len(text) > MAX_SPEECH_CHARS:
            raise SpeechError(
                f"The selection is too long to pronounce ({len(text)} "
                f"characters). Select at most {MAX_SPEECH_CHARS}."
            )

        # MP3 frames concatenate cleanly, so the segments play as one clip.
        audio = bytearray()
        for chunk in split_for_speech(text):
            audio.extend(self._fetch(chunk, lang))
        if not audio:
            raise SpeechError("The speech service returned no audio.")
        return bytes(audio)

    def _fetch(self, chunk: str, lang: str) -> bytes:
        params = {
            "ie": "UTF-8",
            "q": chunk,
            "tl": normalise_two_letter(lang),
            "client": "tw-ob",
        }
        try:
            response = requests.get(
                GOOGLE_TTS_ENDPOINT,
                params=params,
                headers={"User-Agent": USER_AGENT},
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise SpeechError(
                f"The speech request timed out after {self._timeout:g} seconds."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise SpeechError(
                "Could not reach the speech service. Check your internet connection."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise SpeechError(f"The speech request failed: {exc}") from exc

        if response.status_code == 429:
            raise SpeechError(
                "The speech service is rate-limiting requests. Wait a moment "
                "and try again."
            )
        if response.status_code >= 400:
            raise SpeechError(
                f"The speech service rejected the request (HTTP {response.status_code})."
            )

        content = response.content
        if not content:
            raise SpeechError("The speech service returned an empty response.")
        # Guard against an HTML error page being written out as a .mp3.
        if not _looks_like_mp3(content):
            raise SpeechError(
                "The speech service returned data that is not audio. The "
                "endpoint may have changed or be blocking this request."
            )
        return content


def _looks_like_mp3(data: bytes) -> bool:
    """True for an ID3 tag or an MPEG audio frame sync."""
    if data.startswith(b"ID3"):
        return True
    return len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
