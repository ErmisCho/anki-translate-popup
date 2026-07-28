"""Translation provider tests.

Every HTTP call is stubbed - the suite never touches the network and never
spends a paid API quota.
"""

from __future__ import annotations

import json
import unittest
from typing import Any, Optional
from unittest import mock

import requests

from anki_translate_popup import _js_json
from anki_translate_popup.config import DEFAULTS, parse_config
from anki_translate_popup.translation import (
    ConfigurationError,
    DeepLTranslator,
    GoogleUnofficialTranslator,
    LibreTranslateTranslator,
    NetworkError,
    ProviderError,
    TranslationRequest,
    build_translator,
)
from anki_translate_popup.translation import base as base_module


class FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, payload: Any = None, status_code: int = 200, malformed: bool = False):
        self._payload = payload
        self.status_code = status_code
        self._malformed = malformed

    def json(self) -> Any:
        if self._malformed:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


def patch_request(**kwargs):
    """Patch the shared HTTP entry point used by every provider."""
    return mock.patch.object(base_module.requests, "request", **kwargs)


def req(text: str = "das Haus", source: str = "de", target: str = "en") -> TranslationRequest:
    return TranslationRequest(text=text, source_lang=source, target_lang=target)


# -- DeepL -------------------------------------------------------------------


class DeepLTest(unittest.TestCase):
    def make(self, api_key: str = "key-123:fx", timeout: float = 10) -> DeepLTranslator:
        return DeepLTranslator(timeout, api_key)

    def test_happy_path(self):
        payload = {"translations": [{"detected_source_language": "DE", "text": "the house"}]}
        with patch_request(return_value=FakeResponse(payload)) as request:
            result = self.make().translate(req())

        self.assertEqual(result.text, "the house")
        self.assertEqual(result.source_lang, "de")
        self.assertEqual(result.target_lang, "en")
        self.assertEqual(result.provider, "deepl")

        _, kwargs = request.call_args
        self.assertEqual(kwargs["json"]["text"], ["das Haus"])
        self.assertEqual(kwargs["json"]["source_lang"], "DE")
        self.assertEqual(kwargs["json"]["target_lang"], "EN")
        self.assertEqual(kwargs["timeout"], 10)
        self.assertEqual(kwargs["headers"]["Authorization"], "DeepL-Auth-Key key-123:fx")

    def test_free_key_uses_free_endpoint(self):
        payload = {"translations": [{"text": "x"}]}
        with patch_request(return_value=FakeResponse(payload)) as request:
            self.make("abc:fx").translate(req())
        self.assertIn("api-free.deepl.com", request.call_args[0][1])

    def test_pro_key_uses_pro_endpoint(self):
        payload = {"translations": [{"text": "x"}]}
        with patch_request(return_value=FakeResponse(payload)) as request:
            self.make("abc").translate(req())
        self.assertIn("://api.deepl.com", request.call_args[0][1])

    def test_auto_source_omits_source_lang(self):
        payload = {"translations": [{"detected_source_language": "DE", "text": "the house"}]}
        with patch_request(return_value=FakeResponse(payload)) as request:
            result = self.make().translate(req(source="auto"))
        self.assertNotIn("source_lang", request.call_args[1]["json"])
        self.assertEqual(result.source_lang, "de")

    def test_regional_source_reduced_to_two_letters(self):
        payload = {"translations": [{"text": "x"}]}
        with patch_request(return_value=FakeResponse(payload)) as request:
            self.make().translate(req(source="de-AT"))
        self.assertEqual(request.call_args[1]["json"]["source_lang"], "DE")

    def test_missing_api_key_is_a_configuration_error(self):
        with patch_request() as request:
            with self.assertRaises(ConfigurationError) as ctx:
                self.make(api_key="  ").translate(req())
        request.assert_not_called()  # nothing is sent without a key
        self.assertIn("api_key", str(ctx.exception))

    def test_unicode_is_preserved(self):
        payload = {"translations": [{"detected_source_language": "DE", "text": "Greetings, straße"}]}
        with patch_request(return_value=FakeResponse(payload)) as request:
            result = self.make().translate(req(text="Grüße über die Straße – schön!"))
        self.assertEqual(request.call_args[1]["json"]["text"], ["Grüße über die Straße – schön!"])
        self.assertEqual(result.text, "Greetings, straße")

    # -- malformed responses --

    def test_non_dict_response(self):
        with patch_request(return_value=FakeResponse(["unexpected"])):
            with self.assertRaises(ProviderError):
                self.make().translate(req())

    def test_empty_translations_list(self):
        with patch_request(return_value=FakeResponse({"translations": []})):
            with self.assertRaises(ProviderError):
                self.make().translate(req())

    def test_missing_translations_key(self):
        with patch_request(return_value=FakeResponse({"unexpected": 1})):
            with self.assertRaises(ProviderError):
                self.make().translate(req())

    def test_error_message_is_surfaced(self):
        with patch_request(return_value=FakeResponse({"message": "Bad request reason"})):
            with self.assertRaises(ProviderError) as ctx:
                self.make().translate(req())
        self.assertIn("Bad request reason", str(ctx.exception))

    def test_translation_entry_without_text(self):
        with patch_request(return_value=FakeResponse({"translations": [{"foo": "bar"}]})):
            with self.assertRaises(ProviderError):
                self.make().translate(req())

    def test_text_of_wrong_type(self):
        with patch_request(return_value=FakeResponse({"translations": [{"text": 42}]})):
            with self.assertRaises(ProviderError):
                self.make().translate(req())

    def test_body_is_not_json(self):
        with patch_request(return_value=FakeResponse(malformed=True)):
            with self.assertRaises(ProviderError) as ctx:
                self.make().translate(req())
        self.assertIn("malformed", str(ctx.exception).lower())


