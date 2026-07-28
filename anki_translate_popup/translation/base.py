"""Provider-agnostic translation interfaces.

Every backend implements :class:`Translator`. The UI layer only ever sees
:class:`TranslationResult` and the :class:`TranslationError` hierarchy, so a new
backend can be added without touching the popup, the bridge, or the cache.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, FrozenSet, Optional, Tuple

import requests

# Sent so operators of public endpoints can identify the traffic.
USER_AGENT = "AnkiTranslatePopup/1.0 (+https://apps.ankiweb.net)"


class TranslationError(Exception):
    """Base class for every failure the user may be shown."""


class ConfigurationError(TranslationError):
    """The add-on configuration is incomplete or invalid."""


class NetworkError(TranslationError):
    """The provider could not be reached, or the request timed out."""


class ProviderError(TranslationError):
    """The provider was reached but refused or returned an unusable answer."""


@dataclass(frozen=True)
class TranslationRequest:
    text: str
    source_lang: str  # ISO code such as "de", or "auto" for detection
    target_lang: str  # ISO code such as "en"


LanguageSupport = Tuple[FrozenSet[str], FrozenSet[str]]
"""Provider-supported source and target language codes, respectively."""


@dataclass(frozen=True)
class TranslationResult:
    text: str
    source_lang: str  # what the provider actually detected/used
    target_lang: str
    provider: str


class Translator(abc.ABC):
    """A translation backend.

    Implementations must be usable from a worker thread: no Qt calls, no
    shared mutable state beyond what is set in ``__init__``.
    """

    #: Key used in ``config.json`` under ``translation_provider``.
    name: ClassVar[str] = ""
    #: Whether :meth:`validate` should insist on an API key being present.
    requires_api_key: ClassVar[bool] = False
    #: Shown in config.md / README so the user knows where their text goes.
    privacy_note: ClassVar[str] = ""

    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    @abc.abstractmethod
    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Translate ``request`` or raise a :class:`TranslationError`."""

    @abc.abstractmethod
    def validate(self) -> None:
        """Raise :class:`ConfigurationError` if this provider cannot be used."""

    def supported_languages(self) -> Optional[LanguageSupport]:
        """Return supported source/target codes, or ``None`` when unavailable."""
        return None

    # -- shared HTTP plumbing -------------------------------------------------

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Perform an HTTP request and decode JSON, normalising all failures.

        Every ``requests`` exception is translated into our own hierarchy so
        callers never have to know which HTTP library is in use.
        """
        all_headers = {"User-Agent": USER_AGENT}
        if headers:
            all_headers.update(headers)

        try:
            response = requests.request(
                method,
                url,
                headers=all_headers,
                json=json_body,
                params=params,
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise NetworkError(
                "The translation request timed out after "
                f"{self._timeout:g} seconds. Check your connection or raise "
                "'request_timeout_seconds' in the add-on configuration."
            ) from exc
        except requests.exceptions.SSLError as exc:
            raise NetworkError(
                "The secure connection to the translation service failed. "
                "This is often caused by a proxy or antivirus intercepting HTTPS."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise NetworkError(
                "Could not reach the translation service. Check your internet "
                "connection and the configured endpoint."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise NetworkError(f"The translation request failed: {exc}") from exc

        self._raise_for_status(response)

        try:
            return response.json()
        except ValueError as exc:
            raise ProviderError(
                "The translation service returned a malformed response "
                "(expected JSON)."
            ) from exc

    def _raise_for_status(self, response: "requests.Response") -> None:
        """Map HTTP status codes onto actionable messages."""
        status = response.status_code
        if status < 400:
            return
        if status in (401, 403):
            raise ConfigurationError(
                "The translation service rejected your API key (HTTP "
                f"{status}). Check 'api_key' in the add-on configuration."
            )
        if status == 429:
            raise ProviderError(
                "The translation service is rate-limiting requests (HTTP 429). "
                "Wait a moment and try again."
            )
        if status == 456:
            # DeepL uses this for "quota exceeded".
            raise ProviderError(
                "Your translation quota for this billing period is used up "
                "(HTTP 456)."
            )
        if status >= 500:
            raise ProviderError(
                f"The translation service reported a server error (HTTP {status}). "
                "Try again later."
            )
        raise ProviderError(
            f"The translation service rejected the request (HTTP {status})."
        )


def normalise_two_letter(lang: str) -> str:
    """Reduce a code such as ``en-GB`` to its two-letter base (``en``)."""
    return lang.strip().replace("_", "-").split("-")[0].lower()
