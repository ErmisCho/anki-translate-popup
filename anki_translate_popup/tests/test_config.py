"""Configuration validation tests."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from anki_translate_popup.config import DEFAULTS, parse_config
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


class WebviewConfigTest(unittest.TestCase):
    def test_api_key_is_never_exposed_to_the_webview(self):
        config = parse_config(config_with(api_key="super-secret-key:fx"))
        payload = config.for_webview()
        self.assertNotIn("super-secret-key:fx", repr(payload))
        self.assertNotIn("apiKey", payload)
        self.assertNotIn("api_key", payload)

    def test_webview_payload_contents(self):
        payload = parse_config(DEFAULTS).for_webview()
        self.assertEqual(payload["speechLanguage"], "de-DE")
        self.assertEqual(payload["sourceLanguage"], "de")
        self.assertEqual(payload["targetLanguage"], "en")
        self.assertEqual(payload["fontSize"], 14)

    def test_cache_lifetime_seconds(self):
        self.assertEqual(parse_config(config_with(cache_lifetime_days=2)).cache_lifetime_seconds, 172800)


if __name__ == "__main__":
    unittest.main()
