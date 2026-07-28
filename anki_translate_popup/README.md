# Translate & Pronounce Popup

An Anki Desktop add-on for Windows 11. Select a word, phrase, or sentence while
reviewing and a compact popup appears next to the selection with a **Translate**
button plus two icon buttons — a speaker to pronounce and a clipboard to copy.
Both icons carry tooltips and ARIA labels, and the clipboard turns into a tick
for a moment after a successful copy.

The entire interface is in English.

---

## Contents

1. [Requirements and version assumptions](#requirements-and-version-assumptions)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Architecture](#architecture)
5. [Automated tests](#automated-tests)
6. [Manual testing checklist](#manual-testing-checklist)
7. [Known limitations](#known-limitations)
8. [Packaging as .ankiaddon](#packaging-as-ankiaddon)

---

## Requirements and version assumptions

Developed and verified against:

| Component | Version |
| --- | --- |
| Anki | **25.09.4** (`int_version` 250904) |
| Qt / PyQt | Qt 6.8, PyQt6, QtWebEngine 6.8 |
| Python | 3.13.5 (bundled with Anki) |
| `requests` | 2.32.4 (bundled with Anki — no extra dependency added) |

`manifest.json` declares `min_point_version: 250200` (Anki 25.02). Only 25.09.4
was actually tested; the floor is a conservative estimate, not a verified claim.

Every Anki API used is a documented, currently supported one — no deprecated
hooks:

| API | Purpose |
| --- | --- |
| `gui_hooks.webview_will_set_content` | Inject CSS/JS into the reviewer |
| `gui_hooks.webview_did_receive_js_message` | Receive `pycmd()` calls |
| `AddonManager.setWebExports` | Serve `web/` under `/_addons/` |
| `AddonManager.getConfig` / `setConfigUpdatedAction` | Configuration |
| `AddonManager.get_logger` | Add-on-scoped logging |
| `aqt.operations.QueryOp` | Run network calls off the UI thread |

Version-specific behaviour that was **verified empirically**, not assumed:

* **`speechSynthesis` exists** in Anki's QtWebEngine build (it is not enabled in
  every Qt build). Confirmed: `typeof window.speechSynthesis === "object"`.
* **Voices load asynchronously** — `getVoices()` returned `[]` for roughly 3–4
  seconds after page load. The add-on warms the list at startup and waits for
  `voiceschanged`.
* **`speak()` needs a transient user gesture.** A real click works; a synthetic
  one fails with `not-allowed`. Warming the voice list keeps the click-to-speak
  path inside Chromium's activation window.
* **Escape has no reviewer binding** in 25.09.4 (`Reviewer._shortcutKeys()`
  contains no Escape entry, and there is no `Key_Escape` handler in `aqt/main.py`),
  so the popup can close on Escape without stealing an Anki shortcut.
* **The reviewer page is built once per session** — cards are swapped by calling
  `_showQuestion()` in JS, so the injected script persists across cards and must
  survive them. It does.

---

## Installation

### Option A — install the packaged file

1. Build it (see [Packaging](#packaging-as-ankiaddon)) or use the supplied
   `anki_translate_popup.ankiaddon`.
2. In Anki: **Tools → Add-ons → Install from file…**
3. Select `anki_translate_popup.ankiaddon`.
4. Restart Anki.

### Option B — install from source (for development)

Copy or symlink the `anki_translate_popup` folder into your add-ons directory:

```
%APPDATA%\Anki2\addons21\anki_translate_popup
```

A symlink lets you edit in place (run as Administrator, or with Developer Mode on):

```powershell
New-Item -ItemType SymbolicLink `
  -Path "$env:APPDATA\Anki2\addons21\anki_translate_popup" `
  -Target "C:\path\to\anki_translate_popup"
```

Restart Anki. Confirm it loaded via **Tools → Add-ons** — it appears as
*Translate & Pronounce Popup*.

### Verify it works

Start reviewing any card, select some text with the mouse, and the popup should
appear. **Translate** and **Pronounce** both work immediately — the default
provider needs no API key. See the Terms-of-Service caveat under
[Configuration](#configuration).

---

## Configuration

**Tools → Add-ons → Translate & Pronounce Popup → Config.**

Full per-option documentation is in `config.md`, shown next to the editor in
Anki's config dialog. Changes take effect immediately — no restart.

### Default: no setup at all

Out of the box `translation_provider` is `"google_unofficial"`, which needs no
API key and no signup. German → English works the moment you install it.

The trade-off, stated plainly: that endpoint is **undocumented and unsupported**.
Google can rate-limit or break it without notice, and using it may breach their
Terms of Service. Translation quality for German is also a little below DeepL.
If either matters to you, switch provider below.

### Better quality (DeepL)

1. Get a free API key at <https://www.deepl.com/pro-api> (free keys end in `:fx`).
2. Set `"api_key": "your-key-here:fx"` and `"translation_provider": "deepl"`.

The free and paid DeepL hosts differ; the add-on picks the right one from the
`:fx` suffix automatically.

### Belt and braces (both)

`fallback_provider` retries with a second backend when the first fails — no key,
quota gone, rate-limited, offline, or the unofficial endpoint broken:

```json
"translation_provider": "deepl",
"fallback_provider": "google_unofficial"
```

DeepL quality while your quota lasts, Google keeping it working when it doesn't.
Reverse the two for free-by-default with DeepL as insurance.

When the fallback answers, the popup shows **via Google (fallback)** — you are
always told which service received your text, and each provider caches
separately so results never cross over. Disabled by default (`""`).

### Fully private setup (LibreTranslate)

Run LibreTranslate locally, then:

```json
{
  "translation_provider": "libretranslate",
  "libretranslate_endpoint": "http://localhost:5000"
}
```

No text leaves your machine.

### Privacy summary

Text is transmitted **only when you press Translate**. Selecting text, pressing
Pronounce, and pressing Copy are entirely local.

| Provider | Where text goes |
| --- | --- |
| `google_unofficial` **(default)** | `translate.googleapis.com`. **Undocumented endpoint, no service agreement, no stated retention policy.** May breach Google's Terms of Service. Set `enable_google_unofficial: false` to block it entirely. |
| `deepl` | `api.deepl.com` / `api-free.deepl.com` over HTTPS. DeepL states API text is not used for training and is deleted after translation. |
| `libretranslate` | Whichever endpoint you configure. Self-host for full privacy. |

Your API key is stored by Anki in `meta.json` in the add-on folder, in plain
text. It is never logged and never sent to the reviewer page — verified by test.

---

## Architecture

```
anki_translate_popup/
├── __init__.py          Anki hooks, bridge, threading, wiring
├── config.py            Typed + validated view over Anki's config dict
├── config.json          Defaults
├── config.md            User-facing option documentation
├── manifest.json        Add-on metadata
├── cache.py             SQLite translation cache with TTL
├── tts.py               Online speech, for languages with no usable voice
├── translation/
│   ├── base.py          Translator ABC, error hierarchy, shared HTTP
│   ├── deepl.py         DeepL API v2
│   ├── libretranslate.py
│   └── google_unofficial.py   Opt-in only, isolated
├── web/
│   ├── reviewer.js      Selection, popup, speech, clipboard
│   └── reviewer.css     Popup styling, light + dark
└── tests/               100 unit tests, no network
```

### Request flow

```
user selects text
      │  (nothing is sent anywhere)
      ▼
reviewer.js shows the popup
      │
      │  user presses Translate
      ▼
pycmd("anki_translate_popup:translate:{id,text}")
      │
      ▼
webview_did_receive_js_message  ─── main thread, returns immediately
      │
      ▼
QueryOp(...).without_collection().run_in_background()
      │
      │  ── worker thread ──────────────────────────
      │     cache lookup → provider HTTP call → cache store
      │  ─────────────────────────────────────────
      ▼
success/failure callback (main thread)
      │
      ▼
web.eval("...onTranslationResponse({...})")
      │
      ▼
popup renders result or error via textContent
```

### Design decisions

**Why the UI thread never blocks.** All network and SQLite work happens inside
`QueryOp.op`, which Anki runs on a worker thread. `without_collection()` marks
the operation as not needing the collection, so translations are not serialised
behind other collection operations. The bridge handler itself returns
immediately.

**Why injection is safe.** `reviewer.js` writes every external value —
the selection, the translation, error strings — with `textContent`, never
`innerHTML`. The only `innerHTML` assignment is a constant skeleton with no
interpolation. On the Python side, `_js_json()` uses `ensure_ascii=True` (which
escapes umlauts and the U+2028/U+2029 separators that would otherwise terminate
a JS string literal) and rewrites `</` as `<\/` so a value containing
`</script>` cannot close the injected tag early. Both are covered by tests.

**Why the CSS is full of `!important`.** The popup lives in the same document as
the card, so the card template's CSS applies to it. Templates routinely use
broad selectors with `!important` (`div { color: hotpink !important }`), which
beat an add-on rule at any specificity. The stylesheet re-states every inherited
typography and colour property so the popup looks identical on every deck.

**Why the selection is read from the DOM, not `Selection.toString()`.**
`toString()` returns the *rendered* text: on a card styled with
`text-transform: uppercase` it hands back `GROSS` for `groß` and `GRÜSSE` for
`Grüße` — destroying exactly the German characters this add-on exists to handle.
The add-on clones the range instead, strips `<style>`/`<script>` (Anki puts the
card's stylesheet inside `#qa`, and `textContent` would otherwise capture the
entire CSS and post it to a paid API), re-inserts line breaks at block
boundaries, and collapses whitespace.

**Why the cache opens a connection per call.** The cache is touched from Anki's
worker threads, and a `sqlite3` connection cannot be shared across threads.
Per-call connections avoid a lock, and the cost is irrelevant for a
user-triggered action. Note that `sqlite3.Connection` used as a context manager
commits the transaction but does **not** close the connection — `cache.py` wraps
it so the handle is always released.

**Adding a provider.** Subclass `Translator` in `translation/`, implement
`translate()` and `validate()`, set `name` / `requires_api_key` /
`privacy_note`, then register it in `PROVIDERS` and `build_translator()`. The
popup, cache, bridge and threading need no changes.

**Adding a TTS backend.** Subclass `TextToSpeech` in `tts.py` and implement
`synthesize(text, lang) -> bytes`; the caching, playback and error plumbing in
`_synthesize_blocking` are backend-agnostic. Audio plays through Anki's own
`av_player`, which uses the bundled mpv, so any format mpv understands works.
The browser path is separate: `pronounce()` in `reviewer.js` is the only place
that touches `speechSynthesis`, with `loadVoices()` and `pickVoice()` split out
as testable functions.

---

## Automated tests

100 tests, no network access, no paid API calls — every HTTP call is stubbed.

Run from the directory that *contains* `anki_translate_popup`:

```powershell
& "$env:LOCALAPPDATA\AnkiProgramFiles\.venv\Scripts\python.exe" `
  -m unittest discover -s anki_translate_popup/tests -t .
```

Any Python 3.9+ with `requests` installed also works:

```bash
python -m unittest discover -s anki_translate_popup/tests -t .
```

Coverage:

| File | Covers |
| --- | --- |
| `test_config.py` | Defaults, unknown provider, language-code normalisation, `auto` handling, type errors, range bounds, `true` not accepted as a number, all errors reported at once, API key never reaching the webview |
| `test_cache.py` | Key stability and collision resistance, read/write, reopen, overwrite, provider scoping, German/emoji/CJK round-trips, TTL boundaries, `0` = never expire, purge, clear, corrupt-database resilience, connection-close regression |
| `test_translation.py` | DeepL/LibreTranslate/Google parsing, free-vs-pro endpoint, auto-detection, malformed responses, HTTP 401/403/429/456/5xx mapping, timeouts, connection/SSL/DNS failures, timeout propagation, Unicode, provider gating, `</script>` escaping, U+2028/U+2029 escaping |
| `test_tts.py` | Word-boundary chunking, hard-splitting overlong words, multi-segment joining, MP3/ID3 sniffing, HTML-error-page rejection, empty body, rate limit, HTTP errors, timeouts, connection failure, Unicode |
| `test_fallback.py` | Fallback on network/quota/missing-key failures, no fallback when the primary succeeds, both-failed message naming both causes, fallback results cached under the fallback provider, no cache leakage between providers, fallback logged not silent, config validation |

---

## Manual testing checklist

Set up a deck with German cards, then work through these.

### Selection

- [ ] Select **one German word** (`Haus`) → popup appears next to it
- [ ] Select a **multi-word phrase** (`das große Haus`) → full phrase shown
- [ ] Select a **full sentence** → full sentence shown, popup stays on screen
- [ ] Select text on the **question side** → works
- [ ] Select text on the **answer side** → works
- [ ] Select text containing **ä ö ü ß** → shown correctly, not mangled
- [ ] Click without dragging → no popup
- [ ] Select only whitespace → no popup
- [ ] Select text spanning **two lines/paragraphs** → words are not glued together
- [ ] Select across the whole card (Ctrl+A style drag) → **no CSS appears** in the popup

### Popup behaviour

- [ ] Popup stays fully **inside the window**, including near the bottom edge
- [ ] Press **Escape** → popup closes
- [ ] **Click outside** → popup closes
- [ ] Click **×** → popup closes
- [ ] Hover the speaker and clipboard icons → tooltips read *Pronounce* and *Copy*
- [ ] Click the clipboard → turns into a tick for ~1s, then back; paste elsewhere to confirm
- [ ] Select text *inside* the popup → popup does not reset
- [ ] Resize the window while open → popup closes cleanly

### No interference with Anki

- [ ] **Space / Enter** still shows the answer and answers the card
- [ ] Answer buttons **1–4** still work
- [ ] **`e`** still opens the editor, **`u`** still undoes
- [ ] Clicking a **link** on a card still follows it
- [ ] Normal text selection still works when the add-on is disabled

### Appearance

- [ ] **Light mode** → readable, correct contrast
- [ ] **Dark mode** (Tools → Preferences → Appearance) → readable, correct contrast
- [ ] Toggle the theme **while the popup is open** → colours follow immediately
- [ ] Try a deck with a **heavily styled card template** → popup is unaffected
- [ ] Change `popup_font_size` → takes effect without restarting

### Translation

- [ ] **Straight after install, no config** → translation appears, languages shown as `de → en`
- [ ] **Repeat the same selection** → returns instantly, status shows *From cache*
- [ ] Switch to `deepl` with a valid key → translation appears
- [ ] Switch to `deepl` with **no API key** → clear message naming `api_key`, nothing sent
- [ ] Set `enable_google_unofficial: false` while Google is selected → clear message, nothing sent
- [ ] Set `fallback_provider` and break the primary (bad key / airplane mode) → translation still appears, labelled *via … (fallback)*
- [ ] Break **both** providers → one message naming both failures
- [ ] Set `fallback_provider` to the same value as `translation_provider` → config error explaining they must differ
- [ ] **No network** (turn off Wi-Fi) → *Could not reach the translation service*
- [ ] Set `request_timeout_seconds: 1` against a slow endpoint → timeout message names the value
- [ ] Set `source_language: "auto"` → detected language is displayed
- [ ] Select text containing **`<b>`, `&`, `<script>`** → shown literally as text, nothing executes, no layout break
- [ ] Set an invalid config value (e.g. `"request_timeout_seconds": "ten"`) → pressing Translate explains the problem
- [ ] Select an enormous block of text → refused with a length message
- [ ] Press Translate twice quickly → only the newest result is displayed

### Pronunciation

- [ ] Default (`tts_provider: "auto"`), **no German voice installed** → German audio is heard, status says *Spoken by Google (online voice)*
- [ ] Press Pronounce again on the same text → instant (served from `user_files/tts/`)
- [ ] With a **German system voice installed** → uses it, status names the voice, nothing goes online
- [ ] Press Pronounce **twice quickly** → the first stops, no overlap
- [ ] Pronounce **after translating** → the **original German** is spoken, not the English
- [ ] Set `tts_provider: "system"` with no German voice → clear message, nothing sent anywhere
- [ ] Set `tts_provider: "system"`, turn off Wi-Fi → still works if a voice exists
- [ ] Set `tts_provider: "google_unofficial"`, turn off Wi-Fi → clear *could not reach* message
- [ ] Close the popup while online audio is playing → audio stops
- [ ] Change `speech_rate` to `0.5` → noticeably slower
- [ ] Set `preferred_voice` to an installed voice name → that voice is used
- [ ] Set `preferred_voice` to a nonsense name → falls back to `speech_language`

### Persistence

- [ ] **Restart Anki** → add-on still loads, settings retained
- [ ] Restart Anki → previously translated text still returns from cache
- [ ] Set `cache_enabled: false` → every translation hits the network
- [ ] Delete `user_files/cache.sqlite` → cache rebuilds without error

---

## Known limitations

1. **Narrator "natural voices" are invisible to Anki.** Windows 11 has two
   unrelated voice systems. Classic SAPI5/OneCore voices are visible to every
   application; Narrator natural voices (`MicrosoftWindows.Voice.de-DE.Katja`
   and friends) are reserved for Narrator and are never registered as voice
   tokens. You can install German speech, see it listed in Settings, and still
   have no German voice available here. This is a Windows limitation, not an
   add-on bug — and it is exactly why `tts_provider` defaults to `auto`, which
   goes online rather than dead-ending. Use the `Add-WindowsCapability` command
   in `config.md` to install a classic voice if you want offline speech.
2. **Online TTS is unofficial.** The same caveats as the Google translation
   provider apply: undocumented endpoint, no service agreement, may break or
   rate-limit. Audio is cached in `user_files/tts/`, so repeats are free, but
   that folder has no size cap — delete it to reclaim space.
3. **Voice enumeration is slow to start.** System voices appear 3–4 seconds
   after the reviewer opens. The list is warmed at startup.
4. **System speech requires a real user gesture** (a Chromium rule). The popup's
   buttons satisfy it; scripted invocation does not. Online TTS is unaffected,
   because playback goes through Anki's own audio player rather than the webview.
5. **Whitespace is collapsed.** Newlines inside a selection become single spaces.
   This improves cache hits and suits words, phrases and sentences, but a
   deliberate line break (in a poem, say) is not preserved.
6. **The default provider is unofficial and may break at any time.** The Google
   endpoint is undocumented, unversioned, rate-limited at Google's discretion,
   and using it may breach their Terms of Service. It ships as the default
   because it needs no signup; switch to `deepl` or a self-hosted
   `libretranslate` for a supported API, or set `enable_google_unofficial:
   false` to block it. Verified working against the live endpoint at build time
   (~0.2–0.6 s per request), but that is not a guarantee it will keep working.
7. **The API key is stored in plain text** in Anki's `meta.json`, which is how
   Anki's configuration system works. `build_ankiaddon.py` deliberately excludes
   `meta.json` from the package so a key cannot be shipped by accident.
8. **Reviewer only.** The popup does not appear in the card browser, the previewer,
   or the note editor.
9. **Selection is mouse-driven.** Keyboard-only selection (Shift+arrows) does not
   raise the popup, because the add-on deliberately listens to `mouseup` rather
   than binding keys that Anki reserves.
10. **No automatic cache size limit.** Entries expire by age
    (`cache_lifetime_days`), but there is no maximum row count. Delete
    `user_files/cache.sqlite` to reset it.

---

## Packaging as .ankiaddon

From the directory containing `anki_translate_popup`:

```powershell
& "$env:LOCALAPPDATA\AnkiProgramFiles\.venv\Scripts\python.exe" build_ankiaddon.py
```

This writes `anki_translate_popup.ankiaddon` — a zip with `manifest.json` at the
archive **root** (not inside a subfolder), which is what Anki requires.

Deliberately excluded:

| Excluded | Why |
| --- | --- |
| `meta.json` | Holds the user's saved config **including the API key** |
| `user_files/` | The local translation cache |
| `__pycache__/`, `*.pyc` | Build artefacts |

To do it by hand instead: select the *contents* of the `anki_translate_popup`
folder (not the folder itself), send to a zip archive, and rename it to
`.ankiaddon`.

Install with **Tools → Add-ons → Install from file…**

To publish on AnkiWeb, upload the `.ankiaddon` at
<https://ankiweb.net/shared/addons/> — the `package` field in `manifest.json`
must stay stable across versions, and `human_version` should be bumped.
