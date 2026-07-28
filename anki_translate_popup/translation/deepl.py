"""DeepL API v2 backend."""

from __future__ import annotations

from typing import Any, Dict

from .base import (
    ConfigurationError,
    ProviderError,
    TranslationRequest,
    TranslationResult,
    Translator,
    normalise_two_letter,
)

FREE_ENDPOINT = "https://api-free.deepl.com/v2/translate"
PRO_ENDPOINT = "https://api.deepl.com/v2/translate"


class DeepLTranslator(Translator):
    name = "deepl"
    requires_api_key = True
    privacy_note = (
        "Selected text is sent to DeepL (api.deepl.com / api-free.deepl.com) "
        "over HTTPS. DeepL states that API text is not used to train its "
        "models and is deleted after translation; review their current "
        "privacy policy before sending sensitive material."
    )

    def __init__(self, timeout: float, api_key: str) -> None:
        super().__init__(timeout)
        self._api_key = api_key.strip()

    def validate(self) -> None:
        if not self._api_key:
            raise ConfigurationError(
                "DeepL requires an API key. Open Tools > Add-ons > "
                "Translate & Pronounce Popup > Config and set 'api_key'."
            )

    @property
    def _endpoint(self) -> str:
        # DeepL free keys carry a ':fx' suffix and use a separate host.
        return FREE_ENDPOINT if self._api_key.endswith(":fx") else PRO_ENDPOINT

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.validate()

        body: Dict[str, Any] = {
            "text": [request.text],
            "target_lang": request.target_lang.strip().upper(),
        }
        if request.source_lang != "auto":
            # DeepL only accepts a plain two-letter source language.
            body["source_lang"] = normalise_two_letter(request.source_lang).upper()

        payload = self._request_json(
            "POST",
            self._endpoint,
            headers={"Authorization": f"DeepL-Auth-Key {self._api_key}"},
            json_body=body,
        )
        return self._parse(payload, request)

    def _parse(self, payload: Any, request: TranslationRequest) -> TranslationResult:
        if not isinstance(payload, dict):
            raise ProviderError("DeepL returned an unexpected response format.")

        translations = payload.get("translations")
        if not isinstance(translations, list) or not translations:
            message = payload.get("message")
            if isinstance(message, str) and message:
                raise ProviderError(f"DeepL reported an error: {message}")
            raise ProviderError("DeepL returned no translation.")

        first = translations[0]
        if not isinstance(first, dict) or not isinstance(first.get("text"), str):
            raise ProviderError("DeepL returned an unexpected translation entry.")

        detected = first.get("detected_source_language")
        source = (
            detected.lower()
            if isinstance(detected, str) and detected
            else request.source_lang
        )
        return TranslationResult(
            text=first["text"],
            source_lang=source,
            target_lang=request.target_lang.lower(),
            provider=self.name,
        )
