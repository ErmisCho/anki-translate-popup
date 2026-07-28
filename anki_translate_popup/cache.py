"""SQLite-backed translation cache.

Uses one short-lived connection per operation. The cache is touched from
Anki's background worker threads, and SQLite connections cannot be shared
across threads; per-call connections sidestep that without a lock, at a cost
that is irrelevant for a user-triggered action.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from stat import S_ISREG
from typing import Callable, Iterator, List, Optional, Tuple

from .translation.base import TranslationResult

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS translations (
    key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    translated TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_translations_created_at
    ON translations (created_at);
"""


def make_key(provider: str, source_lang: str, target_lang: str, text: str) -> str:
    """Stable cache key.

    NUL separators cannot occur in the parts, so distinct inputs can never
    collide by concatenation. Hashing keeps the key short and keeps arbitrary
    user text out of the index.
    """
    raw = "\x00".join((provider, source_lang, target_lang, text))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def prune_audio_cache(directory: Path, max_bytes: int) -> int:
    """Delete the oldest files until the directory fits in max_bytes.

    Returns the number of files deleted.
    """
    directory = Path(directory)
    # A cache folder that was never created is not an error, just nothing to do.
    if max_bytes <= 0 or not directory.is_dir():
        return 0

    try:
        entries = list(directory.iterdir())
    except OSError:
        logger.exception("Audio cache listing failed for %s", directory)
        return 0

    files: List[Tuple[float, int, Path]] = []
    total = 0
    for entry in entries:
        # Only finished downloads: .part files belong to a fetch in flight.
        if entry.suffix.lower() != ".mp3":
            continue
        try:
            info = entry.stat()
        except OSError:
            logger.exception("Audio cache stat failed for %s", entry)
            continue
        if not S_ISREG(info.st_mode):
            continue
        files.append((info.st_mtime, info.st_size, entry))
        total += info.st_size

    deleted = 0
    for _mtime, size, entry in sorted(files, key=lambda item: item[0]):
        if total <= max_bytes:
            break
        try:
            entry.unlink()
        except OSError:
            # Another process may still hold the file open; leave it and
            # reclaim it on the next prune.
            logger.exception("Audio cache delete failed for %s", entry)
            continue
        total -= size
        deleted += 1
    return deleted


class TranslationCache:
    """Persistent cache with a time-to-live and a row-count limit.

    A ``lifetime_seconds`` of ``0`` means entries never expire; a
    ``max_entries`` of ``0`` means the number of rows is unlimited.
    """

    def __init__(
        self,
        path: Path,
        lifetime_seconds: int,
        clock: Callable[[], float] = time.time,
        *,
        max_entries: int = 0,
    ) -> None:
        self._path = Path(path)
        self._lifetime = max(0, int(lifetime_seconds))
        self._max_entries = max(0, int(max_entries))
        self._clock = clock
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Open a connection, commit or roll back, then always close it.

        ``sqlite3.Connection`` used directly as a context manager only manages
        the transaction - it leaves the connection (and the file handle) open.
        """
        conn = sqlite3.connect(str(self._path), timeout=5.0)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            with conn:
                yield conn
        finally:
            conn.close()

    def _is_expired(self, created_at: float) -> bool:
        if self._lifetime == 0:
            return False
        return (self._clock() - created_at) > self._lifetime

    def get(
        self, provider: str, source_lang: str, target_lang: str, text: str
    ) -> Optional[TranslationResult]:
        """Return a cached result, or ``None`` on a miss or an expired entry."""
        key = make_key(provider, source_lang, target_lang, text)
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT source_lang, target_lang, translated, created_at "
                    "FROM translations WHERE key = ?",
                    (key,),
                ).fetchone()
        except sqlite3.Error:
            # A broken cache must never break translation; surface it in the log.
            logger.exception("Cache lookup failed for provider %s", provider)
            return None

        if row is None:
            return None

        stored_source, stored_target, translated, created_at = row
        if self._is_expired(created_at):
            self.delete(key)
            return None

        return TranslationResult(
            text=translated,
            source_lang=stored_source,
            target_lang=stored_target,
            provider=provider,
        )

    def set(
        self, provider: str, source_lang: str, target_lang: str, text: str,
        result: TranslationResult,
    ) -> None:
        """Store ``result``. Keyed by the *requested* languages, not the detected ones."""
        key = make_key(provider, source_lang, target_lang, text)
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO translations "
                    "(key, provider, source_lang, target_lang, translated, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        key,
                        provider,
                        result.source_lang,
                        result.target_lang,
                        result.text,
                        self._clock(),
                    ),
                )
                self._evict(conn)
        except sqlite3.Error:
            logger.exception("Cache write failed for provider %s", provider)

    def _evict(self, conn: sqlite3.Connection) -> int:
        """Delete everything but the newest ``max_entries`` rows. Returns the count.

        One indexed DELETE rather than a COUNT followed by a conditional
        DELETE: it is a single statement on the same connection and the
        ``created_at`` index covers the ordering, so running it on every write
        is cheaper than the extra round trip a check would add - and the cache
        sits exactly at the limit instead of sawtoothing above it.
        """
        if self._max_entries == 0:
            return 0
        cursor = conn.execute(
            "DELETE FROM translations WHERE key NOT IN ("
            "SELECT key FROM translations ORDER BY created_at DESC LIMIT ?)",
            (self._max_entries,),
        )
        return cursor.rowcount or 0

    def delete(self, key: str) -> None:
        try:
            with self._connect() as conn:
                conn.execute("DELETE FROM translations WHERE key = ?", (key,))
        except sqlite3.Error:
            logger.exception("Cache delete failed")

    def purge_expired(self) -> int:
        """Drop every expired row. Returns the number deleted."""
        if self._lifetime == 0:
            return 0
        cutoff = self._clock() - self._lifetime
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM translations WHERE created_at < ?", (cutoff,)
                )
                return cursor.rowcount or 0
        except sqlite3.Error:
            logger.exception("Cache purge failed")
            return 0

    def enforce_limit(self) -> int:
        """Evict the least-recently-created rows beyond the configured maximum."""
        if self._max_entries == 0:
            return 0
        try:
            with self._connect() as conn:
                return self._evict(conn)
        except sqlite3.Error:
            logger.exception("Cache limit enforcement failed")
            return 0

    def clear(self) -> int:
        try:
            with self._connect() as conn:
                cursor = conn.execute("DELETE FROM translations")
                return cursor.rowcount or 0
        except sqlite3.Error:
            logger.exception("Cache clear failed")
            return 0

    def count(self) -> int:
        try:
            with self._connect() as conn:
                return int(
                    conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
                )
        except sqlite3.Error:
            logger.exception("Cache count failed")
            return 0
