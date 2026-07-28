"""Typed, validated view over Anki's add-on configuration.

Anki hands add-ons a plain ``dict`` merged from ``config.json`` (defaults) and
``meta.json`` (user overrides). Users edit that JSON by hand, so every value is
treated as untrusted here: wrong types and out-of-range numbers are reported
with an actionable message instead of blowing up somewhere deep in a worker
thread.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .translation.base import ConfigurationError, LanguageSupport

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
#: The Web Speech API does not report a voice's gender, so this is a
#: preference applied by name, not a guarantee - see _voice_gender in
#: reviewer.js. "any" takes whatever the language offers.
VALID_VOICE_GENDERS = ("female", "male", "any")

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
    "stop_speech_shortcut": "z",
    "picker_languages": ["de", "en", "fr", "es", "it", "nl", "pt", "pl", "tr", "el", "ru", "zh"],
    "deck_language_pairs": {},
    "auto_translate": True,
    "auto_pronounce": True,
    "auto_pronounce_card": True,
    "auto_pronounce_answer": False,
    "card_speech_scope": "first-line",
    "voice_gender": "female",
    "front_speech_language": "auto",
    "back_speech_language": "auto",
    "expand_abbreviations": True,
    "show_examples": True,
    "tts_provider": "google_unofficial",
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
    stop_speech_shortcut: str
    picker_languages: Tuple[str, ...]
    deck_language_pairs: Mapping[str, Tuple[str, str]]
    auto_translate: bool
    auto_pronounce: bool
    auto_pronounce_card: bool
    auto_pronounce_answer: bool
    card_speech_scope: str
    voice_gender: str
    front_speech_language: str
    back_speech_language: str
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

    def speech_language_for(self, *, is_answer: bool) -> str:
        """Which voice language one side of the card should be read in.

        A deck has a language per side, not one language: the front is the
        word you are learning, the back its translation. Speaking both with
        ``speech_language`` gives an English answer a German voice.

        ``auto`` follows the translation pair, which is what the deck already
        declares. It falls back to ``speech_language`` when the source is
        itself ``auto``, since there is then no configured language to use.
        """
        chosen = self._pair_speech_language(is_answer=is_answer)
        if chosen == "auto":
            return self.speech_language
        return self.with_configured_region(chosen)

    def _pair_speech_language(self, *, is_answer: bool) -> str:
        """The side's language as configured, still ``auto`` if nothing says."""
        chosen = self.back_speech_language if is_answer else self.front_speech_language
        if chosen == "auto":
            chosen = self.target_language if is_answer else self.source_language
        return chosen

    def speech_language_needs_detection(self, *, is_answer: bool) -> bool:
        """Whether the language of this side can only be found by looking.

        True when neither the voice setting nor the pair names one, which is
        the case a deck of mixed or unknown languages lands in. The caller has
        to ask the provider; the config has nothing left to offer.
        """
        return self._pair_speech_language(is_answer=is_answer) == "auto"

    def with_configured_region(self, lang: str) -> str:
        """Prefer the configured region for the same language: de -> de-AT.

        A user who asked for de-AT wants de-AT, not the bare "de" a pair is
        written in or a provider detects. An empty language means nothing is
        known, so the configured one stands.
        """
        if not lang:
            return self.speech_language
        if _base_language(lang) == _base_language(self.speech_language):
            return self.speech_language
        return lang

    def for_deck(self, deck_id: Optional[int]) -> "AddonConfig":
        """Apply a saved deck pair, falling back to the global pair."""
        pair = self.deck_language_pairs.get(str(deck_id)) if deck_id else None
        if not pair:
            return self
        return replace(self, source_language=pair[0], target_language=pair[1])

    def for_webview(
        self, language_support: Optional[LanguageSupport] = None
    ) -> Dict[str, Any]:
        """The non-secret subset the JavaScript layer needs."""
        if language_support is None:
            source_picker = target_picker = list(self.picker_languages)
        else:
            source_picker = _filter_picker(
                self.picker_languages, language_support[0], self.source_language
            )
            target_picker = _filter_picker(
                self.picker_languages, language_support[1], self.target_language
            )
        return {
            "sourceLanguage": self.source_language,
            "targetLanguage": self.target_language,
            "autoTranslate": self.auto_translate,
            "autoPronounce": self.auto_pronounce,
            "autoPronounceCard": self.auto_pronounce_card,
            "autoPronounceAnswer": self.auto_pronounce_answer,
            "showExamples": self.show_examples,
            "expandAbbreviations": self.expand_abbreviations,
            "frontSpeechLanguage": self.front_speech_language,
            "backSpeechLanguage": self.back_speech_language,
            "lookupShortcut": self.lookup_shortcut,
            "pronouncePromptShortcut": self.pronounce_prompt_shortcut,
            "pronounceAnswerShortcut": self.pronounce_answer_shortcut,
            "stopSpeechShortcut": self.stop_speech_shortcut,
            "pickerLanguages": list(self.picker_languages),
            "sourcePickerLanguages": source_picker,
            "targetPickerLanguages": target_picker,
            "ttsProvider": self.tts_provider,
            "voiceGender": self.voice_gender,
            "speechLanguage": self.speech_language,
            "preferredVoice": self.preferred_voice,
            "speechRate": self.speech_rate,
            "fontSize": self.popup_font_size,
            "debug": self.debug_logging,
        }