# -- HTTP status handling ----------------------------------------------------


class StatusCodeTest(unittest.TestCase):
    def translate_with_status(self, status: int):
        translator = DeepLTranslator(10, "key:fx")
        with patch_request(return_value=FakeResponse({}, status_code=status)):
            translator.translate(req())

    def test_401_and_403_point_at_the_api_key(self):
        for status in (401, 403):
            with self.subTest(status=status):
                with self.assertRaises(ConfigurationError) as ctx:
                    self.translate_with_status(status)
                self.assertIn("api_key", str(ctx.exception))

    def test_429_mentions_rate_limiting(self):
        with self.assertRaises(ProviderError) as ctx:
            self.translate_with_status(429)
        self.assertIn("rate-limiting", str(ctx.exception))

    def test_456_mentions_quota(self):
        with self.assertRaises(ProviderError) as ctx:
            self.translate_with_status(456)
        self.assertIn("quota", str(ctx.exception))

    def test_500_is_a_provider_error(self):
        with self.assertRaises(ProviderError) as ctx:
            self.translate_with_status(503)
        self.assertIn("server error", str(ctx.exception))

    def test_other_4xx_is_a_provider_error(self):
        with self.assertRaises(ProviderError):
            self.translate_with_status(400)

    def test_success_statuses_pass_through(self):
        translator = DeepLTranslator(10, "key:fx")
        payload = {"translations": [{"text": "ok"}]}
        with patch_request(return_value=FakeResponse(payload, status_code=200)):
            self.assertEqual(translator.translate(req()).text, "ok")


# -- network failures --------------------------------------------------------


