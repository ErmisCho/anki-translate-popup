"""Which Anki screens the popup attaches to.

`_webview_for` decides both whether to inject assets and whether to accept a
bridge message, so a mistake here either breaks the reviewer or leaks the popup
into a screen it should stay out of.
"""

from __future__ import annotations

import unittest
from unittest import mock

import anki_translate_popup as addon
from anki_translate_popup.config import DEFAULTS


class FakeReviewer:
    def __init__(self) -> None:
        self.web = "REVIEWER_WEB"


class FakePreviewer:
    def __init__(self) -> None:
        self._web = "PREVIEWER_WEB"


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

    def test_previewer_without_a_webview_is_ignored(self):
        """A previewer mid-teardown sets _web to None; never return that."""

        class ClosingPreviewer:
            _web = None

        with mock.patch.object(
            addon.aqt.browser.previewer, "Previewer", ClosingPreviewer
        ):
            with self.configure(enable_in_previewer=True):
                self.assertIsNone(addon._webview_for(ClosingPreviewer()))


if __name__ == "__main__":
    unittest.main()
