"""LibreTranslate backend (self-hosted or public instance)."""

from __future__ import annotations

from typing import Any, Dict, Set

from .base import (
    ConfigurationError,
    LanguageSupport,
    ProviderError,
    TranslationRequest,
    TranslationResult,
    Translator,
    normalise_two_letter,
)


class LibreTranslateTranslator(Translator):
    name = "libretranslate"
    requires_api_key = False
    privacy_note = (
        "Selected text is sent to the LibreTranslate instance you configure. "
        "If you run that instance yourself, no text leaves your machine or "
        "network. Public instances are operated by third parties whose "
        "logging and retention policies you should check yourself."
    )

    def __init__(self, timeout: float, endpoint: str, api_key: str = "") -> None:
        super().__init__(timeout)
        self._endpoint = endpoint.strip().rstrip("/")
        self._api_key = api_key.strip()

    def validate(self) -> None:
        if not self._endpoint:
            raise ConfigurationError(
                "LibreTranslate requires an endpoint URL. Set "
                "'libretranslate_endpoint' in the add-on configuration, for "
                "example 'http://localhost:5000'."
            )
        if not self._endpoint.startswith(("http://", "https://")):
            raise ConfigurationError(
                "'libretranslate_endpoint' must start with http:// or https:// "
                f"(got {self._endpoint!r})."
            )

    def supported_languages(self) -> LanguageSupport:
        self.validate()
        params = {"api_key": self._api_key} if self._api_key else None
        payload = self._request_json(
            "GET", f"{self._endpoint}/languages", params=params
        )
        if not isinstance(payload, list):
            raise ProviderError("LibreTranslate returned an unexpected language list.")

        sources: Set[str] = set()
        targets: Set[str] = set()
        for entry in payload:
            if not isinstance(entry, dict) or not isinstance(entry.get("code"), str):
                continue
            code = entry["code"].lower()
            sources.add(code)
            listed_targets = entry.get("targets")
            if isinstance(listed_targets, list):
                targets.update(
                    target.lower() for target in listed_targets if isinstance(target, str)
                )
        if not sources:
            raise ProviderError("LibreTranslate returned no supported languages.")
        return frozenset(sources), frozenset(targets or sources)

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.validate()

        body: Dict[str, Any] = {
            "q": request.text,
            "source": (
                "auto"
                if request.source_lang == "auto"
                else normalise_two_letter(request.source_lang)
            ),
            "target": normalise_two_letter(request.target_lang),
            "format": "text",
        }
        if self._api_key:
            body["api_key"] = self._api_key

        payload = self._request_json(
            "POST", f"{self._endpoint}/translate", json_body=body
        )
        return self._parse(payload, request)

    def _parse(self, payload: Any, request: TranslationRequest) -> TranslationResult:
        if not isinstance(payload, dict):
            raise ProviderError("LibreTranslate returned an unexpected response format.")

        translated = payload.get("translatedText")
        if not isinstance(translated, str):
            error = payload.get("error")
            if isinstance(error, str) and error:
                raise ProviderError(f"LibreTranslate reported an error: {error}")
            raise ProviderError("LibreTranslate returned no translation.")

        source = normalise_two_letter(request.source_lang)
        # Only present when the request asked for automatic detection.
        detected = payload.get("detectedLanguage")
        if isinstance(detected, dict) and isinstance(detected.get("language"), str):
            source = detected["language"].lower()

        return TranslationResult(
            text=translated,
            source_lang=source,
            target_lang=normalise_two_letter(request.target_lang),
            provider=self.name,
        )
