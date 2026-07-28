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
import html
import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .cache import TranslationCache, prune_audio_cache
from .config import DEFAULTS, AddonConfig, parse_config
from .examples import TatoebaExamples
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
    import aqt.browser.previewer  # explicit: `import aqt` alone does not bind these
    import aqt.reviewer
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
            _cache = TranslationCache(
                _CACHE_PATH,
                config.cache_lifetime_seconds,
                max_entries=config.cache_max_entries,
            )
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
        payload["examples"] = _fetch_examples(config, text)
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
        payload["examples"] = _fetch_examples(config, text)
        return payload


def _fetch_examples(config: AddonConfig, text: str) -> List[Dict[str, str]]:
    """Look up usage examples. Never allowed to fail a translation."""
    if not config.show_examples:
        return []
    try:
        found = TatoebaExamples(config.request_timeout_seconds).fetch(
            text, config.source_language, config.target_language
        )
    except Exception:  # noqa: BLE001 - examples are a bonus, not the answer
        logger.warning("Example lookup failed", exc_info=True)
        return []
    return [{"text": e.text, "translation": e.translation} for e in found]


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

    # Expand before the cache key is built, so "Akk." and "Akkusativ" share one
    # clip and the cached audio always matches what was actually spoken.
    text = prepare_speech_text(text, config)

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

    # Trim after writing, so the clip just fetched is the newest and survives.
    if config.tts_cache_max_mb:
        removed = prune_audio_cache(_TTS_CACHE_DIR, config.tts_cache_max_mb * 1024 * 1024)
        if removed:
            logger.debug("Pruned %s cached audio file(s)", removed)
    return str(path)


#: Toggles the popup's gear menu is allowed to change. An allowlist, because
#: this arrives from the webview and writes straight into the stored config.
_TOGGLEABLE_OPTIONS = (
    "auto_translate",
    "auto_pronounce",
    "auto_pronounce_card",
    "auto_pronounce_answer",
    "expand_abbreviations",
    "show_examples",
)

ANSWER_DIVIDER = "<hr id=answer>"

# Deliberately not anki.utils.strip_html: that call needs Anki's Rust i18n
# backend to be initialised, which would make this function untestable outside
# a running Anki. Tags become spaces so sibling blocks do not run together.
_STYLE_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_AV_TAG_RE = re.compile(r"\[(?:sound|anki:tts)[^\]]*\]", re.IGNORECASE)
#: Tags that end a visual line. Everything else is inline and becomes a space.
_BLOCK_TAG_RE = re.compile(
    r"</?(?:address|article|aside|blockquote|br|dd|div|dl|dt|figure|figcaption"
    r"|footer|h[1-6]|header|hr|li|main|nav|ol|p|pre|section|table|tbody|td"
    r"|tfoot|th|thead|tr|ul)\b[^>]*>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")


#: Grammatical abbreviations that appear constantly on German vocabulary cards.
#: A speech engine reads "Akk." as a letter salad, so expand it to the word.
#: Nominativ is included because a deck using the other three always uses it too.
GERMAN_ABBREVIATIONS = {
    "akk": "Akkusativ",
    "dat": "Dativ",
    "gen": "Genitiv",
    "nom": "Nominativ",
}
#: Word-bounded, so "Akku" (battery) and an already-spelled-out "Genitiv" are
#: both left alone. The trailing full stop is kept: it is a natural pause.
_ABBREVIATION_RE = re.compile(
    r"\b(" + "|".join(sorted(GERMAN_ABBREVIATIONS)) + r")\b", re.IGNORECASE
)


def expand_german_abbreviations(text: str) -> str:
    """Replace Akk./Dat./Gen./Nom. with the full German words."""
    return _ABBREVIATION_RE.sub(
        lambda match: GERMAN_ABBREVIATIONS[match.group(1).lower()], text
    )


def prepare_speech_text(text: str, config: AddonConfig) -> str:
    """Final pass over text on its way to a speech engine."""
    # Only for German speech: "Gen" is a word in English, and expanding it
    # there would be wrong.
    if config.expand_abbreviations and config.speech_language.lower().startswith("de"):
        return expand_german_abbreviations(text)
    return text


