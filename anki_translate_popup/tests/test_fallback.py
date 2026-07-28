"""Provider-fallback tests.

Exercises `_translate_blocking` with the real cache and a stubbed provider
layer, so the fallback decision, the cache keying and the payload flags are all
covered without touching the network.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest import mock

import anki_translate_popup as addon
from anki_translate_popup.config import DEFAULTS, parse_config
from anki_translate_popup.translation.base import (
    ConfigurationError,
    NetworkError,
    ProviderError,
    TranslationResult,
    Translator,
)


class StubTranslator(Translator):
    """Records calls and either returns a result or raises."""

    def __init__(self, name: str, calls: List[str], outcome: Any) -> None:
        super().__init__(10)
        self._name = name
        self._calls = calls
        self._outcome = outcome

    def validate(self) -> None:
        if isinstance(self._outcome, ConfigurationError):
            self._calls.append(f"{self._name}:validate-failed")
            raise self._outcome

    def translate(self, request):  # type: ignore[override]
        self._calls.append(f"{self._name}:translate")
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return TranslationResult(
            text=self._outcome,
            source_lang="de",
            target_lang="en",
            provider=self._name,
        )


class FallbackTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

        # Point the module-level cache at a throwaway file and reset it.
        patcher = mock.patch.object(
            addon, "_CACHE_PATH", Path(self._tmp.name) / "cache.sqlite"
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        addon._cache = None
        addon._cache_lifetime_days = None
        self.addCleanup(self._reset_cache)

        self.calls: List[str] = []

        # The fallback path logs a warning by design; keep it out of test output.
        # `LoggingWarningTest` below asserts it is actually emitted.
        quiet = mock.patch.object(addon.logger, "warning")
        quiet.start()
        self.addCleanup(quiet.stop)

    def _reset_cache(self) -> None:
        addon._cache = None
        addon._cache_lifetime_days = None

    def configure(self, **overrides) -> Dict[str, Any]:
        raw = dict(DEFAULTS)
        raw.update(overrides)
        parse_config(raw)  # fail fast if the test itself is misconfigured
        return raw

    def run_translation(self, raw_config: Dict[str, Any], outcomes: Dict[str, Any], text: str = "das Haus"):
        """Run _translate_blocking with each provider stubbed by name."""

        def fake_build(config, provider=""):
            provider = provider or config.translation_provider
            return StubTranslator(provider, self.calls, outcomes[provider])

        with mock.patch.object(addon, "_raw_config", return_value=raw_config):
            with mock.patch.object(addon, "build_translator", side_effect=fake_build):
                return addon._translate_blocking(text)


class NoFallbackTest(FallbackTestBase):
    def test_primary_success(self):
        raw = self.configure(translation_provider="deepl", api_key="k:fx")
        payload = self.run_translation(raw, {"deepl": "the house"})
        self.assertEqual(payload["text"], "the house")
        self.assertEqual(payload["provider"], "deepl")
        self.assertFalse(payload["usedFallback"])
        self.assertFalse(payload["cached"])

    def test_primary_failure_propagates_when_no_fallback(self):
        raw = self.configure(translation_provider="deepl", api_key="k:fx")
        with self.assertRaises(NetworkError):
            self.run_translation(raw, {"deepl": NetworkError("offline")})
        self.assertEqual(self.calls, ["deepl:translate"])


class FallbackTest(FallbackTestBase):
    def base_config(self, **overrides):
        return self.configure(
            translation_provider="deepl",
            fallback_provider="google_unofficial",
            api_key="k:fx",
            **overrides,
        )

    def test_fallback_used_on_network_error(self):
        payload = self.run_translation(
            self.base_config(),
            {"deepl": NetworkError("offline"), "google_unofficial": "the house"},
        )
        self.assertEqual(payload["text"], "the house")
        self.assertEqual(payload["provider"], "google_unofficial")
        self.assertTrue(payload["usedFallback"])
        self.assertEqual(self.calls, ["deepl:translate", "google_unofficial:translate"])

    def test_fallback_used_on_missing_api_key(self):
        payload = self.run_translation(
            self.base_config(),
            {
                "deepl": ConfigurationError("DeepL requires an API key."),
                "google_unofficial": "the house",
            },
        )
        self.assertTrue(payload["usedFallback"])
        self.assertEqual(payload["provider"], "google_unofficial")
        # validate() failed, so the primary never issued a request.
        self.assertEqual(
            self.calls, ["deepl:validate-failed", "google_unofficial:translate"]
        )

    def test_fallback_used_on_quota_error(self):
        payload = self.run_translation(
            self.base_config(),
            {"deepl": ProviderError("quota used up"), "google_unofficial": "the house"},
        )
        self.assertTrue(payload["usedFallback"])

    def test_fallback_not_used_when_primary_succeeds(self):
        payload = self.run_translation(
            self.base_config(),
            {"deepl": "the house", "google_unofficial": "WRONG"},
        )
        self.assertEqual(payload["text"], "the house")
        self.assertFalse(payload["usedFallback"])
        self.assertEqual(self.calls, ["deepl:translate"])

    def test_both_failing_reports_both_reasons(self):
        with self.assertRaises(ProviderError) as ctx:
            self.run_translation(
                self.base_config(),
                {
                    "deepl": NetworkError("deepl offline"),
                    "google_unofficial": NetworkError("google offline"),
                },
            )
        message = str(ctx.exception)
        self.assertIn("deepl", message)
        self.assertIn("deepl offline", message)
        self.assertIn("google_unofficial", message)
        self.assertIn("google offline", message)


class FallbackCacheTest(FallbackTestBase):
    def test_fallback_result_is_cached_under_the_fallback_provider(self):
        raw = self.configure(
            translation_provider="deepl",
            fallback_provider="google_unofficial",
            api_key="k:fx",
        )
        outcomes = {"deepl": NetworkError("offline"), "google_unofficial": "the house"}

        first = self.run_translation(raw, outcomes)
        self.assertTrue(first["usedFallback"])
        self.assertFalse(first["cached"])

        # Second run: the primary still fails, the fallback answers from cache.
        self.calls.clear()
        second = self.run_translation(raw, outcomes)
        self.assertTrue(second["usedFallback"])
        self.assertTrue(second["cached"])
        self.assertEqual(second["text"], "the house")
        self.assertEqual(self.calls, ["deepl:translate"])  # no second network call

    def test_cache_does_not_leak_between_providers(self):
        """A DeepL result must never be served as a Google one, or vice versa."""
        deepl_only = self.configure(translation_provider="deepl", api_key="k:fx")
        self.run_translation(deepl_only, {"deepl": "deepl answer"})

        google_only = self.configure(translation_provider="google_unofficial")
        payload = self.run_translation(google_only, {"google_unofficial": "google answer"})
        self.assertEqual(payload["text"], "google answer")
        self.assertFalse(payload["cached"])


class LoggingWarningTest(FallbackTestBase):
    def test_falling_back_is_logged_not_silent(self):
        raw = self.configure(
            translation_provider="deepl",
            fallback_provider="google_unofficial",
            api_key="k:fx",
        )
        self.run_translation(
            raw, {"deepl": NetworkError("offline"), "google_unofficial": "the house"}
        )
        addon.logger.warning.assert_called_once()
        message = addon.logger.warning.call_args[0]
        self.assertIn("fallback", message[0])


class FallbackConfigTest(unittest.TestCase):
    def config_with(self, **overrides):
        raw = dict(DEFAULTS)
        raw.update(overrides)
        return raw

    def test_default_is_disabled(self):
        self.assertEqual(parse_config(DEFAULTS).fallback_provider, "")

    def test_valid_fallback_accepted(self):
        config = parse_config(
            self.config_with(translation_provider="deepl", fallback_provider="google_unofficial")
        )
        self.assertEqual(config.fallback_provider, "google_unofficial")

    def test_unknown_fallback_rejected(self):
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config(self.config_with(fallback_provider="bing"))
        self.assertIn("fallback_provider", str(ctx.exception))

    def test_fallback_equal_to_primary_rejected(self):
        with self.assertRaises(ConfigurationError) as ctx:
            parse_config(
                self.config_with(
                    translation_provider="deepl", fallback_provider="deepl"
                )
            )
        self.assertIn("must differ", str(ctx.exception))

    def test_fallback_is_case_insensitive(self):
        config = parse_config(
            self.config_with(translation_provider="deepl", fallback_provider="Google_Unofficial")
        )
        self.assertEqual(config.fallback_provider, "google_unofficial")

    def test_fallback_not_exposed_to_the_webview(self):
        payload = parse_config(DEFAULTS).for_webview()
        self.assertNotIn("fallbackProvider", payload)


if __name__ == "__main__":
    unittest.main()