def _filter_picker(
    configured: Tuple[str, ...], supported: frozenset[str], current: str
) -> List[str]:
    """Keep provider-supported choices and the currently selected value."""
    normalised = {code.lower().replace("_", "-") for code in supported}

    def is_supported(code: str) -> bool:
        code = code.lower().replace("_", "-")
        simplified = {"zh-hans", "zh-cn", "zh-sg"}
        traditional = {"zh-hant", "zh-tw", "zh-hk", "zh-mo"}
        if code in traditional:
            return bool(traditional & normalised)
        if code in simplified:
            return bool(simplified & normalised)
        base = code.split("-")[0]
        return (
            code in normalised
            or base in normalised
            or ("-" not in code and any(item.startswith(base + "-") for item in normalised))
        )

    result = [code for code in configured if is_supported(code)]
    if current != "auto" and current not in result:
        result.append(current)
    return result


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


def _base_language(lang: str) -> str:
    """``en-GB`` -> ``en``. Shared by every "same language?" comparison."""
    return lang.strip().replace("_", "-").split("-")[0].lower()


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


def _require_deck_language_pairs(
    raw: Mapping[str, Any], errors: List[str]
) -> Dict[str, Tuple[str, str]]:
    key = "deck_language_pairs"
    value = raw.get(key, DEFAULTS[key])
    if not isinstance(value, Mapping):
        errors.append(f"'{key}' must be an object keyed by deck ID, got {value!r}.")
        return {}

    pairs: Dict[str, Tuple[str, str]] = {}
    for raw_deck_id, raw_pair in value.items():
        deck_id = str(raw_deck_id)
        if not deck_id.isdigit() or int(deck_id) <= 0:
            errors.append(f"'{key}' deck IDs must be positive integers, got {raw_deck_id!r}.")
            continue
        if (
            not isinstance(raw_pair, (list, tuple))
            or len(raw_pair) != 2
            or not all(isinstance(code, str) for code in raw_pair)
        ):
            errors.append(
                f"'{key}[{deck_id}]' must be [source, target] language codes."
            )
            continue
        source = _parse_language_code(raw_pair[0], allow_auto=True)
        target = _parse_language_code(raw_pair[1], allow_auto=False)
        if source is None or target is None:
            errors.append(
                f"'{key}[{deck_id}]' must contain valid source/target language codes."
            )
            continue
        pairs[deck_id] = (source, target)
    return pairs


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

    voice_gender = _require_str(raw, "voice_gender", errors).lower()
    if voice_gender not in VALID_VOICE_GENDERS:
        errors.append(
            f"'voice_gender' must be one of {', '.join(VALID_VOICE_GENDERS)}, "
            f"got {voice_gender!r}."
        )
        voice_gender = str(DEFAULTS["voice_gender"])

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
        stop_speech_shortcut=_require_str(raw, "stop_speech_shortcut", errors),
        picker_languages=_require_language_list(raw, "picker_languages", errors),
        deck_language_pairs=_require_deck_language_pairs(raw, errors),
        auto_translate=_require_bool(raw, "auto_translate", errors),
        auto_pronounce=_require_bool(raw, "auto_pronounce", errors),
        auto_pronounce_card=_require_bool(raw, "auto_pronounce_card", errors),
        auto_pronounce_answer=_require_bool(raw, "auto_pronounce_answer", errors),
        card_speech_scope=card_speech_scope,
        voice_gender=voice_gender,
        front_speech_language=_normalise_language(
            _require_str(raw, "front_speech_language", errors),
            "front_speech_language",
            errors,
            allow_auto=True,
        ),
        back_speech_language=_normalise_language(
            _require_str(raw, "back_speech_language", errors),
            "back_speech_language",
            errors,
            allow_auto=True,
        ),
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