def card_side_lines(rendered: str, *, is_answer: bool) -> List[str]:
    """The visible lines of one card side, in order, blanks removed.

    Anki renders the answer as question + divider + answer, so the question is
    dropped from the answer side or every answer would repeat it.
    """
    if is_answer and ANSWER_DIVIDER in rendered:
        rendered = rendered.split(ANSWER_DIVIDER, 1)[1]

    text = _STYLE_SCRIPT_RE.sub(" ", rendered)
    # "[sound:hello.mp3]" is a media reference, not something to read aloud.
    text = _AV_TAG_RE.sub(" ", text)
    text = _BLOCK_TAG_RE.sub("\n", text)
    # Inline tags are dropped, not spaced: a browser renders "<b>x</b>, y" with
    # no gap before the comma, and inserting one makes speech stumble.
    text = _TAG_RE.sub("", text)

    lines = []
    for raw_line in html.unescape(text).split("\n"):
        line = " ".join(raw_line.split())
        if line:
            lines.append(line)
    return lines


def card_side_text(rendered: str, *, is_answer: bool, first_line_only: bool = False) -> str:
    """Plain text of one card side, ready to be spoken.

    A vocabulary card's first line is the headword; the lines after it are
    usually a label ("Example"), a sample sentence, or the very thing the user
    is meant to be recalling - none of which should be read out. Hence
    ``first_line_only``, which is the default for card auto-pronounce.
    """
    lines = card_side_lines(rendered, is_answer=is_answer)
    if not lines:
        return ""
    return lines[0] if first_line_only else " ".join(lines)


#: Anki can emit reviewer_did_show_question more than once for a single card
#: (a re-render fires it again), and each one would queue another clip. Ignore
#: a repeat of the same side within this window, but not a genuine re-review
#: later on.
AUTO_SPEAK_DEDUPE_SECONDS = 2.0
_last_auto_spoken: Optional[Tuple[int, bool, float]] = None


def _is_duplicate_card_side(card: Any, is_answer: bool, now: float) -> bool:
    global _last_auto_spoken
    card_id = int(getattr(card, "id", 0) or 0)
    previous = _last_auto_spoken
    if (
        previous is not None
        and previous[0] == card_id
        and previous[1] == is_answer
        and now - previous[2] < AUTO_SPEAK_DEDUPE_SECONDS
    ):
        return True
    _last_auto_spoken = (card_id, is_answer, now)
    return False


def _push_card_text(card: Any, config: AddonConfig, *, is_answer: bool) -> None:
    """Hand the current card's spoken text to the webview.

    Pushed on every card side rather than fetched when a key is pressed: the
    keypress is the transient user activation that lets the webview use a
    system voice at all, and spending it on a bridge round trip risks Chromium
    expiring it before the utterance starts.

    ``answer`` stays empty until the answer is actually on screen, so the
    shortcut cannot read out the very thing the user is still recalling.
    """
    if not (config.pronounce_prompt_shortcut or config.pronounce_answer_shortcut):
        return
    web = getattr(getattr(mw, "reviewer", None), "web", None)
    if web is None:
        return

    first_line = config.speak_first_line_only
    try:
        payload = {
            "prompt": card_side_text(
                card.question(), is_answer=False, first_line_only=first_line
            ),
            "answer": (
                card_side_text(card.answer(), is_answer=True, first_line_only=first_line)
                if is_answer
                else ""
            ),
        }
    except Exception:  # noqa: BLE001 - never let this break the reviewer
        logger.exception("Could not read the card text for the pronounce shortcuts")
        return

    web.eval(
        "globalThis.ankiTranslatePopup && "
        f"globalThis.ankiTranslatePopup.onCardText({_js_json(payload)});"
    )


def _on_card_side_shown(card: Any, *, is_answer: bool) -> None:
    """Speak a card side the moment it appears, with no user interaction.

    Driven from Python rather than the webview on purpose: the browser's
    speechSynthesis needs a transient user activation, and a card appearing is
    not one, so the JS path would fail with "not-allowed". Anki's own audio
    player has no such restriction.
    """
    config, error = _load_config()
    # Before the auto-pronounce gates: the shortcuts stay usable even when
    # nothing is spoken automatically, which is most of their point.
    _push_card_text(card, config, is_answer=is_answer)
    if error or not config.auto_pronounce_card:
        return
    # The answer side is what the user is trying to recall, so speaking it is
    # off unless asked for.
    if is_answer and not config.auto_pronounce_answer:
        return
    # A system voice would need the same missing gesture, so this feature is
    # only available through the online provider.
    if config.tts_provider == "system":
        return
    if _is_duplicate_card_side(card, is_answer, time.monotonic()):
        logger.debug("Skipping duplicate auto-pronounce for the same card side")
        return

    try:
        text = card_side_text(
            card.answer() if is_answer else card.question(),
            is_answer=is_answer,
            first_line_only=config.speak_first_line_only,
        )
    except Exception:  # noqa: BLE001 - never let this break the reviewer
        logger.exception("Could not read the card text for auto-pronounce")
        return

    if not text:
        return
    if len(text) > MAX_SPEECH_CHARS:
        logger.debug("Card side too long to auto-pronounce (%s chars)", len(text))
        return

    def op(_col: Any) -> str:
        return _synthesize_blocking(text)

    def success(path: str) -> None:
        from anki.sound import SoundOrVideoTag
        from aqt.sound import av_player

        # append rather than play: play_file() clears the queue, which would cut
        # off any [sound:] tag Anki is already playing for this card.
        av_player.append_tags([SoundOrVideoTag(filename=path)])

    def failure(exc: Exception) -> None:
        # Unprompted playback must stay quiet about its failures: the user did
        # not ask for this right now, so a popup or banner would be noise.
        logger.warning("Card auto-pronounce failed: %s", exc)

    (
        QueryOp(parent=mw, op=op, success=success)
        .without_collection()
        .failure(failure)
        .run_in_background()
    )


