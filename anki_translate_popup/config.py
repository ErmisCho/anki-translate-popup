"""Typed, validated view over Anki's add-on configuration.

Anki hands add-ons a plain ``dict`` merged from ``config.json`` (defaults) and
``meta.json`` (user overrides). Users edit that JSON by hand, so every value is
treated as untrusted here: wrong types and out-of-range numbers are reported
with an actionable message instead of blowing up somewhere deep in a worker
thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .translation.base import ConfigurationError

#: Bounds chosen so a typo cannot hang the UI or hammer a provider.
MIN_TIMEOUT_SECONDS = 1.0
MAX_TIMEOUT_SECONDS = 120.0
MIN_SPEECH_RATE = 0.1
MAX_SPEECH_RATE = 10.0
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 40
MAX_CACHE_LIFETIME_DAYS = 3650
MAX_CACHE_ENTRIES = 1_000_000
MAX_TTS_CACHE_MB = 10_000

VALID_PROVIDERS = ("deepl", "libretranslate", "google_unofficial")
#: "auto" prefers an installed system voice and only goes online without one.
VALID_TTS_PROVIDERS = ("auto", "system", "google_unofficial")
#: "first-line" speaks only the headword; "full" speaks the whole side.
VALID_CARD_SPEECH_SCOPES = ("first-line", "full")

#: Must stay in sync with config.json - Anki merges that file over these.
DEFAULTS: Dict[str, Any] = {
    "translation_provider": "google_unofficial",
    "fallback_provider": "",
    "source_language": "de",
    "target_language": "en",
    "api_key": "",
    "libretranslate_endpoint": "https://libretranslate.com",
    "enable_google_unofficial": True,
    "request_timeout_seconds": 10,
    "cache_enabled": True,
    "cache_lifetime_days": 30,
    "cache_max_entries": 5000,
    "tts_cache_max_mb": 100,
    "enable_in_previewer": True,
    "lookup_shortcut": "Ctrl+Shift+T",
    "pronounce_prompt_shortcut": "x",
    "pronounce_answer_shortcut": "c",
    "picker_languages": ["de", "en", "fr", "es", "it", "nl", "pt", "pl", "tr", "el", "ru"],
    "auto_translate": True,
    "auto_pronounce": True,
    "auto_pronounce_card": True,
    "auto_pronounce_answer": False,
    "card_speech_scope": "first-line",
    "expand_abbreviations": True,
    "show_examples": True,
    "tts_provider": "auto",
    "speech_language": "de-DE",
    "preferred_voice": "",
    "speech_rate": 0.9,
    "popup_font_size": 14,
    "debug_logging": False,
}


@dataclass(frozen=True)
class AddonConfig:
    translation_provider: str
    fallback_provider: str  # "" means no fallback
    source_language: str
    target_language: str
    api_key: str
    libretranslate_endpoint: str
    enable_google_unofficial: bool
    request_timeout_seconds: float
    cache_enabled: bool
    cache_lifetime_days: int
    cache_max_entries: int
    tts_cache_max_mb: int
    enable_in_previewer: bool
    lookup_shortcut: str
    pronounce_prompt_shortcut: str
    pronounce_answer_shortcut: str
    picker_languages: Tuple[str, ...]
    auto_translate: bool
    auto_pronounce: bool
    auto_pronounce_card: bool
    auto_pronounce_answer: bool
    card_speech_scope: str
    expand_abbreviations: bool
    show_examples: bool
    tts_provider: str
    speech_language: str
    preferred_voice: str
    speech_rate: float
    popup_font_size: int
    debug_logging: bool

    @property
    def cache_lifetime_seconds(self) -> int:
        return self.cache_lifetime_days * 86400

    @property
    def speak_first_line_only(self) -> bool:
        return self.card_speech_scope == "first-line"

    def for_webview(self) -> Dict[str, Any]:
        """The subset the JavaScript layer needs.

        Deliberately excludes ``api_key`` and every other secret: this dict is
        serialised into the reviewer page.
        """
        return {
            "sourceLanguage": self.source_language,
            "targetLanguage": self.target_language,
            "autoTranslate": self.auto_translate,
            "autoPronounce": self.auto_pronounce,
            "autoPronounceCard": self.auto_pronounce_card,
            "autoPronounceAnswer": self.auto_pronounce_answer,
            "showExamples": self.show_examples,
            "expandAbbreviations": self.expand_abbreviations,
            "lookupShortcut": self.lookup_shortcut,
            "pronouncePromptShortcut": self.pronounce_prompt_shortcut,
            "pronounceAnswerShortcut": self.pronounce_answer_shortcut,
            "pickerLanguages": list(self.picker_languages),
            "ttsProvider": self.tts_provider,
            "speechLanguage": self.speech_language,
            "preferredVoice": self.preferred_voice,
            "speechRate": self.speech_rate,
            "fontSize": self.popup_font_size,
            "debug": self.debug_logging,
        }


def _require_str(raw: Mapping[str, Any], key: str, errors: List[str]) -> str:
    value = raw.get(key, DEFAULTS[key])
    if not isinstance(value, str):
        errors.append(f"'{key}' must be text, got {type(value).__name__}.")
        return str(DEFAULTS[key])
    return value.strip()


def _require_bool(raw: Mapping[str, Any], key: str, errors: List[str]) -> bool:
    value = raw.get(key, DEFAULTS[key])
    if not isinstance(value, bool):
        errors.append(f"'{key}' must be true or false, got {value!r}.")
        return bool(DEFAULTS[key])
    return value


def _require_number(
    raw: Mapping[str, Any],
    key: str,
    errors: List[str],
    minimum: float,
    maximum: float,
) -> float:
    value = raw.get(key, DEFAULTS[key])
    # bool is a subclass of int; reject it explicitly so `true` is not read as 1.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append(f"'{key}' must be a number, got {value!r}.")
        return float(DEFAULTS[key])
    if not minimum <= value <= maximum:
        errors.append(f"'{key}' must be between {minimum:g} and {maximum:g}, got {value!r}.")
        return float(DEFAULTS[key])
    return float(value)


def _parse_language_code(value: str, *, allow_auto: bool) -> Optional[str]:
    """Normalise one language code, or return None if it is not one.

    Accepts ``de`` and ``en-GB`` style codes and rejects free text, so a typo
    surfaces here rather than as a cryptic HTTP 400 from a provider. Shared by
    the single-language settings and by ``picker_languages`` so the two cannot
    disagree about what a valid code looks like.
    """
    lang = value.strip().replace("_", "-")
    if not lang:
        return None
    if allow_auto and lang.lower() == "auto":
        return "auto"

    parts = lang.split("-")
    if not (2 <= len(parts[0]) <= 3) or not parts[0].isalpha():
        return None
    if len(parts) == 1:
        return parts[0].lower()
    if len(parts) > 2 or not parts[1].isalnum():
        return None
    return f"{parts[0].lower()}-{parts[1].upper()}"


def _normalise_language(value: str, key: str, errors: List[str], *, allow_auto: bool) -> str:
    if not value.strip():
        errors.append(f"'{key}' must not be empty.")
        return str(DEFAULTS[key])
    code = _parse_language_code(value, allow_auto=allow_auto)
    if code is None:
        errors.append(
            f"'{key}' must be a language code such as 'de', 'en' or 'en-GB', got {value!r}."
        )
        return str(DEFAULTS[key])
    return code


def _require_language_list(raw: Mapping[str, Any], key: str, errors: List[str]) -> Tuple[str, ...]:
    """Validate a list of language codes, dropping duplicates but keeping order."""
    value = raw.get(key, DEFAULTS[key])
    if not isinstance(value, (list, tuple)):
        errors.append(f"'{key}' must be a list of language codes, got {value!r}.")
        return tuple(DEFAULTS[key])

    codes: List[str] = []
    for item in value:
        if not isinstance(item, str):
            errors.append(f"'{key}' entries must be text, got {item!r}.")
            continue
        if not item.strip():
            continue
        # Same parser as source_language/target_language, so a code that is
        # valid as a target is always offerable in the picker.
        code = _parse_language_code(item, allow_auto=False)
        if code is None:
            errors.append(
                f"'{key}' entries must be language codes such as 'de' or "
                f"'en-GB', got {item!r}."
            )
            continue
        if code not in codes:
            codes.append(code)
    return tuple(codes) if codes else tuple(DEFAULTS[key])


def parse_config(raw: Optional[Mapping[str, Any]]) -> AddonConfig:
    """Validate ``raw`` and return a typed config.

    Raises :class:`ConfigurationError` listing *all* problems at once, so the
    user does not have to fix them one reload at a time.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ConfigurationError(
            "The add-on configuration must be a JSON object. Reset it via "
            "Tools > Add-ons > Config > Restore Defaults."
        )

    errors: List[str] = []

    provider = _require_str(raw, "translation_provider", errors).lower()
    if provider not in VALID_PROVIDERS:
        errors.append(
            f"'translation_provider' must be one of {', '.join(VALID_PROVIDERS)}, "
            f"got {provider!r}."
        )
        provider = str(DEFAULTS["translation_provider"])

    fallback = _require_str(raw, "fallback_provider", errors).lower()
    if fallback and fallback not in VALID_PROVIDERS:
        errors.append(
            f"'fallback_provider' must be empty or one of {', '.join(VALID_PROVIDERS)}, "
            f"got {fallback!r}."
        )
        fallback = ""
    if fallback and fallback == provider:
        errors.append(
            "'fallback_provider' must differ from 'translation_provider' "
            f"(both are {provider!r}); use \"\" to disable the fallback."
        )
        fallback = ""

    source = _normalise_language(
        _require_str(raw, "source_language", errors),
        "source_language",
        errors,
        allow_auto=True,
    )
    target = _normalise_language(
        _require_str(raw, "target_language", errors),
        "target_language",
        errors,
        allow_auto=False,
    )
    card_speech_scope = _require_str(raw, "card_speech_scope", errors).lower()
    if card_speech_scope not in VALID_CARD_SPEECH_SCOPES:
        errors.append(
            f"'card_speech_scope' must be one of {', '.join(VALID_CARD_SPEECH_SCOPES)}, "
            f"got {card_speech_scope!r}."
        )
        card_speech_scope = str(DEFAULTS["card_speech_scope"])

    tts_provider = _require_str(raw, "tts_provider", errors).lower()
    if tts_provider not in VALID_TTS_PROVIDERS:
        errors.append(
            f"'tts_provider' must be one of {', '.join(VALID_TTS_PROVIDERS)}, "
            f"got {tts_provider!r}."
        )
        tts_provider = str(DEFAULTS["tts_provider"])

    speech_language = _normalise_language(
        _require_str(raw, "speech_language", errors),
        "speech_language",
        errors,
        allow_auto=False,
    )

    lifetime = int(
        _require_number(raw, "cache_lifetime_days", errors, 0, MAX_CACHE_LIFETIME_DAYS)
    )

    config = AddonConfig(
        translation_provider=provider,
        fallback_provider=fallback,
        source_language=source,
        target_language=target,
        api_key=_require_str(raw, "api_key", errors),
        libretranslate_endpoint=_require_str(raw, "libretranslate_endpoint", errors),
        enable_google_unofficial=_require_bool(raw, "enable_google_unofficial", errors),
        request_timeout_seconds=_require_number(
            raw, "request_timeout_seconds", errors, MIN_TIMEOUT_SECONDS, MAX_TIMEOUT_SECONDS
        ),
        cache_enabled=_require_bool(raw, "cache_enabled", errors),
        cache_lifetime_days=lifetime,
        cache_max_entries=int(
            _require_number(raw, "cache_max_entries", errors, 0, MAX_CACHE_ENTRIES)
        ),
        tts_cache_max_mb=int(
            _require_number(raw, "tts_cache_max_mb", errors, 0, MAX_TTS_CACHE_MB)
        ),
        enable_in_previewer=_require_bool(raw, "enable_in_previewer", errors),
        lookup_shortcut=_require_str(raw, "lookup_shortcut", errors),
        pronounce_prompt_shortcut=_require_str(raw, "pronounce_prompt_shortcut", errors),
        pronounce_answer_shortcut=_require_str(raw, "pronounce_answer_shortcut", errors),
        picker_languages=_require_language_list(raw, "picker_languages", errors),
        auto_translate=_require_bool(raw, "auto_translate", errors),
        auto_pronounce=_require_bool(raw, "auto_pronounce", errors),
        auto_pronounce_card=_require_bool(raw, "auto_pronounce_card", errors),
        auto_pronounce_answer=_require_bool(raw, "auto_pronounce_answer", errors),
        card_speech_scope=card_speech_scope,
        expand_abbreviations=_require_bool(raw, "expand_abbreviations", errors),
        show_examples=_require_bool(raw, "show_examples", errors),
        tts_provider=tts_provider,
        speech_language=speech_language,
        preferred_voice=_require_str(raw, "preferred_voice", errors),
        speech_rate=_require_number(
            raw, "speech_rate", errors, MIN_SPEECH_RATE, MAX_SPEECH_RATE
        ),
        popup_font_size=int(
            _require_number(raw, "popup_font_size", errors, MIN_FONT_SIZE, MAX_FONT_SIZE)
        ),
        debug_logging=_require_bool(raw, "debug_logging", errors),
    )

    if errors:
        raise ConfigurationError(
            "The add-on configuration has problems:\n- " + "\n- ".join(errors)
        )
    return config
