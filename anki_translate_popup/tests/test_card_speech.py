"""Card auto-pronounce: which text gets spoken, and which options gate it."""

from __future__ import annotations

import json
import unittest
from unittest import mock

import anki_translate_popup as addon
from anki_translate_popup.config import DEFAULTS, parse_config
from anki_translate_popup.translation.base import ConfigurationError
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


class FirstLineTest(unittest.TestCase):
    """A vocabulary card's first line is the headword; the rest is not."""

    # Taken from a real card: headword, then a literal "Example" label.
    QUESTION_DIVS = '<div>der Gesichtspunkt, -e</div><div class="ex">Example</div>'
    QUESTION_BRS = 'der Gesichtspunkt, -e<br><br><span class="ex">Example</span>'

    def test_label_after_the_headword_is_not_spoken(self):
        for rendered in (self.QUESTION_DIVS, self.QUESTION_BRS):
            with self.subTest(rendered=rendered):
                self.assertEqual(
                    addon.card_side_text(rendered, is_answer=False, first_line_only=True),
                    "der Gesichtspunkt, -e",
                )

    def test_full_scope_still_reads_everything(self):
        self.assertEqual(
            addon.card_side_text(self.QUESTION_DIVS, is_answer=False),
            "der Gesichtspunkt, -e Example",
        )

    def test_lines_are_split_on_block_boundaries(self):
        self.assertEqual(
            addon.card_side_lines(self.QUESTION_DIVS, is_answer=False),
            ["der Gesichtspunkt, -e", "Example"],
        )

    def test_inline_markup_does_not_split_a_line(self):
        rendered = "<div>der <b>Gesichtspunkt</b>, -e</div>"
        self.assertEqual(
            addon.card_side_lines(rendered, is_answer=False), ["der Gesichtspunkt, -e"]
        )

    def test_leading_blank_blocks_are_skipped(self):
        rendered = "<div><br></div><div>der Gesichtspunkt, -e</div><div>Example</div>"
        self.assertEqual(
            addon.card_side_text(rendered, is_answer=False, first_line_only=True),
            "der Gesichtspunkt, -e",
        )

    def test_single_line_card_is_unaffected(self):
        self.assertEqual(
            addon.card_side_text("Das Haus", is_answer=False, first_line_only=True),
            "Das Haus",
        )

    def test_empty_side_yields_nothing(self):
        self.assertEqual(
            addon.card_side_text("<div><br></div>", is_answer=False, first_line_only=True),
            "",
        )


class GermanAbbreviationTest(unittest.TestCase):
    """Speech engines read "Akk." as letters; expand it to the word."""

    def expand(self, text: str) -> str:
        return addon.expand_german_abbreviations(text)

    def test_the_four_cases(self):
        self.assertEqual(self.expand("Akk"), "Akkusativ")
        self.assertEqual(self.expand("Dat"), "Dativ")
        self.assertEqual(self.expand("Gen"), "Genitiv")
        self.assertEqual(self.expand("Nom"), "Nominativ")

    def test_trailing_full_stop_is_kept_as_a_pause(self):
        self.assertEqual(self.expand("warten auf + Akk."), "warten auf + Akkusativ.")

    def test_case_insensitive(self):
        self.assertEqual(self.expand("AKK"), "Akkusativ")
        self.assertEqual(self.expand("dat."), "Dativ.")

    def test_mid_sentence(self):
        self.assertEqual(
            self.expand("helfen + Dat., danken + Dat."),
            "helfen + Dativ., danken + Dativ.",
        )

    def test_longer_words_starting_with_an_abbreviation_are_untouched(self):
        """"Akku" is a battery, and "Genitiv" is already the full word."""
        for word in ("Akku", "Akkus", "Genitiv", "Datum", "Nomen", "Datei"):
            with self.subTest(word=word):
                self.assertEqual(self.expand(word), word)

    def test_already_expanded_text_is_stable(self):
        once = self.expand("Akk.")
        self.assertEqual(self.expand(once), once)

    def test_umlauts_survive(self):
        self.assertEqual(
            self.expand("gegenüber + Dat. für Grüße"), "gegenüber + Dativ. für Grüße"
        )

    def test_text_without_abbreviations_is_unchanged(self):
        self.assertEqual(self.expand("der Gesichtspunkt, -e"), "der Gesichtspunkt, -e")


