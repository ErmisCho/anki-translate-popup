"""DeepL API v2 backend."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet

from .base import (
    ConfigurationError,
    LanguageSupport,
    ProviderError,
    TranslationRequest,
    TranslationResult,
    Translator,
    normalise_two_letter,
)

FREE_API = "https://api-free.deepl.com/v2"
PRO_API = "https://api.deepl.com/v2"
FREE_ENDPOINT = f"{FREE_API}/translate"
PRO_ENDPOINT = f"{PRO_API}/translate"


def deepl_target_language(lang: str) -> str:
    """Map user-facing Chinese codes onto DeepL's required target variants."""
    code = lang.strip().replace("_", "-").upper()
    if code in ("ZH", "ZH-CN", "ZH-SG", "ZH-HANS"):
        return "ZH-HANS"
    if code in ("ZH-TW", "ZH-HK", "ZH-MO", "ZH-HANT"):
        return "ZH-HANT"
    return code


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
    def _api(self) -> str:
        # DeepL free keys carry a ':fx' suffix and use a separate host.
        return FREE_API if self._api_key.endswith(":fx") else PRO_API

    @property
    def _endpoint(self) -> str:
        return f"{self._api}/translate"

    def supported_languages(self) -> LanguageSupport:
        self.validate()
        headers = {"Authorization": f"DeepL-Auth-Key {self._api_key}"}
        source = self._language_codes(
            self._request_json(
                "GET", f"{self._api}/languages", headers=headers, params={"type": "source"}
            )
        )
        target = self._language_codes(
            self._request_json(
                "GET", f"{self._api}/languages", headers=headers, params={"type": "target"}
            )
        )
        return source, target

    @staticmethod
    def _language_codes(payload: Any) -> FrozenSet[str]:
        if not isinstance(payload, list):
            raise ProviderError("DeepL returned an unexpected language list.")
        codes = frozenset(
            entry["language"].lower()
            for entry in payload
            if isinstance(entry, dict) and isinstance(entry.get("language"), str)
        )
        if not codes:
            raise ProviderError("DeepL returned no supported languages.")
        return codes

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.validate()

        body: Dict[str, Any] = {
            "text": [request.text],
            "target_lang": deepl_target_language(request.target_lang),
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
