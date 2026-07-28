"""Example-sentence lookup tests. No network access."""

from __future__ import annotations

import unittest
from unittest import mock

import requests

from anki_translate_popup import examples as examples_module
from anki_translate_popup.examples import (
    MAX_QUERY_CHARS,
    MAX_UNSPACED_QUERY_CHARS,
    TatoebaExamples,
    is_example_worthy,
    to_iso3,
)


class FakeResponse:
    def __init__(self, payload=None, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def patch_get(**kwargs):
    return mock.patch.object(examples_module.requests, "get", **kwargs)


def tatoeba_payload(pairs):
    return {
        "paging": {},
        "results": [
            {
                "text": de,
                "translations": [[{"lang": "eng", "text": en}]] if en else [[]],
            }
            for de, en in pairs
        ],
    }


class LanguageCodeTest(unittest.TestCase):
    def test_common_codes(self):
        self.assertEqual(to_iso3("de"), "deu")
        self.assertEqual(to_iso3("en"), "eng")
        self.assertEqual(to_iso3("zh"), "cmn")

    def test_regional_codes_reduced(self):
        self.assertEqual(to_iso3("de-AT"), "deu")
        self.assertEqual(to_iso3("en_GB"), "eng")

    def test_unknown_language(self):
        self.assertIsNone(to_iso3("xx"))
        self.assertIsNone(to_iso3("auto"))


class WorthinessTest(unittest.TestCase):
    def test_single_word(self):
        self.assertTrue(is_example_worthy("Anleger"))

    def test_short_phrase(self):
        self.assertTrue(is_example_worthy("das grosse Haus"))

    def test_full_sentence_rejected(self):
        self.assertFalse(
            is_example_worthy("Das Haus ist gross und es steht in München.")
        )

    def test_too_many_words_rejected(self):
        self.assertFalse(is_example_worthy("eins zwei drei vier"))

    def test_too_long_rejected(self):
        self.assertFalse(is_example_worthy("a" * (MAX_QUERY_CHARS + 1)))

    def test_empty_rejected(self):
        self.assertFalse(is_example_worthy("   "))

    def test_short_chinese_phrase_is_accepted(self):
        self.assertTrue(is_example_worthy("漂亮房子", "zh-CN"))

    def test_chinese_sentence_is_gated_by_characters_not_spaces(self):
        text = "这" * (MAX_UNSPACED_QUERY_CHARS + 1)
        self.assertLess(len(text), MAX_QUERY_CHARS)
        self.assertFalse(is_example_worthy(text, "zh"))


class FetchTest(unittest.TestCase):
    def make(self, timeout: float = 10) -> TatoebaExamples:
        return TatoebaExamples(timeout)

    def test_happy_path(self):
        payload = tatoeba_payload(
            [
                ("Eine Gruppe von Anlegern versucht eine Übernahme.", "A group of investors."),
                ("Ausländische Anleger zogen ihr Geld zurück.", "Foreign investors withdrew."),
            ]
        )
        with patch_get(return_value=FakeResponse(payload)) as get:
            found = self.make().fetch("Anleger", "de", "en")

        self.assertEqual(len(found), 2)
        self.assertEqual(found[0].text, "Eine Gruppe von Anlegern versucht eine Übernahme.")
        self.assertEqual(found[0].translation, "A group of investors.")
        params = get.call_args[1]["params"]
        self.assertEqual(params["from"], "deu")
        self.assertEqual(params["to"], "eng")
        self.assertEqual(params["query"], "Anleger")
        self.assertEqual(get.call_args[1]["timeout"], 10)

    def test_limit_is_respected(self):
        payload = tatoeba_payload([(f"Satz {i}", f"Sentence {i}") for i in range(10)])
        with patch_get(return_value=FakeResponse(payload)):
            self.assertEqual(len(self.make().fetch("Haus", "de", "en", limit=3)), 3)

    def test_entries_without_a_matching_translation_are_skipped(self):
        payload = {
            "results": [
                {"text": "Nur Deutsch", "translations": [[{"lang": "fra", "text": "Français"}]]},
                {"text": "Mit Englisch", "translations": [[{"lang": "eng", "text": "With English"}]]},
            ]
        }
        with patch_get(return_value=FakeResponse(payload)):
            found = self.make().fetch("Haus", "de", "en")
        self.assertEqual([e.text for e in found], ["Mit Englisch"])

    def test_long_selection_makes_no_request(self):
        with patch_get() as get:
            self.assertEqual(
                self.make().fetch("Das Haus ist gross und schön gelegen.", "de", "en"), []
            )
        get.assert_not_called()

    def test_unsupported_language_makes_no_request(self):
        with patch_get() as get:
            self.assertEqual(self.make().fetch("Haus", "xx", "en"), [])
            self.assertEqual(self.make().fetch("Haus", "de", "zz"), [])
        get.assert_not_called()

    def test_auto_source_makes_no_request(self):
        # The translation coordinator replaces auto with the detected language;
        # direct unresolved calls still have no ISO 639-3 code to send.
        with patch_get() as get:
            self.assertEqual(self.make().fetch("Haus", "auto", "en"), [])
        get.assert_not_called()

    def test_long_unspaced_chinese_selection_makes_no_request(self):
        with patch_get() as get:
            self.assertEqual(
                self.make().fetch("这" * (MAX_UNSPACED_QUERY_CHARS + 1), "zh", "en"),
                [],
            )
        get.assert_not_called()

    # -- malformed and failing responses --

    def test_http_error_returns_empty(self):
        with patch_get(return_value=FakeResponse({}, status_code=503)):
            self.assertEqual(self.make().fetch("Haus", "de", "en"), [])

    def test_malformed_shapes_return_empty(self):
        for payload in ([], {"results": "nope"}, {}, {"results": [None, 5]}):
            with self.subTest(payload=payload):
                with patch_get(return_value=FakeResponse(payload)):
                    self.assertEqual(self.make().fetch("Haus", "de", "en"), [])

    def test_entry_without_text_is_skipped(self):
        payload = {"results": [{"translations": [[{"lang": "eng", "text": "x"}]]}]}
        with patch_get(return_value=FakeResponse(payload)):
            self.assertEqual(self.make().fetch("Haus", "de", "en"), [])

    def test_network_error_propagates_for_the_caller_to_log(self):
        with patch_get(side_effect=requests.exceptions.Timeout("slow")):
            with self.assertRaises(requests.exceptions.Timeout):
                self.make().fetch("Haus", "de", "en")

    def test_unicode_preserved(self):
        payload = tatoeba_payload([("Grüße aus München!", "Greetings from Munich!")])
        with patch_get(return_value=FakeResponse(payload)):
            found = self.make().fetch("Grüße", "de", "en")
        self.assertEqual(found[0].text, "Grüße aus München!")

    def test_html_in_a_sentence_is_returned_verbatim(self):
        # The JS layer renders with textContent, so markup must survive intact
        # rather than being mangled here.
        hostile = "<script>alert(1)</script> ist gefährlich"
        payload = tatoeba_payload([(hostile, "is dangerous")])
        with patch_get(return_value=FakeResponse(payload)):
            found = self.make().fetch("Haus", "de", "en")
        self.assertEqual(found[0].text, hostile)


if __name__ == "__main__":
    unittest.main()