class PrepareSpeechTextTest(unittest.TestCase):
    def config(self, **overrides):
        raw = dict(DEFAULTS)
        raw.update(overrides)
        from anki_translate_popup.config import parse_config

        return parse_config(raw)

    def test_expands_for_german_speech(self):
        self.assertEqual(
            addon.prepare_speech_text("mit + Dat.", self.config(speech_language="de-DE")),
            "mit + Dativ.",
        )

    def test_disabled_leaves_text_alone(self):
        self.assertEqual(
            addon.prepare_speech_text(
                "mit + Dat.", self.config(expand_abbreviations=False)
            ),
            "mit + Dat.",
        )

    def test_not_applied_to_other_languages(self):
        """"Gen" is an English word; expanding it there would be wrong."""
        self.assertEqual(
            addon.prepare_speech_text(
                "the gen on that", self.config(speech_language="en-US")
            ),
            "the gen on that",
        )

    def test_any_german_locale_counts(self):
        for locale in ("de", "de-DE", "de-AT", "de-CH"):
            with self.subTest(locale=locale):
                self.assertEqual(
                    addon.prepare_speech_text("+ Gen.", self.config(speech_language=locale)),
                    "+ Genitiv.",
                )


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
        with self.configure(auto_pronounce_card=True, auto_pronounce_answer=True):
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

    def test_answer_side_is_silent_by_default(self):
        """The answer is what the user is recalling; speaking it gives it away."""
        with self.configure(auto_pronounce_card=True):
            addon.on_reviewer_did_show_answer(FakeCard())
        self.assertEqual(self.scheduled, [])

    def test_answer_side_speaks_only_the_answer_when_enabled(self):
        with self.configure(auto_pronounce_card=True, auto_pronounce_answer=True):
            with mock.patch.object(addon, "_synthesize_blocking") as synth:
                addon.on_reviewer_did_show_answer(FakeCard())
                self.scheduled[0]._op(None)
        # "en", not the German speech_language: the answer is the target side.
        synth.assert_called_once_with("the house", "en")

    def test_question_speaks_only_its_first_line_by_default(self):
        card = FakeCard(question="<div>der Gesichtspunkt, -e</div><div>Example</div>")
        with self.configure(auto_pronounce_card=True):
            with mock.patch.object(addon, "_synthesize_blocking") as synth:
                addon.on_reviewer_did_show_question(card)
                self.scheduled[0]._op(None)
        synth.assert_called_once_with("der Gesichtspunkt, -e", "de-DE")

    def test_full_scope_speaks_the_whole_side(self):
        card = FakeCard(question="<div>der Gesichtspunkt, -e</div><div>Example</div>")
        with self.configure(auto_pronounce_card=True, card_speech_scope="full"):
            with mock.patch.object(addon, "_synthesize_blocking") as synth:
                addon.on_reviewer_did_show_question(card)
                self.scheduled[0]._op(None)
        synth.assert_called_once_with("der Gesichtspunkt, -e Example", "de-DE")

    def test_a_broken_card_never_raises_into_the_reviewer(self):
        class ExplodingCard:
            def question(self):
                raise RuntimeError("render failed")

        with self.configure(auto_pronounce_card=True):
            with mock.patch.object(addon.logger, "exception") as logged:
                addon.on_reviewer_did_show_question(ExplodingCard())  # must not raise
        self.assertEqual(self.scheduled, [])
        # At least once: more than one speech path may report the same bad card.
        logged.assert_called()


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


