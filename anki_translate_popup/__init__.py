"""Translate & Pronounce Popup - Anki add-on entry point.

Verified against Anki 25.09.4 (Qt 6.8 / PyQt6, Python 3.13). Everything here
uses documented add-on APIs:

* ``gui_hooks.webview_will_set_content``   - inject CSS/JS into the reviewer
* ``gui_hooks.webview_did_receive_js_message`` - receive ``pycmd()`` calls
* ``AddonManager.setWebExports``           - serve ``web/`` over ``/_addons``
* ``AddonManager.getConfig`` / ``setConfigUpdatedAction`` - configuration
* ``aqt.operations.QueryOp``               - run network calls off the UI thread

Importing this module outside Anki (as the test suite does) is safe: the Anki
wiring is skipped when ``aqt`` is unavailable.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .cache import TranslationCache
from .config import DEFAULTS, AddonConfig, parse_config
from .translation import TranslationError, TranslationRequest, build_translator
from .translation.base import ConfigurationError, ProviderError
from .tts import MAX_SPEECH_CHARS, GoogleTextToSpeech, SpeechError

ADDON_NAME = "Translate & Pronounce Popup"
BRIDGE_PREFIX = "anki_translate_popup:"
#: Guard against a runaway selection being posted to a paid API.
MAX_TEXT_LENGTH = 5000

_ADDON_DIR = Path(__file__).resolve().parent
_CACHE_PATH = _ADDON_DIR / "user_files" / "cache.sqlite"
#: Synthesised audio is kept on disk so repeating a card costs no network.
_TTS_CACHE_DIR = _ADDON_DIR / "user_files" / "tts"

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised only inside Anki
    import aqt
    import aqt.reviewer  # imported explicitly; `import aqt` alone may not bind it
    from aqt import gui_hooks, mw
    from aqt.addons import AddonManager
    from aqt.operations import QueryOp
    from aqt.webview import WebContent

    _INSIDE_ANKI = mw is not None
except ImportError:  # pragma: no cover - test / tooling environment
    _INSIDE_ANKI = False


_cache: Optional[TranslationCache] = None
_cache_lifetime_days: Optional[int] = None
# `without_collection()` lets translations run in parallel, so the cache
# singleton is reachable from several worker threads at once.
_cache_lock = threading.Lock()


# -- configuration ----------------------------------------------------------


def _raw_config() -> Dict[str, Any]:
    """Read the merged config.json + meta.json mapping Anki maintains."""
    if not _INSIDE_ANKI:
        return dict(DEFAULTS)
    raw = mw.addonManager.getConfig(__name__)
    return dict(raw) if isinstance(raw, dict) else dict(DEFAULTS)


def _load_config() -> Tuple[AddonConfig, Optional[str]]:
    """Return ``(config, error)``.

    A broken configuration must not disable the whole add-on: pronunciation and
    the popup still work on defaults, and the error is reported when the user
    actually presses Translate.
    """
    try:
        return parse_config(_raw_config()), None
    except ConfigurationError as exc:
        logger.warning("Invalid configuration: %s", exc)
        return parse_config(DEFAULTS), str(exc)


def _get_cache(config: AddonConfig) -> Optional[TranslationCache]:
    """Lazily build the cache, rebuilding it when the lifetime setting changes."""
    global _cache, _cache_lifetime_days
    if not config.cache_enabled:
        return None
    with _cache_lock:
        if _cache is None or _cache_lifetime_days != config.cache_lifetime_days:
            _cache = TranslationCache(_CACHE_PATH, config.cache_lifetime_seconds)
            _cache_lifetime_days = config.cache_lifetime_days
            _cache.purge_expired()
        return _cache


# -- translation (worker thread) --------------------------------------------


def _translate_with(config: AddonConfig, provider: str, text: str) -> Dict[str, Any]:
    """Cache-aware translation through one named provider.

    Cache entries are keyed by provider, so a fallback result never masquerades
    as one from the primary backend.
    """
    cache = _get_cache(config)

    if cache is not None:
        hit = cache.get(provider, config.source_language, config.target_language, text)
        if hit is not None:
            logger.debug("Cache hit (%s chars) via %s", len(text), provider)
            return {
                "text": hit.text,
                "sourceLang": hit.source_lang,
                "targetLang": hit.target_lang,
                "provider": provider,
                "cached": True,
            }

    translator = build_translator(config, provider)
    translator.validate()

    logger.debug("Translating %s chars via %s", len(text), provider)
    result = translator.translate(
        TranslationRequest(
            text=text,
            source_lang=config.source_language,
            target_lang=config.target_language,
        )
    )

    if cache is not None:
        cache.set(provider, config.source_language, config.target_language, text, result)

    return {
        "text": result.text,
        "sourceLang": result.source_lang,
        "targetLang": result.target_lang,
        "provider": provider,
        "cached": False,
    }


def _translate_blocking(text: str) -> Dict[str, Any]:
    """Perform a translation. Runs on a worker thread - no Qt calls in here."""
    config, config_error = _load_config()
    if config_error:
        raise ConfigurationError(config_error)

    primary = config.translation_provider
    try:
        payload = _translate_with(config, primary, text)
        payload["usedFallback"] = False
        return payload
    except TranslationError as primary_error:
        if not config.fallback_provider:
            raise

        # Any failure is worth retrying elsewhere: a missing key, an exhausted
        # quota, and a broken unofficial endpoint all leave the user stuck.
        logger.warning(
            "Provider %s failed (%s); trying fallback %s",
            primary,
            primary_error,
            config.fallback_provider,
        )
        try:
            payload = _translate_with(config, config.fallback_provider, text)
        except TranslationError as fallback_error:
            raise ProviderError(
                f"Both providers failed. {primary}: {primary_error} "
                f"Fallback {config.fallback_provider}: {fallback_error}"
            ) from fallback_error

        payload["usedFallback"] = True
        return payload


# -- speech (worker thread) -------------------------------------------------


def _speech_cache_path(provider: str, lang: str, text: str) -> Path:
    key = hashlib.sha256(
        "\x00".join((provider, lang, text)).encode("utf-8")
    ).hexdigest()
    return _TTS_CACHE_DIR / f"{key}.mp3"


def _synthesize_blocking(text: str) -> str:
    """Return a path to playable audio. Runs on a worker thread."""
    config, config_error = _load_config()
    if config_error:
        raise ConfigurationError(config_error)

    engine = GoogleTextToSpeech(config.request_timeout_seconds)
    path = _speech_cache_path(engine.name, config.speech_language, text)
    if path.is_file() and path.stat().st_size > 0:
        logger.debug("Speech cache hit (%s chars)", len(text))
        return str(path)

    logger.debug("Synthesising %s chars via %s", len(text), engine.name)
    audio = engine.synthesize(text, config.speech_language)

    _TTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Write to a temporary name first so a failed download can never leave a
    # truncated file that later looks like a valid cache hit.
    partial = path.with_suffix(".part")
    partial.write_bytes(audio)
    partial.replace(path)
    return str(path)


def _start_speech(web: Any, request_id: int, text: str) -> None:
    text = text.strip()
    if not text:
        return
    if len(text) > MAX_SPEECH_CHARS:
        _send_to_webview(
            web,
            {
                "id": request_id,
                "kind": "speech",
                "ok": False,
                "error": (
                    f"The selection is too long to pronounce ({len(text)} "
                    f"characters). Select at most {MAX_SPEECH_CHARS}."
                ),
            },
        )
        return

    def op(_col: Any) -> str:
        return _synthesize_blocking(text)

    def success(path: str) -> None:
        # Imported lazily: this module is loaded during Anki's startup, before
        # the audio stack is ready, and add-ons should not force it up early.
        from aqt.sound import av_player

        av_player.stop_and_clear_queue()  # never overlap two pronunciations
        av_player.play_file(path)
        _send_to_webview(web, {"id": request_id, "kind": "speech", "ok": True})

    def failure(exc: Exception) -> None:
        if isinstance(exc, (SpeechError, TranslationError)):
            message = str(exc)
        else:
            logger.exception("Unexpected speech failure")
            message = (
                f"Unexpected error: {type(exc).__name__}: {exc}. "
                "See the add-on log for details."
            )
        _send_to_webview(
            web, {"id": request_id, "kind": "speech", "ok": False, "error": message}
        )

    (
        QueryOp(parent=mw, op=op, success=success)
        .without_collection()
        .failure(failure)
        .run_in_background()
    )


# -- webview plumbing -------------------------------------------------------


def _js_json(payload: Any) -> str:
    """JSON that is safe both as a JS expression and inside a <script> block.

    ``ensure_ascii`` escapes umlauts and the U+2028/U+2029 line separators that
    would otherwise terminate a JS string literal; the ``</`` substitution stops
    a value such as ``</script>`` from closing the tag early.
    """
    return json.dumps(payload, ensure_ascii=True).replace("</", "<\\/")


_RESPONSE_HANDLERS = {
    "speech": "onSpeechResponse",
    "copy": "onCopyResponse",
}


def _send_to_webview(web: Any, payload: Dict[str, Any]) -> None:
    handler = _RESPONSE_HANDLERS.get(payload.get("kind", ""), "onTranslationResponse")
    web.eval(
        "globalThis.ankiTranslatePopup && "
        f"globalThis.ankiTranslatePopup.{handler}({_js_json(payload)});"
    )


def _is_reviewer(context: Any) -> bool:
    """True only for the main reviewer webview, not the answer-button bar."""
    return isinstance(context, aqt.reviewer.Reviewer)


def on_webview_will_set_content(web_content: "WebContent", context: Any) -> None:
    if not _is_reviewer(context):
        return

    package = mw.addonManager.addonFromModule(__name__)
    config, config_error = _load_config()
    if config_error:
        logger.warning("Serving reviewer with default settings: %s", config_error)

    # Runs before the <body> scripts, so reviewer.js sees the config immediately.
    web_content.head += (
        "<script>globalThis.ankiTranslatePopupConfig = "
        f"{_js_json(config.for_webview())};</script>"
    )
    web_content.css.append(f"/_addons/{package}/web/reviewer.css")
    web_content.js.append(f"/_addons/{package}/web/reviewer.js")


def on_js_message(
    handled: Tuple[bool, Any], message: str, context: Any
) -> Tuple[bool, Any]:
    if not message.startswith(BRIDGE_PREFIX):
        return handled
    if not _is_reviewer(context):
        return handled

    command, _, raw_payload = message[len(BRIDGE_PREFIX) :].partition(":")

    if command == "stop_speech":
        from aqt.sound import av_player

        av_player.stop_and_clear_queue()
        return True, None

    if command not in ("translate", "speak", "copy"):
        logger.warning("Ignoring unknown bridge command %r", command)
        return True, None

    try:
        payload = json.loads(raw_payload)
        request_id = int(payload["id"])
        text = str(payload["text"])
    except (ValueError, TypeError, KeyError):
        logger.exception("Malformed bridge payload from the reviewer")
        return True, None

    if command == "translate":
        _start_translation(context.web, request_id, text)
    elif command == "speak":
        _start_speech(context.web, request_id, text)
    else:
        _copy_to_clipboard(context.web, request_id, text)
    return True, None


def _copy_to_clipboard(web: Any, request_id: int, text: str) -> None:
    """Write to Qt's clipboard.

    Done in Python because Anki leaves JavascriptCanAccessClipboard disabled,
    which makes the webview's own clipboard APIs unusable. Synchronous and
    instant, so no worker thread is involved.
    """
    if not text:
        return
    try:
        mw.app.clipboard().setText(text)
    except Exception as exc:  # noqa: BLE001 - report rather than fail silently
        logger.exception("Clipboard write failed")
        _send_to_webview(
            web,
            {
                "id": request_id,
                "kind": "copy",
                "ok": False,
                "error": f"Could not copy to the clipboard: {exc}",
            },
        )
        return
    _send_to_webview(web, {"id": request_id, "kind": "copy", "ok": True})


def _start_translation(web: Any, request_id: int, text: str) -> None:
    text = text.strip()
    if not text:
        return
    if len(text) > MAX_TEXT_LENGTH:
        _send_to_webview(
            web,
            {
                "id": request_id,
                "ok": False,
                "error": (
                    f"The selection is too long ({len(text)} characters). "
                    f"Select at most {MAX_TEXT_LENGTH} characters."
                ),
            },
        )
        return

    def op(_col: Any) -> Dict[str, Any]:
        return _translate_blocking(text)

    def success(result: Dict[str, Any]) -> None:
        payload = {"id": request_id, "ok": True}
        payload.update(result)
        _send_to_webview(web, payload)

    def failure(exc: Exception) -> None:
        if isinstance(exc, TranslationError):
            message = str(exc)
        else:
            # Never swallow an unexpected error: log the traceback, show a
            # short message, and point the user at the add-on log.
            logger.exception("Unexpected translation failure")
            message = (
                f"Unexpected error: {type(exc).__name__}: {exc}. "
                "See the add-on log for details."
            )
        _send_to_webview(web, {"id": request_id, "ok": False, "error": message})

    # `without_collection` lets several translations run in parallel, since we
    # never touch the collection.
    (
        QueryOp(parent=mw, op=op, success=success)
        .without_collection()
        .failure(failure)
        .run_in_background()
    )


def on_config_updated(_new_config: Any) -> None:
    """Push edited settings into an already-open reviewer page."""
    global _cache, _cache_lifetime_days
    with _cache_lock:
        _cache = None
        _cache_lifetime_days = None

    config, error = _load_config()
    if error:
        logger.warning("Configuration saved with problems: %s", error)

    reviewer = getattr(mw, "reviewer", None)
    web = getattr(reviewer, "web", None)
    if web is None or mw.state != "review":
        return
    web.eval(
        "globalThis.ankiTranslatePopup && "
        f"globalThis.ankiTranslatePopup.onConfigChanged({_js_json(config.for_webview())});"
    )


def setup() -> None:
    """Register hooks. Called once at import time when running inside Anki."""
    global logger
    try:
        logger = AddonManager.get_logger(__name__)
    except Exception:  # pragma: no cover - older Anki without addon loggers
        logger.debug("Falling back to the module logger", exc_info=True)

    mw.addonManager.setWebExports(__name__, r"web/.*\.(css|js)")
    mw.addonManager.setConfigUpdatedAction(__name__, on_config_updated)
    gui_hooks.webview_will_set_content.append(on_webview_will_set_content)
    gui_hooks.webview_did_receive_js_message.append(on_js_message)
    logger.info("%s loaded", ADDON_NAME)


if _INSIDE_ANKI:  # pragma: no cover - exercised only inside Anki
    setup()
