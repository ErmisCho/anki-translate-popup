"""Unofficial Google Translate backend.

This provider talks to an undocumented endpoint that Google publishes for its
own web widget. It has no service agreement, no stability guarantee, and using
it may violate Google's Terms of Service. It is therefore gated behind an
explicit opt-in flag (``enable_google_unofficial``) and is never selected by
default. Keep it isolated in this module so the supported providers stay clean.
"""

from __future__ import annotations

from typing import Any, List

from .base import (
    ConfigurationError,
    ProviderError,
    TranslationRequest,
    TranslationResult,
    Translator,
    normalise_two_letter,
)

ENDPOINT = "https://translate.googleapis.com/translate_a/single"


class GoogleUnofficialTranslator(Translator):
    name = "google_unofficial"
    requires_api_key = False
    privacy_note = (
        "UNOFFICIAL. Selected text is sent to an undocumented Google endpoint "
        "with no service agreement, no rate-limit guarantee, and no stated "
        "retention policy for this use. Google may block it or change it "
        "without notice, and using it may breach Google's Terms of Service. "
        "Disabled by default; enable at your own risk."
    )

    def __init__(self, timeout: float, enabled: bool) -> None:
        super().__init__(timeout)
        self._enabled = enabled

    def validate(self) -> None:
        if not self._enabled:
            raise ConfigurationError(
                "The unofficial Google Translate provider is disabled. It uses "
                "an undocumented endpoint and may breach Google's Terms of "
                "Service. To use it anyway, set 'enable_google_unofficial' to "
                "true in the add-on configuration."
            )

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.validate()

        params = {
            "client": "gtx",
            "sl": (
                "auto"
                if request.source_lang == "auto"
                else normalise_two_letter(request.source_lang)
            ),
            "tl": normalise_two_letter(request.target_lang),
            "dt": "t",
            "q": request.text,
        }
        payload = self._request_json("GET", ENDPOINT, params=params)
        return self._parse(payload, request)

    def _parse(self, payload: Any, request: TranslationRequest) -> TranslationResult:
        # Shape: [[[translated, original, ...], ...], ..., detected_lang, ...]
        # Long input is split into several segments that must be re-joined.
        if not isinstance(payload, list) or not payload:
            raise ProviderError(
                "The unofficial Google endpoint returned an unexpected response."
            )

        segments = payload[0]
        if not isinstance(segments, list) or not segments:
            raise ProviderError("The unofficial Google endpoint returned no translation.")

        parts: List[str] = []
        for segment in segments:
            if isinstance(segment, list) and segment and isinstance(segment[0], str):
                parts.append(segment[0])
        if not parts:
            raise ProviderError("The unofficial Google endpoint returned no translation.")

        source = normalise_two_letter(request.source_lang)
        if len(payload) > 2 and isinstance(payload[2], str) and payload[2]:
            source = normalise_two_letter(payload[2])

        return TranslationResult(
            text="".join(parts),
            source_lang=source,
            target_lang=normalise_two_letter(request.target_lang),
            provider=self.name,
        )