class SpeechLanguagePerSideTest(unittest.TestCase):
    """A deck has a language per side, not one language for both."""

    def config(self, **overrides):
        raw = dict(DEFAULTS)
        raw.update(overrides)
        return parse_config(raw)

    def test_auto_follows_the_translation_pair(self):
        config = self.config(source_language="de", target_language="en")
        self.assertEqual(config.speech_language_for(is_answer=False), "de-DE")
        self.assertEqual(config.speech_language_for(is_answer=True), "en")

    def test_auto_swaps_when_the_pair_swaps(self):
        config = self.config(source_language="en", target_language="de")
        self.assertEqual(config.speech_language_for(is_answer=False), "en")
        self.assertEqual(config.speech_language_for(is_answer=True), "de-DE")

    def test_region_is_kept_for_the_same_language(self):
        """A user who asked for de-AT wants de-AT, not the pair's bare 'de'."""
        config = self.config(speech_language="de-AT", source_language="de")
        self.assertEqual(config.speech_language_for(is_answer=False), "de-AT")

    def test_explicit_setting_wins_over_the_pair(self):
        config = self.config(front_speech_language="fr", back_speech_language="el")
        self.assertEqual(config.speech_language_for(is_answer=False), "fr")
        self.assertEqual(config.speech_language_for(is_answer=True), "el")

    def test_auto_source_falls_back_to_speech_language(self):
        """'auto' as a source names no language, so there is nothing to follow."""
        config = self.config(source_language="auto", speech_language="de-DE")
        self.assertEqual(config.speech_language_for(is_answer=False), "de-DE")

    def test_one_side_can_be_pinned_while_the_other_follows(self):
        config = self.config(back_speech_language="en-GB", target_language="en")
        self.assertEqual(config.speech_language_for(is_answer=False), "de-DE")
        self.assertEqual(config.speech_language_for(is_answer=True), "en-GB")

    def test_a_bad_code_is_rejected(self):
        with self.assertRaises(ConfigurationError) as ctx:
            self.config(front_speech_language="not a language")
        self.assertIn("front_speech_language", str(ctx.exception))

    def test_abbreviations_expand_only_for_the_german_side(self):
        """The English back must not have "gen" turned into "Genitiv"."""
        config = self.config()
        self.assertEqual(
            addon.prepare_speech_text("+ Gen.", config, "de-DE"), "+ Genitiv."
        )
        self.assertEqual(
            addon.prepare_speech_text("the gen on that", config, "en"),
            "the gen on that",
        )


