"""Which Anki screens the popup attaches to.

`_webview_for` decides both whether to inject assets and whether to accept a
bridge message, so a mistake here either breaks the reviewer or leaks the popup
into a screen it should stay out of.
"""

from __future__ import annotations

import unittest
from unittest import mock

import anki_translate_popup as addon
from anki_translate_popup.config import DEFAULTS, parse_config


class FakeReviewer:
    def __init__(self) -> None:
        self.web = "REVIEWER_WEB"


class FakePreviewer:
    def __init__(self) -> None:
        self._web = "PREVIEWER_WEB"
        self._card = mock.Mock(did=77, odid=0)

    def card(self):
        return self._card


class FakeBottomBar:
    def __init__(self) -> None:
        self.web = "BOTTOM_BAR_WEB"


class WebviewForTest(unittest.TestCase):
    def setUp(self) -> None:
        # Swap in stand-ins: the real classes cannot be constructed without a
        # running Anki, but the branching under test is pure isinstance logic.
        reviewer = mock.patch.object(addon.aqt.reviewer, "Reviewer", FakeReviewer)
        previewer = mock.patch.object(
            addon.aqt.browser.previewer, "Previewer", FakePreviewer
        )
        reviewer.start()
        previewer.start()
        self.addCleanup(reviewer.stop)
        self.addCleanup(previewer.stop)

    def configure(self, **overrides):
        raw = dict(DEFAULTS)
        raw.update(overrides)
        return mock.patch.object(addon, "_raw_config", return_value=raw)

    def test_reviewer_is_supported(self):
        with self.configure():
            self.assertEqual(addon._webview_for(FakeReviewer()), "REVIEWER_WEB")

    def test_previewer_is_supported_when_enabled(self):
        with self.configure(enable_in_previewer=True):
            self.assertEqual(addon._webview_for(FakePreviewer()), "PREVIEWER_WEB")

    def test_previewer_can_be_switched_off(self):
        with self.configure(enable_in_previewer=False):
            self.assertIsNone(addon._webview_for(FakePreviewer()))

    def test_disabling_the_previewer_leaves_the_reviewer_alone(self):
        with self.configure(enable_in_previewer=False):
            self.assertEqual(addon._webview_for(FakeReviewer()), "REVIEWER_WEB")

    def test_answer_button_bar_is_not_supported(self):
        """It holds no card text, so a popup there would be meaningless."""
        with self.configure():
            self.assertIsNone(addon._webview_for(FakeBottomBar()))

    def test_unrelated_contexts_are_ignored(self):
        with self.configure():
            for context in (None, object(), "deck browser", 42):
                with self.subTest(context=context):
                    self.assertIsNone(addon._webview_for(context))

    def test_is_reviewer_tracks_webview_for(self):
        with self.configure(enable_in_previewer=True):
            self.assertTrue(addon._is_reviewer(FakeReviewer()))
            self.assertTrue(addon._is_reviewer(FakePreviewer()))
            self.assertFalse(addon._is_reviewer(FakeBottomBar()))

    def test_previewer_uses_the_previewed_cards_deck(self):
        with self.configure():
            self.assertEqual(addon._context_deck_id(FakePreviewer()), 77)

    def test_previewer_without_a_webview_is_ignored(self):
        """A previewer mid-teardown sets _web to None; never return that."""

        class ClosingPreviewer:
            _web = None

        with mock.patch.object(
            addon.aqt.browser.previewer, "Previewer", ClosingPreviewer
        ):
            with self.configure(enable_in_previewer=True):
                self.assertIsNone(addon._webview_for(ClosingPreviewer()))


class LanguageSupportProbeTest(unittest.TestCase):
    def setUp(self) -> None:
        addon._language_support_key = None
        addon._language_support = None
        addon._language_support_webviews = []
        self.addCleanup(setattr, addon, "_language_support_key", None)
        self.addCleanup(setattr, addon, "_language_support", None)
        self.addCleanup(setattr, addon, "_language_support_webviews", [])

    def test_reviewer_broadcast_resolves_the_card_that_is_current_now(self):
        web = mock.MagicMock()
        mw = mock.MagicMock()
        mw.reviewer.web = web
        mw.reviewer.card = mock.Mock(did=2, odid=0)
        addon._language_support_webviews = [(web, 1)]
        raw = dict(
            DEFAULTS,
            deck_language_pairs={"1": ["es", "en"], "2": ["fr", "en"]},
        )
        with mock.patch.object(addon, "mw", mw, create=True):
            with mock.patch.object(addon, "_raw_config", return_value=raw):
                addon._broadcast_webview_configs()
        self.assertIn('"sourceLanguage": "fr"', web.eval.call_args.args[0])

    def test_provider_probe_runs_in_queryop_not_the_ui_thread(self):
        jobs = []

        class FakeQueryOp:
            def __init__(inner, *, parent, op, success):
                inner.op = op
                inner.success = success
                jobs.append(inner)

            def without_collection(inner):
                return inner

            def failure(inner, callback):
                inner.failure_callback = callback
                return inner

            def run_in_background(inner):
                pass

        translator = mock.MagicMock()
        support = (frozenset({"de"}), frozenset({"en"}))
        translator.supported_languages.return_value = support
        config = parse_config(
            dict(DEFAULTS, translation_provider="deepl", api_key="key:fx")
        )
        reviewer_web = mock.MagicMock()
        previewer_web = mock.MagicMock()

        with mock.patch.object(addon, "QueryOp", FakeQueryOp, create=True):
            with mock.patch.object(addon, "build_translator", return_value=translator):
                with mock.patch.object(addon, "mw", mock.MagicMock(), create=True):
                    addon._start_language_support_probe(config, reviewer_web, 1)
                    addon._start_language_support_probe(config, previewer_web, 2)

        self.assertEqual(len(jobs), 1)
        translator.supported_languages.assert_not_called()
        jobs[0].success(jobs[0].op(None))
        translator.supported_languages.assert_called_once_with()
        self.assertEqual(addon._language_support, support)
        for web in (reviewer_web, previewer_web):
            self.assertIn("onConfigChanged", web.eval.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
