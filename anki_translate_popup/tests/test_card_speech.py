"""Card auto-pronounce: which text gets spoken, and which options gate it."""

from __future__ import annotations

import unittest
from unittest import mock

import anki_translate_popup as addon
from anki_translate_popup.config import DEFAULTS
from anki_translate_popup.tts import MAX_SPEECH_CHARS


class CardSideTextTest(unittest.TestCase):
    def test_question_is_plain_text(self):
        self.assertEqual(
            addon.card_side_text("<div>Das Haus</div>", is_answer=False), "Das Haus"
        )

    def test_answer_drops_the_repeated_question(self):
        """Anki renders the answer as question + divider + answer."""
        rendered = "Das Haus<hr id=answer>the house"
        self.assertEqual(addon.card_side_text(rendered, is_answer=True), "the house")

    def test_answer_without_a_divider_is_used_whole(self):
        self.assertEqual(
            addon.card_side_text("<b>the house</b>", is_answer=True), "the house"
        )

    def test_question_keeps_its_divider_text(self):
        # The divider only means something on the answer side.
        self.assertEqual(
            addon.card_side_text("a<hr id=answer>b", is_answer=False), "a b"
        )

    def test_markup_and_whitespace_are_stripped(self):
        rendered = "  <div class='x'>Gr&uuml;&szlig;e</div>  "
        self.assertEqual(addon.card_side_text(rendered, is_answer=False), "Grüße")

    def test_sibling_blocks_do_not_run_together(self):
        self.assertEqual(
            addon.card_side_text("<div>Das Haus</div><div>ist groß</div>", is_answer=False),
            "Das Haus ist groß",
        )

    def test_sound_tags_are_not_read_aloud(self):
        rendered = "Das Haus [sound:hallo.mp3]"
        self.assertEqual(addon.card_side_text(rendered, is_answer=False), "Das Haus")

    def test_style_and_script_contents_are_not_read_aloud(self):
        rendered = "<style>.card { color: red; }</style><div>Das Haus</div>"
        self.assertEqual(addon.card_side_text(rendered, is_answer=False), "Das Haus")

    def test_empty_side(self):
        self.assertEqual(addon.card_side_text("<br>", is_answer=False), "")
        self.assertEqual(addon.card_side_text("", is_answer=True), "")

    def test_only_the_first_divider_splits(self):
        rendered = "q<hr id=answer>a<hr id=answer>b"
        self.assertEqual(addon.card_side_text(rendered, is_answer=True), "a b")


class FakeCard:
    def __init__(self, question: str = "Das Haus", answer: str = "Das Haus<hr id=answer>the house"):
        self._q = question
        self._a = answer

    def question(self) -> str:
        return self._q

    def answer(self) -> str:
        return self._a