class PushCardTextTest(unittest.TestCase):
    """What the pronounce shortcuts are given to say."""

    def setUp(self) -> None:
        self.mw = mock.MagicMock()
        for target, value in (("mw", self.mw), ("QueryOp", mock.MagicMock())):
            patcher = mock.patch.object(addon, target, value, create=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        addon._last_auto_spoken = None
        self.addCleanup(setattr, addon, "_last_auto_spoken", None)

    def configure(self, **overrides):
        raw = dict(DEFAULTS)
        raw.update(overrides)
        return mock.patch.object(addon, "_raw_config", return_value=raw)

    def pushed(self):
        """The payload from the last onCardText call, or None if there was none."""
        for call in reversed(self.mw.reviewer.web.eval.call_args_list):
            script = call.args[0]
            if "onCardText(" in script:
                body = script.split("onCardText(", 1)[1].rsplit(");", 1)[0]
                return json.loads(body)
        return None

    def test_question_side_sends_the_prompt_only(self):
        """The answer must not reach the page while it is still hidden."""
        with self.configure():
            addon.on_reviewer_did_show_question(FakeCard())
        self.assertEqual(
            self.pushed(),
            {
                "prompt": "Das Haus",
                "promptLang": "de-DE",
                "answer": "",
                "answerLang": "en",
            },
        )

    def test_answer_side_sends_both(self):
        with self.configure():
            addon.on_reviewer_did_show_answer(FakeCard())
        self.assertEqual(
            self.pushed(),
            {
                "prompt": "Das Haus",
                "promptLang": "de-DE",
                "answer": "the house",
                "answerLang": "en",
            },
        )

    def test_each_side_carries_its_own_language(self):
        """A German voice reading the English back was the bug this fixes."""
        with self.configure(source_language="de", target_language="en"):
            addon.on_reviewer_did_show_answer(FakeCard())
        pushed = self.pushed()
        self.assertEqual(pushed["promptLang"], "de-DE")
        self.assertEqual(pushed["answerLang"], "en")

    def test_a_pinned_side_overrides_the_pair(self):
        with self.configure(back_speech_language="fr"):
            addon.on_reviewer_did_show_answer(FakeCard())
        self.assertEqual(self.pushed()["answerLang"], "fr")

    def test_sent_even_when_auto_pronounce_is_off(self):
        """The shortcuts are most of the point when nothing speaks by itself."""
        with self.configure(auto_pronounce_card=False):
            addon.on_reviewer_did_show_question(FakeCard())
        self.assertEqual(self.pushed()["prompt"], "Das Haus")

    def test_sent_for_a_system_voice(self):
        """A keypress is the user gesture that auto-pronounce never has."""
        with self.configure(tts_provider="system"):
            addon.on_reviewer_did_show_answer(FakeCard())
        self.assertEqual(self.pushed()["answer"], "the house")

    def test_disabling_both_shortcuts_skips_the_render(self):
        with self.configure(pronounce_prompt_shortcut="", pronounce_answer_shortcut=""):
            addon.on_reviewer_did_show_answer(FakeCard())
        self.assertIsNone(self.pushed())

    def test_scope_full_sends_every_line(self):
        card = FakeCard(question="<div>Das Haus</div><div>ist groß</div>")
        with self.configure(card_speech_scope="full"):
            addon.on_reviewer_did_show_question(card)
        self.assertEqual(self.pushed()["prompt"], "Das Haus ist groß")

    def test_no_reviewer_webview_is_survivable(self):
        self.mw.reviewer = None
        with self.configure():
            addon.on_reviewer_did_show_question(FakeCard())  # must not raise


class ResendCardTextTest(unittest.TestCase):
    """The page can lose the pushed text; asking again must work.

    A sync, the editor and the More menu can all rebuild the reviewer page
    between one card side and the next, which drops what Python pushed.
    """

    def setUp(self) -> None:
        self.mw = mock.MagicMock()
        patcher = mock.patch.object(addon, "mw", self.mw, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.mw.reviewer.card = FakeCard()

    def configure(self, **overrides):
        raw = dict(DEFAULTS)
        raw.update(overrides)
        return mock.patch.object(addon, "_raw_config", return_value=raw)

    def pushed(self):
        for call in reversed(self.mw.reviewer.web.eval.call_args_list):
            script = call.args[0]
            if "onCardText(" in script:
                return json.loads(script.split("onCardText(", 1)[1].rsplit(");", 1)[0])
        return None

    def test_prompt_is_resent_and_marked_to_speak(self):
        self.mw.reviewer.state = "question"
        with self.configure():
            addon._resend_card_text("prompt")
        payload = self.pushed()
        self.assertEqual(payload["prompt"], "Das Haus")
        self.assertEqual(payload["speak"], "prompt")

    def test_the_answer_is_withheld_while_the_question_is_showing(self):
        """Asking must not become a way to hear the answer early."""
        self.mw.reviewer.state = "question"
        with self.configure():
            addon._resend_card_text("answer")
        self.assertEqual(self.pushed()["answer"], "")

    def test_the_answer_is_sent_once_it_is_showing(self):
        self.mw.reviewer.state = "answer"
        with self.configure():
            addon._resend_card_text("answer")
        payload = self.pushed()
        self.assertEqual(payload["answer"], "the house")
        self.assertEqual(payload["speak"], "answer")

    def test_an_unknown_side_is_refused(self):
        with mock.patch.object(addon.logger, "warning") as warned:
            addon._resend_card_text("everything")
        self.assertIsNone(self.pushed())
        warned.assert_called_once()

    def test_no_card_is_survivable(self):
        self.mw.reviewer.card = None
        with self.configure():
            addon._resend_card_text("prompt")  # between cards; must not raise
        self.assertIsNone(self.pushed())

    def test_the_bridge_command_routes_here(self):
        self.mw.reviewer.state = "question"
        with self.configure():
            with mock.patch.object(addon, "_webview_for", return_value="WEB"):
                handled = addon.on_js_message(
                    (False, None), addon.BRIDGE_PREFIX + "card_text:prompt", None
                )
        self.assertEqual(handled, (True, None))
        self.assertEqual(self.pushed()["speak"], "prompt")


class DeckLanguagePersistenceTest(unittest.TestCase):
    def test_header_change_is_saved_for_the_current_deck(self):
        mw = mock.MagicMock()
        mw.reviewer.card = FakeCard()
        mw.reviewer.card.did = 42
        mw.reviewer.card.odid = 0
        with mock.patch.object(addon, "mw", mw, create=True):
            with mock.patch.object(addon, "_raw_config", return_value=dict(DEFAULTS)):
                addon._set_languages('{"source": "es", "target": "en"}')

        written = mw.addonManager.writeConfig.call_args.args[1]
        self.assertEqual(written["deck_language_pairs"], {"42": ["es", "en"]})
        self.assertEqual(written["source_language"], "de")


class QtSpeechShortcutFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.mw = mock.MagicMock()
        self.mw.reviewer.card = FakeCard()
        self.mw.reviewer.state = "question"
        self.mw.reviewer.web.hasFocus.return_value = False
        patcher = mock.patch.object(addon, "mw", self.mw, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        raw = mock.patch.object(addon, "_raw_config", return_value=dict(DEFAULTS))
        raw.start()
        self.addCleanup(raw.stop)
        addon._qt_speech_shortcuts = []
        addon._qt_speech_shortcut_keys = []
        self.addCleanup(setattr, addon, "_qt_speech_shortcuts", [])
        self.addCleanup(setattr, addon, "_qt_speech_shortcut_keys", [])

    def test_fallback_shortcuts_are_added_only_to_review(self):
        shortcuts = []
        addon.on_state_shortcuts_will_change("review", shortcuts)
        self.assertEqual([key for key, _callback in shortcuts], ["x", "c", "z"])

        elsewhere = []
        addon.on_state_shortcuts_will_change("deckBrowser", elsewhere)
        self.assertEqual(elsewhere, [])

    def test_qt_fallback_is_disabled_while_the_webview_has_focus(self):
        shortcuts = [mock.MagicMock() for _ in range(3)]
        for shortcut, key in zip(shortcuts, ("X", "C", "Z")):
            shortcut.key.return_value.toString.return_value = key
        self.mw.stateShortcuts = shortcuts
        self.mw.reviewer.web.hasFocus.return_value = True
        addon._qt_speech_shortcut_keys = ["x", "c", "z"]
        addon._capture_qt_speech_shortcuts()
        for shortcut in shortcuts:
            shortcut.setEnabled.assert_called_with(False)

        self.mw.reviewer.web.hasFocus.return_value = False
        addon._sync_qt_speech_shortcuts()
        for shortcut in shortcuts:
            shortcut.setEnabled.assert_called_with(True)

    def test_off_focus_prompt_uses_the_online_python_path(self):
        with mock.patch.object(addon, "_qt_stop_speech") as stop:
            with mock.patch.object(addon, "_start_speech") as start:
                addon._qt_pronounce_card_side(is_answer=False)
        stop.assert_called_once_with()
        start.assert_called_once_with(
            self.mw.reviewer.web, 0, "Das Haus", "de-DE"
        )

    def test_hidden_answer_and_system_only_mode_stay_silent(self):
        with mock.patch.object(addon, "_start_speech") as start:
            addon._qt_pronounce_card_side(is_answer=True)
            with mock.patch.object(
                addon, "_raw_config", return_value=dict(DEFAULTS, tts_provider="system")
            ):
                addon._qt_pronounce_card_side(is_answer=False)
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
