"""Cache read/write/expiry/size-limit tests."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from anki_translate_popup.cache import TranslationCache, make_key, prune_audio_cache
from anki_translate_popup.translation.base import TranslationResult


class FakeClock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def result(text: str = "the house", source: str = "de", target: str = "en") -> TranslationResult:
    return TranslationResult(text=text, source_lang=source, target_lang=target, provider="deepl")


class CacheTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "nested" / "cache.sqlite"
        self.clock = FakeClock()

    def make_cache(
        self, lifetime_seconds: int = 3600, max_entries: int = 0
    ) -> TranslationCache:
        return TranslationCache(
            self.path, lifetime_seconds, clock=self.clock, max_entries=max_entries
        )


class KeyTest(unittest.TestCase):
    def test_key_is_stable(self):
        self.assertEqual(
            make_key("deepl", "de", "en", "das Haus"),
            make_key("deepl", "de", "en", "das Haus"),
        )

    def test_key_varies_with_every_component(self):
        base = make_key("deepl", "de", "en", "das Haus")
        self.assertNotEqual(base, make_key("libretranslate", "de", "en", "das Haus"))
        self.assertNotEqual(base, make_key("deepl", "auto", "en", "das Haus"))
        self.assertNotEqual(base, make_key("deepl", "de", "fr", "das Haus"))
        self.assertNotEqual(base, make_key("deepl", "de", "en", "das Auto"))

    def test_concatenation_cannot_collide(self):
        # "de" + "en" vs "deen" + "" must not produce the same key.
        self.assertNotEqual(
            make_key("deepl", "de", "en", "x"),
            make_key("deepl", "deen", "", "x"),
        )


class ReadWriteTest(CacheTestBase):
    def test_miss_returns_none(self):
        cache = self.make_cache()
        self.assertIsNone(cache.get("deepl", "de", "en", "das Haus"))

    def test_roundtrip(self):
        cache = self.make_cache()
        cache.set("deepl", "de", "en", "das Haus", result())
        hit = cache.get("deepl", "de", "en", "das Haus")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.text, "the house")
        self.assertEqual(hit.source_lang, "de")
        self.assertEqual(hit.target_lang, "en")
        self.assertEqual(hit.provider, "deepl")

    def test_creates_missing_parent_directories(self):
        self.make_cache()
        self.assertTrue(self.path.exists())

    def test_survives_reopen(self):
        self.make_cache().set("deepl", "de", "en", "das Haus", result())
        reopened = self.make_cache()
        self.assertEqual(reopened.get("deepl", "de", "en", "das Haus").text, "the house")

    def test_overwrite_replaces_entry(self):
        cache = self.make_cache()
        cache.set("deepl", "de", "en", "das Haus", result("the house"))
        cache.set("deepl", "de", "en", "das Haus", result("the building"))
        self.assertEqual(cache.get("deepl", "de", "en", "das Haus").text, "the building")
        self.assertEqual(cache.count(), 1)

    def test_provider_scoped(self):
        cache = self.make_cache()
        cache.set("deepl", "de", "en", "das Haus", result())
        self.assertIsNone(cache.get("libretranslate", "de", "en", "das Haus"))

    def test_detected_language_is_stored_not_the_requested_one(self):
        cache = self.make_cache()
        cache.set("deepl", "auto", "en", "das Haus", result(source="de"))
        hit = cache.get("deepl", "auto", "en", "das Haus")
        self.assertEqual(hit.source_lang, "de")


class UnicodeTest(CacheTestBase):
    def test_german_characters_roundtrip(self):
        cache = self.make_cache()
        text = "Grüße über die Straße, Fußgängerübergang – schön!"
        translated = "Greetings across the street, pedestrian crossing – lovely!"
        cache.set("deepl", "de", "en", text, result(translated))
        self.assertEqual(cache.get("deepl", "de", "en", text).text, translated)

    def test_umlaut_variants_are_distinct_keys(self):
        cache = self.make_cache()
        cache.set("deepl", "de", "en", "schon", result("already"))
        cache.set("deepl", "de", "en", "schön", result("beautiful"))
        self.assertEqual(cache.get("deepl", "de", "en", "schon").text, "already")
        self.assertEqual(cache.get("deepl", "de", "en", "schön").text, "beautiful")

    def test_emoji_and_cjk(self):
        cache = self.make_cache()
        cache.set("deepl", "de", "en", "Hund 🐕 犬", result("dog"))
        self.assertEqual(cache.get("deepl", "de", "en", "Hund 🐕 犬").text, "dog")


class ExpiryTest(CacheTestBase):
    def test_entry_within_lifetime_is_returned(self):
        cache = self.make_cache(lifetime_seconds=3600)
        cache.set("deepl", "de", "en", "das Haus", result())
        self.clock.advance(3599)
        self.assertIsNotNone(cache.get("deepl", "de", "en", "das Haus"))

    def test_entry_past_lifetime_is_dropped(self):
        cache = self.make_cache(lifetime_seconds=3600)
        cache.set("deepl", "de", "en", "das Haus", result())
        self.clock.advance(3601)
        self.assertIsNone(cache.get("deepl", "de", "en", "das Haus"))
        # The expired row is removed on read, not merely hidden.
        self.assertEqual(cache.count(), 0)

    def test_zero_lifetime_never_expires(self):
        cache = self.make_cache(lifetime_seconds=0)
        cache.set("deepl", "de", "en", "das Haus", result())
        self.clock.advance(10 * 365 * 86400)
        self.assertIsNotNone(cache.get("deepl", "de", "en", "das Haus"))

    def test_purge_expired_only_removes_stale_rows(self):
        cache = self.make_cache(lifetime_seconds=100)
        cache.set("deepl", "de", "en", "alt", result("old"))
        self.clock.advance(200)
        cache.set("deepl", "de", "en", "neu", result("new"))
        self.assertEqual(cache.purge_expired(), 1)
        self.assertIsNone(cache.get("deepl", "de", "en", "alt"))
        self.assertIsNotNone(cache.get("deepl", "de", "en", "neu"))

    def test_purge_is_a_noop_when_lifetime_is_zero(self):
        cache = self.make_cache(lifetime_seconds=0)
        cache.set("deepl", "de", "en", "das Haus", result())
        self.assertEqual(cache.purge_expired(), 0)
        self.assertEqual(cache.count(), 1)

    def test_clear_removes_everything(self):
        cache = self.make_cache()
        cache.set("deepl", "de", "en", "eins", result())
        cache.set("deepl", "de", "en", "zwei", result())
        self.assertEqual(cache.clear(), 2)
        self.assertEqual(cache.count(), 0)


class LimitTest(CacheTestBase):
    def fill(self, cache: TranslationCache, count: int) -> None:
        # One tick between writes: created_at decides eviction order.
        for index in range(count):
            self.clock.advance(1)
            cache.set("deepl", "de", "en", f"wort{index}", result(f"word{index}"))

    def test_below_the_limit_nothing_is_evicted(self):
        cache = self.make_cache(lifetime_seconds=0, max_entries=5)
        self.fill(cache, 3)
        self.assertEqual(cache.enforce_limit(), 0)
        self.assertEqual(cache.count(), 3)

    def test_at_the_limit_nothing_is_evicted(self):
        cache = self.make_cache(lifetime_seconds=0, max_entries=3)
        self.fill(cache, 3)
        self.assertEqual(cache.enforce_limit(), 0)
        self.assertEqual(cache.count(), 3)

    def test_enforce_limit_drops_the_oldest_rows(self):
        # Fill without a limit, then reopen with one - as if the setting changed.
        self.fill(self.make_cache(lifetime_seconds=0), 5)
        cache = self.make_cache(lifetime_seconds=0, max_entries=2)
        self.assertEqual(cache.enforce_limit(), 3)
        self.assertEqual(cache.count(), 2)
        self.assertIsNone(cache.get("deepl", "de", "en", "wort0"))
        self.assertIsNone(cache.get("deepl", "de", "en", "wort2"))
        self.assertIsNotNone(cache.get("deepl", "de", "en", "wort3"))
        self.assertIsNotNone(cache.get("deepl", "de", "en", "wort4"))

    def test_zero_max_entries_is_unlimited(self):
        cache = self.make_cache(lifetime_seconds=0, max_entries=0)
        self.fill(cache, 10)
        self.assertEqual(cache.enforce_limit(), 0)
        self.assertEqual(cache.count(), 10)

    def test_set_keeps_the_cache_within_the_limit(self):
        cache = self.make_cache(lifetime_seconds=0, max_entries=3)
        self.fill(cache, 6)
        # Eviction happens through plain writes, without an explicit call.
        self.assertEqual(cache.count(), 3)
        self.assertIsNone(cache.get("deepl", "de", "en", "wort0"))
        self.assertIsNone(cache.get("deepl", "de", "en", "wort2"))
        self.assertIsNotNone(cache.get("deepl", "de", "en", "wort5"))

    def test_overwrite_does_not_count_twice(self):
        cache = self.make_cache(lifetime_seconds=0, max_entries=2)
        for _ in range(4):
            self.clock.advance(1)
            cache.set("deepl", "de", "en", "das Haus", result())
        self.assertEqual(cache.count(), 1)


class ResilienceTest(CacheTestBase):
    def test_corrupt_database_does_not_raise(self):
        cache = self.make_cache()
        cache.set("deepl", "de", "en", "das Haus", result())
        # WAL keeps recent writes in sidecar files; clear them too so the
        # database really is unreadable.
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.path) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        self.path.write_bytes(b"this is definitely not a sqlite database")

        # A broken cache degrades to a miss rather than breaking translation -
        # but the failure is logged, never silently swallowed.
        with self.assertLogs("anki_translate_popup.cache", level="ERROR") as logs:
            self.assertIsNone(cache.get("deepl", "de", "en", "das Haus"))
            cache.set("deepl", "de", "en", "das Haus", result())  # must not raise
            self.assertEqual(cache.count(), 0)
        self.assertTrue(any("not a database" in message for message in logs.output))

    def test_schema_is_idempotent(self):
        self.make_cache()
        self.make_cache()
        conn = sqlite3.connect(str(self.path))
        try:
            names = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        self.assertIn("translations", names)

    def test_connections_are_closed(self):
        """Regression: leaked handles blocked file deletion on Windows."""
        cache = self.make_cache()
        cache.set("deepl", "de", "en", "das Haus", result())
        cache.get("deepl", "de", "en", "das Haus")
        cache.purge_expired()
        cache.enforce_limit()
        # Windows refuses to unlink a file that still has an open handle.
        self.path.unlink()
        self.assertFalse(self.path.exists())

    def test_enforce_limit_survives_a_corrupt_database(self):
        cache = self.make_cache(lifetime_seconds=0, max_entries=1)
        cache.set("deepl", "de", "en", "das Haus", result())
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.path) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        self.path.write_bytes(b"this is definitely not a sqlite database")

        with self.assertLogs("anki_translate_popup.cache", level="ERROR"):
            self.assertEqual(cache.enforce_limit(), 0)


class AudioPruneTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.directory = Path(self._tmp.name)

    def write(self, name: str, size: int, mtime: float) -> Path:
        path = self.directory / name
        path.write_bytes(b"x" * size)
        os.utime(path, (mtime, mtime))
        return path

    def test_under_the_limit_nothing_is_deleted(self):
        kept = self.write("a.mp3", 100, 1)
        self.assertEqual(prune_audio_cache(self.directory, 1000), 0)
        self.assertTrue(kept.exists())

    def test_oldest_files_go_first(self):
        old = self.write("old.mp3", 100, 1)
        middle = self.write("middle.mp3", 100, 2)
        new = self.write("new.mp3", 100, 3)
        self.assertEqual(prune_audio_cache(self.directory, 250), 1)
        self.assertFalse(old.exists())
        self.assertTrue(middle.exists())
        self.assertTrue(new.exists())

    def test_deletes_until_it_fits(self):
        paths = [self.write(f"{index}.mp3", 100, index) for index in range(5)]
        self.assertEqual(prune_audio_cache(self.directory, 250), 3)
        self.assertEqual([path.exists() for path in paths], [False, False, False, True, True])

    def test_zero_max_bytes_is_unlimited(self):
        kept = self.write("a.mp3", 1000, 1)
        self.assertEqual(prune_audio_cache(self.directory, 0), 0)
        self.assertTrue(kept.exists())

    def test_missing_directory_is_not_an_error(self):
        self.assertEqual(prune_audio_cache(self.directory / "nope", 10), 0)

    def test_non_mp3_files_are_left_alone(self):
        pending = self.write("pending.part", 5000, 1)
        kept = self.write("a.mp3", 100, 2)
        self.assertEqual(prune_audio_cache(self.directory, 100), 0)
        self.assertTrue(pending.exists())
        self.assertTrue(kept.exists())

    def test_directories_are_ignored(self):
        (self.directory / "nested.mp3").mkdir()
        self.assertEqual(prune_audio_cache(self.directory, 1), 0)

    def test_unstattable_file_is_skipped(self):
        kept = self.write("a.mp3", 1000, 1)
        real_stat = Path.stat

        def fail_on_mp3(self: Path, *args, **kwargs):
            if self.suffix == ".mp3":
                raise OSError("vanished mid-prune")
            return real_stat(self, *args, **kwargs)

        with mock.patch.object(Path, "stat", fail_on_mp3):
            with self.assertLogs("anki_translate_popup.cache", level="ERROR"):
                self.assertEqual(prune_audio_cache(self.directory, 10), 0)
        self.assertTrue(kept.exists())

    def test_locked_file_is_skipped_not_raised(self):
        locked = self.write("a.mp3", 1000, 1)
        with mock.patch.object(Path, "unlink", side_effect=OSError("locked")):
            with self.assertLogs("anki_translate_popup.cache", level="ERROR"):
                self.assertEqual(prune_audio_cache(self.directory, 10), 0)
        self.assertTrue(locked.exists())


if __name__ == "__main__":
    unittest.main()