class AutoPronounceGatingTest(unittest.TestCase):
    """The op must only be scheduled when it can actually work."""

    def setUp(self) -> None:
        self.scheduled = []

        class FakeQueryOp:
            def __init__(inner, *, parent, op, success):
                inner._op = op
                self.scheduled.append(inner)

            def without_collection(inner):
                return inner

            def failure(inner, _fn):
                return inner

            def run_in_background(inner):
                pass

        patcher = mock.patch.object(addon, "QueryOp", FakeQueryOp, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # The dedupe guard is module state; isolate each test from the last.
        addon._last_auto_spoken = None
        self.addCleanup(setattr, addon, "_last_auto_spoken", None)
        mw = mock.patch.object(addon, "mw", mock.MagicMock(), create=True)
        mw.start()
        self.addCleanup(mw.stop)

    def configure(self, **overrides):
        raw = dict(DEFAULTS)
        raw.update(overrides)
        return mock.patch.object(addon, "_raw_config", return_value=raw)

    def test_enabled_schedules_speech(self):
        with self.configure(auto_pronounce_card=True):
            addon.on_reviewer_did_show_question(FakeCard())
        self.assertEqual(len(self.scheduled), 1)

    def test_the_same_side_firing_twice_only_speaks_once(self):
        """Anki re-emits the hook on a re-render; two clips would queue up."""
        card = FakeCard()
        card.id = 42
        with self.configure(auto_pronounce_card=True):
            addon.on_reviewer_did_show_question(card)
            addon.on_reviewer_did_show_question(card)
        self.assertEqual(len(self.scheduled), 1)

    def test_the_other_side_is_not_deduplicated(self):
        card = FakeCard()
        card.id = 42
        with self.configure(auto_pronounce_card=True):
            addon.on_reviewer_did_show_question(card)
            addon.on_reviewer_did_show_answer(card)
        self.assertEqual(len(self.scheduled), 2)

    def test_a_different_card_is_not_deduplicated(self):
        first, second = FakeCard(), FakeCard()
        first.id, second.id = 1, 2
        with self.configure(auto_pronounce_card=True):
            addon.on_reviewer_did_show_question(first)
            addon.on_reviewer_did_show_question(second)
        self.assertEqual(len(self.scheduled), 2)

    def test_a_genuine_re_review_after_the_window_speaks_again(self):
        card = FakeCard()
        card.id = 42
        with self.configure(auto_pronounce_card=True):
            addon.on_reviewer_did_show_question(card)
            base = addon._last_auto_spoken[2]
            # Pretend the first showing was longer ago than the dedupe window.
            addon._last_auto_spoken = (42, False, base - addon.AUTO_SPEAK_DEDUPE_SECONDS - 1)
            addon.on_reviewer_did_show_question(card)
        self.assertEqual(len(self.scheduled), 2)

    def test_disabled_does_nothing(self):
        with self.configure(auto_pronounce_card=False):
            addon.on_reviewer_did_show_question(FakeCard())
        self.assertEqual(self.scheduled, [])

    def test_system_tts_is_skipped(self):
        """A system voice needs a user gesture, which a card appearing is not."""
        with self.configure(auto_pronounce_card=True, tts_provider="system"):
            addon.on_reviewer_did_show_question(FakeCard())
        self.assertEqual(self.scheduled, [])

    def test_empty_card_side_is_skipped(self):
        with self.configure(auto_pronounce_card=True):
            addon.on_reviewer_did_show_question(FakeCard(question="<br>"))
        self.assertEqual(self.scheduled, [])

    def test_overlong_side_is_skipped(self):
        with self.configure(auto_pronounce_card=True):
            addon.on_reviewer_did_show_question(FakeCard(question="a " * MAX_SPEECH_CHARS))
        self.assertEqual(self.scheduled, [])

    def test_answer_side_speaks_only_the_answer(self):
        with self.configure(auto_pronounce_card=True):
            with mock.patch.object(addon, "_synthesize_blocking") as synth:
                addon.on_reviewer_did_show_answer(FakeCard())
                self.scheduled[0]._op(None)
        synth.assert_called_once_with("the house")

    def test_a_broken_card_never_raises_into_the_reviewer(self):
        class ExplodingCard:
            def question(self):
                raise RuntimeError("render failed")

        with self.configure(auto_pronounce_card=True):
            with mock.patch.object(addon.logger, "exception") as logged:
                addon.on_reviewer_did_show_question(ExplodingCard())  # must not raise
        self.assertEqual(self.scheduled, [])
        logged.assert_called_once()


class SetOptionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.written = {}
        fake_mw = mock.MagicMock()
        fake_mw.addonManager.writeConfig.side_effect = (
            lambda _mod, conf: self.written.update(conf)
        )
        patcher = mock.patch.object(addon, "mw", fake_mw, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.raw = dict(DEFAULTS)
        cfg = mock.patch.object(addon, "_raw_config", return_value=self.raw)
        cfg.start()
        self.addCleanup(cfg.stop)

    def test_known_option_is_written(self):
        addon._set_option('{"key": "auto_pronounce_card", "value": false}')
        self.assertIs(self.written["auto_pronounce_card"], False)

    def test_unknown_key_is_refused(self):
        """The payload comes from the webview, so the key must be allowlisted."""
        with mock.patch.object(addon.logger, "warning") as warned:
            addon._set_option('{"key": "api_key", "value": "stolen"}')
        self.assertEqual(self.written, {})
        warned.assert_called_once()

    def test_non_toggle_config_key_is_refused(self):
        with mock.patch.object(addon.logger, "warning"):
            addon._set_option('{"key": "translation_provider", "value": true}')
        self.assertEqual(self.written, {})

    def test_malformed_payload_is_refused(self):
        for payload in ("{", "[]", '{"key": "auto_translate"}', "null"):
            with self.subTest(payload=payload):
                with mock.patch.object(addon.logger, "exception"):
                    addon._set_option(payload)
        self.assertEqual(self.written, {})

    def test_value_is_coerced_to_bool(self):
        addon._set_option('{"key": "show_examples", "value": 1}')
        self.assertIs(self.written["show_examples"], True)


if __name__ == "__main__":
    unittest.main()