def on_reviewer_did_show_question(card: Any) -> None:
    _on_card_side_shown(card, is_answer=False)


def on_reviewer_did_show_answer(card: Any) -> None:
    _on_card_side_shown(card, is_answer=True)


def _set_option(raw_payload: str) -> None:
    """Flip one boolean setting from the popup's gear menu."""
    try:
        payload = json.loads(raw_payload)
        key = str(payload["key"])
        value = bool(payload["value"])
    except (ValueError, TypeError, KeyError):
        logger.exception("Malformed set_option payload")
        return

    if key not in _TOGGLEABLE_OPTIONS:
        logger.warning("Refusing to set unknown option %r from the webview", key)
        return

    raw = _raw_config()
    raw[key] = value
    try:
        parse_config(raw)
    except ConfigurationError as exc:
        logger.warning("Refusing invalid option change (%s=%s): %s", key, value, exc)
        return

    mw.addonManager.writeConfig(__name__, raw)
    logger.debug("Option %s set to %s", key, value)


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


def _webview_for(context: Any) -> Optional[Any]:
    """Return the webview to inject into, or None for an unsupported screen.

    The reviewer and the browser's previewer both render a card with
    ``Reviewer.revHtml()``, so the same popup works in each; they simply keep
    their webview under different attribute names. The bottom answer-button bar
    (``ReviewerBottomBar``) and the card-layout editor are deliberately
    excluded - the former holds no card text, and the latter is a text editor
    where a selection popup would fight with typing.
    """
    if isinstance(context, aqt.reviewer.Reviewer):
        return context.web

    previewer = getattr(aqt.browser.previewer, "Previewer", None)
    if previewer is not None and isinstance(context, previewer):
        config, _ = _load_config()
        if not config.enable_in_previewer:
            return None
        return getattr(context, "_web", None)

    return None


def _is_reviewer(context: Any) -> bool:
    """True for any screen the popup supports."""
    return _webview_for(context) is not None


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
    web = _webview_for(context)
    if web is None:
        return handled

    command, _, raw_payload = message[len(BRIDGE_PREFIX) :].partition(":")

    if command == "stop_speech":
        from aqt.sound import av_player

        av_player.stop_and_clear_queue()
        return True, None

    if command == "set_languages":
        _set_languages(raw_payload)
        return True, None

    if command == "set_option":
        _set_option(raw_payload)
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
        _start_translation(web, request_id, text)
    elif command == "speak":
        _start_speech(web, request_id, text)
    else:
        _copy_to_clipboard(web, request_id, text)
    return True, None


def _set_languages(raw_payload: str) -> None:
    """Persist a language pair chosen from the popup header.

    Validated before it is written: the popup is the only caller today, but a
    bad pair saved here would break every later lookup, and ``target`` must
    never be ``auto``.
    """
    try:
        payload = json.loads(raw_payload)
        source = str(payload["source"])
        target = str(payload["target"])
    except (ValueError, TypeError, KeyError):
        logger.exception("Malformed set_languages payload")
        return

    raw = _raw_config()
    raw["source_language"] = source
    raw["target_language"] = target
    try:
        parse_config(raw)
    except ConfigurationError as exc:
        logger.warning("Refusing invalid language change (%s -> %s): %s", source, target, exc)
        return

    # writeConfig fires setConfigUpdatedAction, which re-pushes the config to
    # every open webview - that is how the other screens stay in step.
    mw.addonManager.writeConfig(__name__, raw)
    logger.debug("Language pair set to %s -> %s", source, target)


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
    gui_hooks.reviewer_did_show_question.append(on_reviewer_did_show_question)
    gui_hooks.reviewer_did_show_answer.append(on_reviewer_did_show_answer)
    logger.info("%s loaded", ADDON_NAME)


if _INSIDE_ANKI:  # pragma: no cover - exercised only inside Anki
    setup()