class NetworkFailureTest(unittest.TestCase):
    def assert_network_error(self, exception: Exception, expected_fragment: str):
        translator = DeepLTranslator(7.5, "key:fx")
        with patch_request(side_effect=exception):
            with self.assertRaises(NetworkError) as ctx:
                translator.translate(req())
        self.assertIn(expected_fragment, str(ctx.exception))

    def test_timeout(self):
        self.assert_network_error(requests.exceptions.Timeout("slow"), "timed out")

    def test_read_timeout_is_a_timeout(self):
        self.assert_network_error(requests.exceptions.ReadTimeout("slow"), "timed out")

    def test_timeout_message_names_the_configured_value(self):
        self.assert_network_error(requests.exceptions.Timeout("slow"), "7.5 seconds")

    def test_connection_error(self):
        self.assert_network_error(
            requests.exceptions.ConnectionError("no route"), "Could not reach"
        )

    def test_dns_failure_is_a_connection_error(self):
        self.assert_network_error(
            requests.exceptions.ConnectionError("Name or service not known"),
            "internet connection",
        )

    def test_ssl_error(self):
        self.assert_network_error(requests.exceptions.SSLError("bad cert"), "secure connection")

    def test_generic_request_exception(self):
        self.assert_network_error(
            requests.exceptions.TooManyRedirects("loop"), "request failed"
        )

    def test_timeout_value_is_actually_passed_to_requests(self):
        translator = DeepLTranslator(3.5, "key:fx")
        payload = {"translations": [{"text": "ok"}]}
        with patch_request(return_value=FakeResponse(payload)) as request:
            translator.translate(req())
        self.assertEqual(request.call_args[1]["timeout"], 3.5)


# -- LibreTranslate ----------------------------------------------------------


class LibreTranslateTest(unittest.TestCase):
    def make(self, endpoint: str = "http://localhost:5000", api_key: str = ""):
        return LibreTranslateTranslator(10, endpoint, api_key)

    def test_happy_path(self):
        with patch_request(return_value=FakeResponse({"translatedText": "the house"})) as request:
            result = self.make().translate(req())
        self.assertEqual(result.text, "the house")
        self.assertEqual(result.source_lang, "de")
        self.assertEqual(result.provider, "libretranslate")
        self.assertEqual(request.call_args[0][1], "http://localhost:5000/translate")
        self.assertEqual(request.call_args[1]["json"]["source"], "de")
        self.assertEqual(request.call_args[1]["json"]["format"], "text")

    def test_trailing_slash_is_trimmed(self):
        with patch_request(return_value=FakeResponse({"translatedText": "x"})) as request:
            self.make("http://localhost:5000/").translate(req())
        self.assertEqual(request.call_args[0][1], "http://localhost:5000/translate")

    def test_detected_language_is_used(self):
        payload = {
            "translatedText": "the house",
            "detectedLanguage": {"language": "DE", "confidence": 98},
        }
        with patch_request(return_value=FakeResponse(payload)):
            result = self.make().translate(req(source="auto"))
        self.assertEqual(result.source_lang, "de")

    def test_auto_source_is_sent_as_auto(self):
        with patch_request(return_value=FakeResponse({"translatedText": "x"})) as request:
            self.make().translate(req(source="auto"))
        self.assertEqual(request.call_args[1]["json"]["source"], "auto")

    def test_regional_codes_are_reduced(self):
        with patch_request(return_value=FakeResponse({"translatedText": "x"})) as request:
            self.make().translate(req(source="de-AT", target="en-GB"))
        body = request.call_args[1]["json"]
        self.assertEqual(body["source"], "de")
        self.assertEqual(body["target"], "en")

    def test_api_key_included_only_when_set(self):
        with patch_request(return_value=FakeResponse({"translatedText": "x"})) as request:
            self.make().translate(req())
        self.assertNotIn("api_key", request.call_args[1]["json"])

        with patch_request(return_value=FakeResponse({"translatedText": "x"})) as request:
            self.make(api_key="secret").translate(req())
        self.assertEqual(request.call_args[1]["json"]["api_key"], "secret")

    def test_empty_endpoint_rejected(self):
        with self.assertRaises(ConfigurationError) as ctx:
            self.make(endpoint="").translate(req())
        self.assertIn("libretranslate_endpoint", str(ctx.exception))

    def test_endpoint_without_scheme_rejected(self):
        with self.assertRaises(ConfigurationError) as ctx:
            self.make(endpoint="localhost:5000").translate(req())
        self.assertIn("http://", str(ctx.exception))

    def test_error_field_is_surfaced(self):
        with patch_request(return_value=FakeResponse({"error": "Invalid target language"})):
            with self.assertRaises(ProviderError) as ctx:
                self.make().translate(req())
        self.assertIn("Invalid target language", str(ctx.exception))

    def test_malformed_shapes(self):
        for payload in ([1, 2, 3], {"translatedText": 42}, {}):
            with self.subTest(payload=payload):
                with patch_request(return_value=FakeResponse(payload)):
                    with self.assertRaises(ProviderError):
                        self.make().translate(req())

    def test_unicode_roundtrip(self):
        with patch_request(return_value=FakeResponse({"translatedText": "größer"})) as request:
            result = self.make().translate(req(text="Fußgängerübergang"))
        self.assertEqual(request.call_args[1]["json"]["q"], "Fußgängerübergang")
        self.assertEqual(result.text, "größer")


