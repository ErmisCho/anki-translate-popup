"""Online text-to-speech tests. No network access."""

from __future__ import annotations

import unittest
from unittest import mock

import requests

from anki_translate_popup import tts as tts_module
from anki_translate_popup.tts import (
    MAX_CHUNK_CHARS,
    MAX_SPEECH_CHARS,
    GoogleTextToSpeech,
    SpeechError,
    split_for_speech,
)

# A minimal valid MPEG frame header; enough to pass the audio sniff.
MP3 = b"\xff\xf3\x84\xc4" + b"\x00" * 64
ID3 = b"ID3\x03\x00" + b"\x00" * 64


class FakeResponse:
    def __init__(self, content: bytes = MP3, status_code: int = 200):
        self.content = content
        self.status_code = status_code


def patch_get(**kwargs):
    return mock.patch.object(tts_module.requests, "get", **kwargs)


class SplitTest(unittest.TestCase):
    def test_short_text_is_one_chunk(self):
        self.assertEqual(split_for_speech("Das Haus"), ["Das Haus"])

    def test_empty_text_yields_nothing(self):
        self.assertEqual(split_for_speech("   "), [])

    def test_splits_on_word_boundaries(self):
        text = " ".join(["Haus"] * 100)  # 499 chars
        chunks = split_for_speech(text, limit=50)
        self.assertTrue(all(len(c) <= 50 for c in chunks))
        # No word may be broken across chunks.
        self.assertEqual(" ".join(chunks).split(), text.split())

    def test_long_single_word_is_hard_split(self):
        word = "a" * 250
        chunks = split_for_speech(word, limit=100)
        self.assertEqual(chunks, ["a" * 100, "a" * 100, "a" * 50])
        self.assertEqual("".join(chunks), word)

    def test_german_compound_noun_survives(self):
        text = "Donaudampfschifffahrtsgesellschaftskapitän fährt"
        chunks = split_for_speech(text)
        self.assertEqual(" ".join(chunks), text)

    def test_every_chunk_within_limit(self):
        text = "Grüße aus München! " * 40
        for chunk in split_for_speech(text):
            self.assertLessEqual(len(chunk), MAX_CHUNK_CHARS)


class SynthesizeTest(unittest.TestCase):
    def make(self, timeout: float = 10) -> GoogleTextToSpeech:
        return GoogleTextToSpeech(timeout)

    def test_happy_path(self):
        with patch_get(return_value=FakeResponse()) as get:
            audio = self.make().synthesize("Das Haus ist groß", "de-DE")
        self.assertEqual(audio, MP3)
        params = get.call_args[1]["params"]
        self.assertEqual(params["q"], "Das Haus ist groß")
        self.assertEqual(params["tl"], "de")  # de-DE reduced for the endpoint
        self.assertEqual(params["client"], "tw-ob")
        self.assertEqual(get.call_args[1]["timeout"], 10)

    def test_id3_prefixed_audio_accepted(self):
        with patch_get(return_value=FakeResponse(ID3)):
            self.assertEqual(self.make().synthesize("Haus", "de"), ID3)

    def test_long_text_is_fetched_in_segments_and_joined(self):
        text = " ".join(["Haus"] * 100)
        with patch_get(return_value=FakeResponse()) as get:
            audio = self.make().synthesize(text, "de")
        self.assertGreater(get.call_count, 1)
        self.assertEqual(audio, MP3 * get.call_count)

    def test_empty_text_rejected(self):
        with patch_get() as get:
            with self.assertRaises(SpeechError):
                self.make().synthesize("   ", "de")
        get.assert_not_called()

    def test_overlong_text_rejected_before_any_request(self):
        with patch_get() as get:
            with self.assertRaises(SpeechError) as ctx:
                self.make().synthesize("a" * (MAX_SPEECH_CHARS + 1), "de")
        get.assert_not_called()
        self.assertIn("too long", str(ctx.exception))

    def test_unicode_is_passed_through(self):
        with patch_get(return_value=FakeResponse()) as get:
            self.make().synthesize("Grüße über die Straße", "de")
        self.assertEqual(get.call_args[1]["params"]["q"], "Grüße über die Straße")

    # -- failure modes --

    def test_html_error_page_is_not_treated_as_audio(self):
        with patch_get(return_value=FakeResponse(b"<!DOCTYPE html><html>nope")):
            with self.assertRaises(SpeechError) as ctx:
                self.make().synthesize("Haus", "de")
        self.assertIn("not audio", str(ctx.exception))

    def test_empty_body_rejected(self):
        with patch_get(return_value=FakeResponse(b"")):
            with self.assertRaises(SpeechError) as ctx:
                self.make().synthesize("Haus", "de")
        self.assertIn("empty", str(ctx.exception))

    def test_rate_limit_message(self):
        with patch_get(return_value=FakeResponse(MP3, status_code=429)):
            with self.assertRaises(SpeechError) as ctx:
                self.make().synthesize("Haus", "de")
        self.assertIn("rate-limiting", str(ctx.exception))

    def test_http_error_message(self):
        with patch_get(return_value=FakeResponse(MP3, status_code=503)):
            with self.assertRaises(SpeechError) as ctx:
                self.make().synthesize("Haus", "de")
        self.assertIn("503", str(ctx.exception))

    def test_timeout(self):
        with patch_get(side_effect=requests.exceptions.Timeout("slow")):
            with self.assertRaises(SpeechError) as ctx:
                GoogleTextToSpeech(4.5).synthesize("Haus", "de")
        self.assertIn("timed out", str(ctx.exception))
        self.assertIn("4.5", str(ctx.exception))

    def test_connection_error(self):
        with patch_get(side_effect=requests.exceptions.ConnectionError("no route")):
            with self.assertRaises(SpeechError) as ctx:
                self.make().synthesize("Haus", "de")
        self.assertIn("Could not reach", str(ctx.exception))

    def test_generic_request_error(self):
        with patch_get(side_effect=requests.exceptions.TooManyRedirects("loop")):
            with self.assertRaises(SpeechError):
                self.make().synthesize("Haus", "de")

    def test_privacy_note_documented(self):
        self.assertIn("UNOFFICIAL", GoogleTextToSpeech.privacy_note)


class SniffTest(unittest.TestCase):
    def test_mp3_frame_sync_detected(self):
        self.assertTrue(tts_module._looks_like_mp3(b"\xff\xfb\x90\x00"))
        self.assertTrue(tts_module._looks_like_mp3(b"\xff\xf3\x84\xc4"))

    def test_id3_detected(self):
        self.assertTrue(tts_module._looks_like_mp3(b"ID3\x03"))

    def test_html_and_json_rejected(self):
        self.assertFalse(tts_module._looks_like_mp3(b"<html>"))
        self.assertFalse(tts_module._looks_like_mp3(b'{"error":1}'))
        self.assertFalse(tts_module._looks_like_mp3(b""))
        self.assertFalse(tts_module._looks_like_mp3(b"\xff"))


if __name__ == "__main__":
    unittest.main()
