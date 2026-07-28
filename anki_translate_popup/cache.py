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
from typing import Callable, Iterator, Optional

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


class TranslationCache:
    """Persistent cache with a time-to-live.

    A ``lifetime_seconds`` of ``0`` means entries never expire.
    """

    def __init__(
        self,
        path: Path,
        lifetime_seconds: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._path = Path(path)
        self._lifetime = max(0, int(lifetime_seconds))
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
        except sqlite3.Error:
            logger.exception("Cache write failed for provider %s", provider)

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