# -- Google (unofficial) -----------------------------------------------------


class GoogleUnofficialTest(unittest.TestCase):
    def make(self, enabled: bool = True):
        return GoogleUnofficialTranslator(10, enabled)

    def test_disabled_by_default_and_sends_nothing(self):
        with patch_request() as request:
            with self.assertRaises(ConfigurationError) as ctx:
                self.make(enabled=False).translate(req())
        request.assert_not_called()
        self.assertIn("enable_google_unofficial", str(ctx.exception))

    def test_happy_path(self):
        payload = [[["the house", "das Haus", None, None, 10]], None, "de"]
        with patch_request(return_value=FakeResponse(payload)) as request:
            result = self.make().translate(req())
        self.assertEqual(result.text, "the house")
        self.assertEqual(result.source_lang, "de")
        self.assertEqual(result.provider, "google_unofficial")
        self.assertEqual(request.call_args[1]["params"]["q"], "das Haus")
        self.assertEqual(request.call_args[1]["params"]["sl"], "de")

    def test_multiple_segments_are_joined(self):
        payload = [
            [
                ["The house is big. ", "Das Haus ist groß. ", None, None, 10],
                ["It is red.", "Es ist rot.", None, None, 10],
            ],
            None,
            "de",
        ]
        with patch_request(return_value=FakeResponse(payload)):
            result = self.make().translate(req())
        self.assertEqual(result.text, "The house is big. It is red.")

    def test_auto_detection(self):
        payload = [[["the house", "das Haus", None, None, 10]], None, "de-DE"]
        with patch_request(return_value=FakeResponse(payload)) as request:
            result = self.make().translate(req(source="auto"))
        self.assertEqual(request.call_args[1]["params"]["sl"], "auto")
        self.assertEqual(result.source_lang, "de")

    def test_malformed_shapes(self):
        for payload in ([], {}, [None], [[]], [[None]], [["not-a-list"]]):
            with self.subTest(payload=payload):
                with patch_request(return_value=FakeResponse(payload)):
                    with self.assertRaises(ProviderError):
                        self.make().translate(req())

    def test_unicode(self):
        payload = [[["greetings", "Grüße", None, None, 10]], None, "de"]
        with patch_request(return_value=FakeResponse(payload)) as request:
            result = self.make().translate(req(text="Grüße"))
        self.assertEqual(request.call_args[1]["params"]["q"], "Grüße")
        self.assertEqual(result.text, "greetings")


# -- factory -----------------------------------------------------------------


