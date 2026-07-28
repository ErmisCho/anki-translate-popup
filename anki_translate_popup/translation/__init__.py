"""Translation backends and the factory that selects one."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Type

from .base import (
    ConfigurationError,
    NetworkError,
    ProviderError,
    TranslationError,
    TranslationRequest,
    TranslationResult,
    Translator,
)
from .deepl import DeepLTranslator
from .google_unofficial import GoogleUnofficialTranslator
from .libretranslate import LibreTranslateTranslator

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..config import AddonConfig

PROVIDERS: Dict[str, Type[Translator]] = {
    DeepLTranslator.name: DeepLTranslator,
    LibreTranslateTranslator.name: LibreTranslateTranslator,
    GoogleUnofficialTranslator.name: GoogleUnofficialTranslator,
}

__all__ = [
    "PROVIDERS",
    "ConfigurationError",
    "DeepLTranslator",
    "GoogleUnofficialTranslator",
    "LibreTranslateTranslator",
    "NetworkError",
    "ProviderError",
    "TranslationError",
    "TranslationRequest",
    "TranslationResult",
    "Translator",
    "build_translator",
]


def build_translator(config: "AddonConfig", provider: str = "") -> Translator:
    """Instantiate a provider, defaulting to ``config.translation_provider``.

    ``provider`` overrides the configured choice so the fallback path can build
    a second backend from the same configuration.

    Raises :class:`ConfigurationError` for an unknown provider name. The
    returned translator has *not* been validated yet; call ``validate()`` (or
    ``translate()``, which validates first) to surface missing credentials.
    """
    provider = provider or config.translation_provider
    if provider == DeepLTranslator.name:
        return DeepLTranslator(config.request_timeout_seconds, config.api_key)
    if provider == LibreTranslateTranslator.name:
        return LibreTranslateTranslator(
            config.request_timeout_seconds,
            config.libretranslate_endpoint,
            config.api_key,
        )
    if provider == GoogleUnofficialTranslator.name:
        return GoogleUnofficialTranslator(
            config.request_timeout_seconds, config.enable_google_unofficial
        )
    raise ConfigurationError(
        f"Unknown translation provider {provider!r}. Choose one of: "
        + ", ".join(sorted(PROVIDERS))
    )
