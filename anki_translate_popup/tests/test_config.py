"""Configuration validation tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from anki_translate_popup.config import (
    DEFAULTS,
    MAX_CACHE_ENTRIES,
    MAX_TTS_CACHE_MB,
    parse_config,
)
from anki_translate_popup.translation import build_translator
from anki_translate_popup.translation.base import ConfigurationError


def config_with(**overrides):
    raw = dict(DEFAULTS)
    raw.update(overrides)
    return raw


class ParseDefaultsTest(unittest.TestCase):
    def test_defaults_are_valid(self):
        config = parse_config(DEFAULTS)
        self.assertEqual(config.translation_provider, "google_unofficial")
        self.assertEqual(config.source_language, "de")
        self.assertEqual(config.target_language, "en")
        self.assertEqual(config.speech_language, "de-DE")
        self.assertTrue(config.cache_enabled)
        # Google is the shipped default, so its opt-in gate must be open;
        # setting it to false still hard-disables the provider.
        self.assertTrue(config.enable_google_unofficial)

    def test_default_provider_needs_no_api_key(self):
        """The shipped default must work out of the box with no credentials."""
        config = parse_config(DEFAULTS)
        self.assertEqual(config.api_key, "")
        build_translator(config).validate()  # must not raise

    def test_none_falls_back_to_defaults(self):
        self.assertEqual(parse_config(None).translation_provider, "google_unofficial")

    def test_config_json_matches_python_defaults(self):
        """config.json is what Anki actually ships; DEFAULTS is the fallback."""
        path = Path(__file__).resolve().parent.parent / "config.json"
        shipped = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(shipped, DEFAULTS)

    def test_documented_defaults_for_recent_options(self):
        """Guards against a key silently vanishing from both DEFAULTS and config.json."""
        self.assertEqual(DEFAULTS["cache_max_entries"], 5000)
        self.assertEqual(DEFAULTS["tts_cache_max_mb"], 100)
        self.assertTrue(DEFAULTS["enable_in_previewer"])
        # Online by default: a system voice is the robotic one, and cards
        # cannot use it at all without a user gesture.
        self.assertEqual(DEFAULTS["tts_provider"], "google_unofficial")
        self.assertEqual(DEFAULTS["voice_gender"], "female")
        self.assertEqual(DEFAULTS["lookup_shortcut"], "Ctrl+Shift+T")
        self.assertEqual(
            DEFAULTS["picker_languages"],
            ["de", "en", "fr", "es", "it", "nl", "pt", "pl", "tr", "el", "ru", "zh"],
        )
        self.assertEqual(DEFAULTS["deck_language_pairs"], {})

    def test_missing_keys_fall_back_to_defaults(self):
        config = parse_config({"api_key": "abc"})
        self.assertEqual(config.api_key, "abc")
        self.assertEqual(config.request_timeout_seconds, 10.0)

    def test_non_mapping_is_rejected(self):
        with self.assertRaises(ConfigurationError):
            parse_config(["not", "a", "mapping"])


class ProviderValidationTest(unittest.TestCase):
    def test_unknown_provider_rejected(self):
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config(config_with(translation_provider="bing"))
        self.assertIn("translation_provider", str(ctx.exception))

    def test_provider_is_case_insensitive(self):
        self.assertEqual(
            parse_config(config_with(translation_provider="DeepL")).translation_provider,
            "deepl",
        )

    def test_all_documented_providers_accepted(self):
        for name in ("deepl", "libretranslate", "google_unofficial"):
            self.assertEqual(
                parse_config(config_with(translation_provider=name)).translation_provider,
                name,
            )


class LanguageValidationTest(unittest.TestCase):
    def test_regional_code_is_normalised(self):
        config = parse_config(config_with(target_language="en_gb"))
        self.assertEqual(config.target_language, "en-GB")

    def test_auto_allowed_for_source_only(self):
        self.assertEqual(parse_config(config_with(source_language="auto")).source_language, "auto")
        with self.assertRaises(ConfigurationError):
            parse_config(config_with(target_language="auto"))

    def test_free_text_language_rejected(self):
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config(config_with(source_language="German please"))
        self.assertIn("source_language", str(ctx.exception))

    def test_empty_language_rejected(self):
        with self.assertRaises(ConfigurationError):
            parse_config(config_with(target_language="   "))


class DeckLanguagePairTest(unittest.TestCase):
    def test_deck_pair_overrides_the_global_pair(self):
        config = parse_config(
            config_with(deck_language_pairs={"42": ["es", "en"]})
        ).for_deck(42)
        self.assertEqual((config.source_language, config.target_language), ("es", "en"))

    def test_missing_deck_falls_back_to_the_global_pair(self):
        config = parse_config(
            config_with(
                source_language="de",
                target_language="en",
                deck_language_pairs={"42": ["es", "fr"]},
            )
        ).for_deck(7)
        self.assertEqual((config.source_language, config.target_language), ("de", "en"))

    def test_deck_pair_codes_are_normalised(self):
        config = parse_config(
            config_with(deck_language_pairs={"42": ["AUTO", "zh_tw"]})
        )
        self.assertEqual(config.deck_language_pairs["42"], ("auto", "zh-TW"))

    def test_invalid_deck_pair_is_rejected(self):
        for value in ([], {"deck": ["de", "en"]}, {"42": ["de"]}, {"42": ["de", "auto"]}):
            with self.subTest(value=value):
                with self.assertRaises(ConfigurationError) as ctx:
                    parse_config(config_with(deck_language_pairs=value))
                self.assertIn("deck_language_pairs", str(ctx.exception))


class TypeAndRangeTest(unittest.TestCase):
    def test_timeout_must_be_a_number(self):
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config(config_with(request_timeout_seconds="ten"))
        self.assertIn("request_timeout_seconds", str(ctx.exception))

    def test_timeout_out_of_range_rejected(self):
        for value in (0, -5, 1000):
            with self.subTest(value=value):
                with self.assertRaises(ConfigurationError):
                    parse_config(config_with(request_timeout_seconds=value))

    def test_bool_is_not_accepted_as_a_number(self):
        # `true` must not silently become 1 second.
        with self.assertRaises(ConfigurationError):
            parse_config(config_with(request_timeout_seconds=True))

    def test_non_bool_flag_rejected(self):
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config(config_with(cache_enabled="yes"))
        self.assertIn("cache_enabled", str(ctx.exception))

    def test_font_size_range(self):
        self.assertEqual(parse_config(config_with(popup_font_size=20)).popup_font_size, 20)
        with self.assertRaises(ConfigurationError):
            parse_config(config_with(popup_font_size=200))

    def test_speech_rate_range(self):
        self.assertEqual(parse_config(config_with(speech_rate=1.5)).speech_rate, 1.5)
        with self.assertRaises(ConfigurationError):
            parse_config(config_with(speech_rate=0))

    def test_cache_lifetime_zero_allowed(self):
        config = parse_config(config_with(cache_lifetime_days=0))
        self.assertEqual(config.cache_lifetime_days, 0)
        self.assertEqual(config.cache_lifetime_seconds, 0)

    def test_all_errors_reported_at_once(self):
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config(
                config_with(
                    translation_provider="nope",
                    request_timeout_seconds="soon",
                    popup_font_size=999,
                )
            )
        message = str(ctx.exception)
        self.assertIn("translation_provider", message)
        self.assertIn("request_timeout_seconds", message)
        self.assertIn("popup_font_size", message)

    def test_all_cache_and_reviewer_errors_reported_at_once(self):
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config(
                config_with(
                    cache_max_entries=-1,
                    tts_cache_max_mb="lots",
                    enable_in_previewer="yes",
                    picker_languages="de",
                )
            )
        message = str(ctx.exception)
        for key in (
            "cache_max_entries",
            "tts_cache_max_mb",
            "enable_in_previewer",
            "picker_languages",
        ):
            self.assertIn(key, message)


class CacheLimitTest(unittest.TestCase):
    """`cache_max_entries` and `tts_cache_max_mb` share the same bounds behaviour."""

    LIMITS = (
        ("cache_max_entries", MAX_CACHE_ENTRIES),
        ("tts_cache_max_mb", MAX_TTS_CACHE_MB),
    )

    def test_in_range_values_accepted(self):
        for key, maximum in self.LIMITS:
            for value in (1, 42, maximum):
                with self.subTest(key=key, value=value):
                    config = parse_config(config_with(**{key: value}))
                    self.assertEqual(getattr(config, key), value)

    def test_zero_means_unlimited(self):
        for key, _maximum in self.LIMITS:
            with self.subTest(key=key):
                self.assertEqual(getattr(parse_config(config_with(**{key: 0})), key), 0)

    def test_out_of_range_rejected(self):
        for key, maximum in self.LIMITS:
            for value in (-1, -5000, maximum + 1):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(ConfigurationError) as ctx:
                        parse_config(config_with(**{key: value}))
                    self.assertIn(key, str(ctx.exception))

    def test_string_rejected(self):
        for key, _maximum in self.LIMITS:
            with self.subTest(key=key):
                with self.assertRaises(ConfigurationError) as ctx:
                    parse_config(config_with(**{key: "5000"}))
                self.assertIn(key, str(ctx.exception))

    def test_bool_is_not_accepted_as_a_number(self):
        # `true` must not silently become an entry/megabyte budget of 1.
        for key, _maximum in self.LIMITS:
            with self.subTest(key=key):
                with self.assertRaises(ConfigurationError) as ctx:
                    parse_config(config_with(**{key: True}))
                self.assertIn(key, str(ctx.exception))


class ReviewerOptionTest(unittest.TestCase):
    def test_previewer_flag_accepts_both_booleans(self):
        for value in (True, False):
            with self.subTest(value=value):
                config = parse_config(config_with(enable_in_previewer=value))
                self.assertIs(config.enable_in_previewer, value)

    def test_previewer_flag_rejects_non_bool(self):
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config(config_with(enable_in_previewer="yes"))
        self.assertIn("enable_in_previewer", str(ctx.exception))

    def test_shortcut_default(self):
        self.assertEqual(parse_config(DEFAULTS).lookup_shortcut, "Ctrl+Shift+T")

    def test_empty_shortcut_disables_the_feature(self):
        self.assertEqual(parse_config(config_with(lookup_shortcut="")).lookup_shortcut, "")

    def test_shortcut_is_trimmed(self):
        config = parse_config(config_with(lookup_shortcut="  Ctrl+Alt+L  "))
        self.assertEqual(config.lookup_shortcut, "Ctrl+Alt+L")

    def test_whitespace_only_shortcut_becomes_disabled(self):
        self.assertEqual(parse_config(config_with(lookup_shortcut="   ")).lookup_shortcut, "")


class PickerLanguagesTest(unittest.TestCase):
    def test_regional_codes_accepted_like_the_single_language_settings(self):
        """Regression: the picker once rejected codes the languages accept.

        `target_language` allows "en-GB", so listing that same code in the
        picker must work too, or a user on en-GB cannot select their own
        target from the dropdown.
        """
        config = parse_config(
            config_with(target_language="en-GB", picker_languages=["de", "en_gb", "pt-BR"])
        )
        self.assertEqual(config.picker_languages, ("de", "en-GB", "pt-BR"))
        self.assertIn(config.target_language, config.picker_languages)

    def test_malformed_regional_codes_still_rejected(self):
        for bad in (["e-n"], ["en-"], ["en-GB-oed"], ["en-G B"]):
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigurationError):
                    parse_config(config_with(picker_languages=bad))

    def test_default_list_is_used(self):
        self.assertEqual(
            parse_config(DEFAULTS).picker_languages, tuple(DEFAULTS["picker_languages"])
        )

    def test_valid_list_keeps_order(self):
        config = parse_config(config_with(picker_languages=["fr", "de", "en"]))
        self.assertEqual(config.picker_languages, ("fr", "de", "en"))

    def test_codes_are_lower_cased(self):
        config = parse_config(config_with(picker_languages=["DE", "En", " fr "]))
        self.assertEqual(config.picker_languages, ("de", "en", "fr"))

    def test_duplicates_removed_keeping_first_position(self):
        config = parse_config(config_with(picker_languages=["de", "en", "DE", " en ", "fr"]))
        self.assertEqual(config.picker_languages, ("de", "en", "fr"))

    def test_three_letter_codes_accepted(self):
        config = parse_config(config_with(picker_languages=["deu", "eng"]))
        self.assertEqual(config.picker_languages, ("deu", "eng"))

    def test_non_list_rejected(self):
        for value in ("de", 5, {"de": True}):
            with self.subTest(value=value):
                with self.assertRaises(ConfigurationError) as ctx:
                    parse_config(config_with(picker_languages=value))
                self.assertIn("picker_languages", str(ctx.exception))

    def test_non_string_entry_rejected(self):
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config(config_with(picker_languages=["de", 7]))
        self.assertIn("picker_languages", str(ctx.exception))

    def test_invalid_codes_rejected(self):
        for value in ("d", "germ", "d1", "e-n"):
            with self.subTest(value=value):
                with self.assertRaises(ConfigurationError) as ctx:
                    parse_config(config_with(picker_languages=["de", value]))
                self.assertIn("picker_languages", str(ctx.exception))

    def test_empty_list_falls_back_to_defaults(self):
        """An empty picker would leave the user with no languages to switch to."""
        config = parse_config(config_with(picker_languages=[]))
        self.assertEqual(config.picker_languages, tuple(DEFAULTS["picker_languages"]))

    def test_blank_entries_are_dropped_without_an_error(self):
        config = parse_config(config_with(picker_languages=["de", "", "   ", "en"]))
        self.assertEqual(config.picker_languages, ("de", "en"))


class VoiceGenderTest(unittest.TestCase):
    def test_default_is_female(self):
        self.assertEqual(parse_config(DEFAULTS).voice_gender, "female")

    def test_every_documented_value_is_accepted(self):
        for value in ("female", "male", "any"):
            with self.subTest(value=value):
                self.assertEqual(
                    parse_config(config_with(voice_gender=value)).voice_gender, value
                )

    def test_case_is_ignored(self):
        self.assertEqual(parse_config(config_with(voice_gender="FEMALE")).voice_gender, "female")

    def test_unknown_value_is_rejected_by_name(self):
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config(config_with(voice_gender="neutral"))
        self.assertIn("voice_gender", str(ctx.exception))

    def test_reaches_the_webview(self):
        """The page picks the voice, so the preference has to get there."""
        payload = parse_config(config_with(voice_gender="male")).for_webview()
        self.assertEqual(payload["voiceGender"], "male")


class WebviewConfigTest(unittest.TestCase):
    def test_api_key_is_never_exposed_to_the_webview(self):
        config = parse_config(config_with(api_key="super-secret-key:fx"))
        payload = config.for_webview()
        self.assertNotIn("super-secret-key:fx", repr(payload))
        # The payload is serialised into the reviewer page, so check the wire form too.
        self.assertNotIn("super-secret-key:fx", json.dumps(payload))
        self.assertNotIn("apiKey", payload)
        self.assertNotIn("api_key", payload)

    def test_webview_payload_contents(self):
        payload = parse_config(DEFAULTS).for_webview()
        self.assertEqual(payload["speechLanguage"], "de-DE")
        self.assertEqual(payload["sourceLanguage"], "de")
        self.assertEqual(payload["targetLanguage"], "en")
        self.assertEqual(payload["fontSize"], 14)

    def test_webview_payload_exposes_reviewer_options(self):
        payload = parse_config(DEFAULTS).for_webview()
        self.assertEqual(payload["lookupShortcut"], "Ctrl+Shift+T")
        self.assertEqual(payload["pickerLanguages"], DEFAULTS["picker_languages"])
        # A plain list, not the internal tuple: the payload is handed to JSON
        # encoders and to code that compares it against config.json values.
        self.assertIsInstance(payload["pickerLanguages"], list)
        json.loads(json.dumps(payload))  # must not raise

    def test_provider_support_filters_each_translation_picker(self):
        config = parse_config(
            config_with(source_language="el", target_language="es")
        )
        support = (frozenset({"de", "zh"}), frozenset({"en", "zh-hans"}))
        payload = config.for_webview(support)
        self.assertEqual(payload["sourcePickerLanguages"], ["de", "zh", "el"])
        self.assertEqual(payload["targetPickerLanguages"], ["en", "zh", "es"])
        # Voice choices are not translation-provider capabilities.
        self.assertEqual(payload["pickerLanguages"], DEFAULTS["picker_languages"])

    def test_one_chinese_variant_does_not_enable_the_other(self):
        config = parse_config(
            config_with(picker_languages=["zh", "zh-TW"], target_language="en")
        )
        payload = config.for_webview(
            (frozenset({"zh"}), frozenset({"zh-hans", "en"}))
        )
        self.assertEqual(payload["targetPickerLanguages"], ["zh", "en"])

        for provider_code in ("zh-hant", "zh-tw"):
            traditional = config.for_webview(
                (frozenset({"zh"}), frozenset({provider_code, "en"}))
            )
            self.assertEqual(
                traditional["targetPickerLanguages"], ["zh", "zh-TW", "en"]
            )

    def test_missing_support_falls_back_to_the_unfiltered_list(self):
        payload = parse_config(DEFAULTS).for_webview(None)
        self.assertEqual(payload["sourcePickerLanguages"], DEFAULTS["picker_languages"])
        self.assertEqual(payload["targetPickerLanguages"], DEFAULTS["picker_languages"])

    def test_cache_lifetime_seconds(self):
        self.assertEqual(parse_config(config_with(cache_lifetime_days=2)).cache_lifetime_seconds, 172800)


if __name__ == "__main__":
    unittest.main()