class BuildTranslatorTest(unittest.TestCase):
    def config(self, **overrides):
        raw = dict(DEFAULTS)
        raw.update(overrides)
        return parse_config(raw)

    def test_builds_each_provider(self):
        self.assertIsInstance(
            build_translator(self.config(translation_provider="deepl")), DeepLTranslator
        )
        self.assertIsInstance(
            build_translator(self.config(translation_provider="libretranslate")),
            LibreTranslateTranslator,
        )
        self.assertIsInstance(
            build_translator(self.config(translation_provider="google_unofficial")),
            GoogleUnofficialTranslator,
        )

    def test_google_can_be_hard_disabled(self):
        """Google ships enabled, but clearing the flag must still block it."""
        disabled = build_translator(
            self.config(
                translation_provider="google_unofficial", enable_google_unofficial=False
            )
        )
        with self.assertRaises(ConfigurationError) as ctx:
            disabled.validate()
        self.assertIn("enable_google_unofficial", str(ctx.exception))

        enabled = build_translator(
            self.config(translation_provider="google_unofficial", enable_google_unofficial=True)
        )
        enabled.validate()  # must not raise

    def test_disabled_google_sends_nothing(self):
        translator = build_translator(
            self.config(
                translation_provider="google_unofficial", enable_google_unofficial=False
            )
        )
        with patch_request() as request:
            with self.assertRaises(ConfigurationError):
                translator.translate(req())
        request.assert_not_called()

    def test_timeout_is_propagated(self):
        translator = build_translator(self.config(request_timeout_seconds=42))
        self.assertEqual(translator._timeout, 42.0)

    def test_every_provider_documents_its_privacy_implications(self):
        for name in ("deepl", "libretranslate", "google_unofficial"):
            with self.subTest(name=name):
                translator = build_translator(self.config(translation_provider=name))
                self.assertTrue(len(translator.privacy_note) > 40)


# -- escaping / injection ----------------------------------------------------


class JsEscapingTest(unittest.TestCase):
    """`_js_json` output is embedded both in a <script> tag and in web.eval."""

    def test_script_tag_cannot_be_closed_early(self):
        encoded = _js_json({"text": "</script><img src=x onerror=alert(1)>"})
        self.assertNotIn("</script>", encoded)
        self.assertIn("<\\/script>", encoded)

    def test_still_decodes_to_the_original_string(self):
        hostile = "</script><script>alert('xss')</script>"
        decoded = json.loads(_js_json({"text": hostile}).replace("<\\/", "</"))
        self.assertEqual(decoded["text"], hostile)

    def test_quotes_and_backslashes_are_escaped(self):
        encoded = _js_json({"text": 'he said "hi" \\ bye'})
        self.assertEqual(json.loads(encoded)["text"], 'he said "hi" \\ bye')

    def test_line_separators_are_escaped(self):
        # U+2028/U+2029 terminate a JavaScript string literal if left raw.
        encoded = _js_json({"text": "a b c"})
        self.assertNotIn(" ", encoded)
        self.assertNotIn(" ", encoded)
        self.assertEqual(json.loads(encoded)["text"], "a b c")

    def test_german_characters_are_ascii_escaped_and_survive(self):
        encoded = _js_json({"text": "Grüße über die Straße"})
        self.assertTrue(encoded.isascii())
        self.assertEqual(json.loads(encoded)["text"], "Grüße über die Straße")

    def test_newlines_and_control_characters(self):
        encoded = _js_json({"text": "line1\nline2\ttab\r\n"})
        self.assertNotIn("\n", encoded)
        self.assertEqual(json.loads(encoded)["text"], "line1\nline2\ttab\r\n")

    def test_html_from_a_provider_is_passed_through_verbatim(self):
        # Python must not mangle the text; the JS layer renders it with
        # textContent, so markup is displayed literally rather than parsed.
        payload = {"translations": [{"text": "<b>bold</b> & <i>italic</i>"}]}
        with patch_request(return_value=FakeResponse(payload)):
            result = DeepLTranslator(10, "k:fx").translate(req())
        self.assertEqual(result.text, "<b>bold</b> & <i>italic</i>")


if __name__ == "__main__":
    unittest.main()
