# Translate & Pronounce Popup

An Anki Desktop add-on for Windows 11. Select a word, phrase, or sentence while
reviewing and a compact popup appears next to it, already showing the
translation — plus real example sentences so you can see the word in use.

The header carries three icon buttons (translate, speaker, clipboard) and a
close button. All have tooltips and ARIA labels.

By default the lookup runs **automatically on selection**, which means the
selected text is transmitted as soon as you select it. `auto_translate` and
`auto_pronounce` turn that off if you would rather click.

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
9. [Licence](#licence)

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
| `gui_hooks.webview_will_set_content` | Inject CSS/JS into the reviewer and previewer |
| `gui_hooks.webview_did_receive_js_message` | Receive `pycmd()` calls |
| `gui_hooks.state_shortcuts_will_change` / `focus_did_change` | Keep speech keys alive when reviewer focus moves to Qt |
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

With the default `auto_translate: true`, selected text is transmitted as soon
as you select it. `auto_pronounce` fetches online audio: with the default
`tts_provider: google_unofficial`, **nothing is spoken offline**, because a
card cannot use a system voice at all and a split between the two produced two
different voices for the same word. Turn both off for click-to-act behavior. Copy is always
local. DeepL and LibreTranslate probe their language-list API when the reviewer
opens; this sends no card text, though DeepL authenticates the probe with your
API key.

One case sends text you never selected: with **both** `source_language` and the
side's voice language on `auto`, card auto-pronounce asks the provider to
identify the card side, because nothing in the configuration names its
language. A 200-character sample goes, the answer is cached so a card costs at
most one detection, and naming a real `source_language` — or turning off
`auto_pronounce_card` — stops it entirely.

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
├── cache.py             SQLite translation/example cache with TTL
├── tts.py               Online speech, for languages with no usable voice
├── examples.py          Usage examples from the Tatoeba corpus
├── translation/
│   ├── base.py          Translator ABC, error hierarchy, shared HTTP
│   ├── deepl.py         DeepL API v2
│   ├── libretranslate.py
│   └── google_unofficial.py   Opt-in only, isolated
├── web/
│   ├── reviewer.js      Selection, popup, speech, clipboard
│   └── reviewer.css     Popup styling, light + dark
└── tests/               Unit tests with all network calls stubbed
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

**Why one implementation covers reviewer and previewer.** The browser's
previewer renders a card with the same `Reviewer.revHtml()` the reviewer uses,
so the injected JS and CSS work unchanged; the two only differ in which
attribute holds the webview (`Reviewer.web` vs `Previewer._web`), which
`_webview_for()` resolves. The answer-button bar is excluded because it holds
no card text, and the card-layout and note editors because they are text-editing
surfaces where a selection popup would fight with typing.

**Why the UI thread never blocks.** Translation, Tatoeba, TTS, provider
language-capability probes, and SQLite work happen inside `QueryOp.op`, which
Anki runs on a worker thread. `without_collection()` keeps them from being
serialised behind collection operations. Bridge handlers return immediately.

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
`translate()` / `validate()` and optionally `supported_languages()`, then
register it in `PROVIDERS` and `build_translator()`. The popup, cache, bridge
and threading need no changes.

**Adding a TTS backend.** Subclass `TextToSpeech` in `tts.py` and implement
`synthesize(text, lang) -> bytes`; the caching, playback and error plumbing in
`_synthesize_blocking` are backend-agnostic. Audio plays through Anki's own
`av_player`, which uses the bundled mpv, so any format mpv understands works.
The browser path is separate: `pronounce()` in `reviewer.js` is the only place
that touches `speechSynthesis`, with `loadVoices()` and `pickVoice()` split out
as testable functions.

---

## Automated tests

314 tests, no network access and no paid API calls — every HTTP call is stubbed.

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
| `test_config.py` | Defaults, deck pairs, provider-filtered pickers, language-code normalisation, `auto`, type/range errors, API key never reaching the webview |
| `test_cache.py` | Translation/example read/write and key scoping, Unicode, TTL and row limits, corrupt-database resilience, connection-close regression |
| `test_translation.py` | Provider parsing/capabilities, DeepL Chinese aliases, auto-detection, malformed responses, HTTP status/network failures, Unicode, provider gating, JS escaping |
| `test_examples.py` | ISO 639-1→3 mapping, spaced/Chinese phrase gating, limits, unsupported languages, HTTP/malformed responses, Unicode and safe markup handling |
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
- [ ] Click the **gear** → every switch and all three voice rows are visible at once, no scrolling, ticks matching the current config
- [ ] Flip a toggle → tick changes, menu stays open, setting persists after reopening the popup
- [ ] Turn *Speak the card as it appears* **on** mid-card → the card on screen is spoken at once, not one card later
- [ ] Turn it on **while the answer is showing**, with *Also speak the answer* off → the card's prompt is spoken, not silence
- [ ] Turn it off **while a card is being spoken** → the audio stops there and then
- [ ] Turn it **off** → nothing is spoken, and the next card is silent
- [ ] Reveal the answer, then turn *Also speak the answer* on → the answer is spoken immediately
- [ ] Flip a toggle with the browser previewer also open → both screens agree without a restart
- [ ] Flip one in the gear, then check Tools → Add-ons → Config → the same value is there
- [ ] Escape with the gear menu open → closes the menu only; a second Escape closes the popup
- [ ] Open the gear near the **bottom of the window** → the menu flips above the icon rather than overflowing
- [ ] Click the clipboard → turns into a tick for ~1s, then back; paste elsewhere to confirm
- [ ] Select text *inside* the popup → popup does not reset
- [ ] Resize the window while open → popup closes cleanly
- [ ] Click the source code (**DE**) → dropdown lists the configured languages plus *auto*
- [ ] Click the target code (**EN**) → dropdown lists them **without** *auto*
- [ ] Pick a different language → popup re-translates, does not merely relabel
- [ ] Click the **→** → languages swap and the text re-translates
- [ ] Swap while source is `auto` → the detected language becomes the target, never `auto`
- [ ] Escape with a dropdown open → closes the dropdown only; a second Escape closes the popup
- [ ] Reopen the popup after changing languages → the current deck's pair persisted
- [ ] Change deck A to `de → en`, deck B to `es → en`, then switch between them → each pair returns
- [ ] With DeepL/LibreTranslate configured → source and target lists hide unsupported choices
- [ ] Break the language-list probe → the full configured list remains available
- [ ] Tab to the language controls and press Enter → dropdown opens (keyboard accessible)
- [ ] Select text, press Escape, then **Ctrl+Shift+T** → popup reopens for that selection
- [ ] Press Ctrl+Shift+T with nothing selected → nothing happens
- [ ] Preview a card from the browser → popup works there too
- [ ] Set `enable_in_previewer: false` → popup no longer appears in the previewer, still works in the reviewer
- [ ] On a question, press **`x`** → the front is spoken, with nothing selected
- [ ] On the same question, press **`c`** → silence; the answer is not out yet
- [ ] Show the answer, press **`c`** → the back is spoken, without repeating the front
- [ ] Press **`x`** then **`c`** quickly → the second interrupts the first, they do not queue
- [ ] Press **`c`** twice → it speaks twice; the auto-pronounce dedupe does not swallow it
- [ ] Review a reversed card → `x` still speaks the prompt, `c` still speaks what you were recalling
- [ ] On a type-in-the-answer card, type a word containing **x** and **c** → both letters land in the field and nothing is spoken
- [ ] Set `pronounce_answer_shortcut: ""` → `c` does nothing, `x` still works
- [ ] With a `de → en` pair, press `x` then `c` → German voice for the front, English voice for the back
- [ ] Swap the pair in the header, then press `x` → the voice swaps with it
- [ ] Gear → **Voice for the back** → pick a language → it sticks, and the row shows it
- [ ] Gear → **Voice for the back** → **Auto** → follows the pair again
- [ ] Set `speech_language: de-AT` with a `de → en` pair → the front keeps the Austrian voice
- [ ] Put `Gen.` on an English back → spoken as "gen", not "Genitiv"

### Speech survives leaving the reviewer

- [ ] While a card is being spoken, press **`z`** → audio stops at once
- [ ] After `z`, press `x` → speaks again; `z` mutes nothing permanently
- [ ] Let a card auto-pronounce, press `z` mid-clip → that clip stops too
- [ ] **Sync**, return to the card, press `x` → still speaks
- [ ] **Edit** the card, close the editor, press `x` → still speaks, with the edited text
- [ ] Open **More**, pick an action, press `x` → still speaks
- [ ] Same three, but let the card auto-pronounce instead of pressing a key → still speaks
- [ ] Repeat Sync/Edit/More with `tts_provider: system` → click the card before `x`; no off-focus fallback sends text online

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

- [ ] **Straight after install, no config** → selecting a word translates it with no click
- [ ] Select a single word → up to 3 example sentences appear under *Examples · Tatoeba*
- [ ] Select a **whole sentence** → translation appears, no examples (expected: too long to look up)
- [ ] Select a word with no corpus match → translation still appears, no examples
- [ ] Set `show_examples: false` → no examples section, no Tatoeba request
- [ ] Set `auto_translate: false` → nothing is sent until the translate icon is pressed
- [ ] Set `auto_pronounce: false` → no audio until the speaker is pressed
- [ ] Select text near the **bottom of the window** → popup grows with examples and flips above the selection rather than overflowing
- [ ] **Repeat the same selection** → returns instantly, status shows *From cache*
- [ ] Switch to `deepl` with a valid key → translation appears
- [ ] Switch to `deepl` with **no API key** → clear message naming `api_key`, nothing sent
- [ ] Set `enable_google_unofficial: false` while Google is selected → clear message, nothing sent
- [ ] Set `fallback_provider` and break the primary (bad key / airplane mode) → translation still appears, labelled *via … (fallback)*
- [ ] Break **both** providers → one message naming both failures
- [ ] Set `fallback_provider` to the same value as `translation_provider` → config error explaining they must differ
- [ ] **No network** (turn off Wi-Fi) → *Could not reach the translation service*
- [ ] Set `request_timeout_seconds: 1` against a slow endpoint → timeout message names the value
- [ ] Set `source_language: "auto"` → detected language is displayed and examples still appear
- [ ] Translate `房子` from `zh` → translation and a short Tatoeba lookup work
- [ ] Select a Chinese sentence longer than 8 characters → translation works, example lookup is skipped
- [ ] With DeepL, target `zh` / `zh-TW` → simplified / traditional translation succeeds
- [ ] Select text containing **`<b>`, `&`, `<script>`** → shown literally as text, nothing executes, no layout break
- [ ] Set an invalid config value (e.g. `"request_timeout_seconds": "ten"`) → pressing Translate explains the problem
- [ ] Select an enormous block of text → refused with a length message
- [ ] Press Translate twice quickly → only the newest result is displayed

### Pronunciation

- [ ] **Show a card and touch nothing** → the German side is spoken automatically
- [ ] Reveal the answer → the **answer only** is spoken, not the question again
- [ ] Same card side re-rendering → spoken once, not twice
- [ ] A card with its own `[sound:]` audio → Anki's clip plays first, the spoken text follows, neither is cut off
- [ ] Turn *Speak the card as it appears* off in the gear → next card is silent
- [ ] **Sync** while a card is being spoken → the audio stops, and the card is not spoken again afterwards
- [ ] Edit a card, or open **More**, and come back → not spoken again, however long you took
- [ ] Answer the card and press **Again** → the question *is* spoken again: that is a real second showing
- [ ] Under an `auto` pair, let the card auto-pronounce, then press **x** → the same language, not the `speech_language` fallback
- [ ] `source_language: "auto"` on an English deck → the card is spoken in English, not the `speech_language` German
- [ ] A card reading `die Aktie, -n` under an `auto` pair → spoken as German, not as English
- [ ] A card with a German line then an English line, `card_speech_scope: full` → each line in its own voice
- [ ] A card of three German lines → still one clip, not three
- [ ] Same card again → spoken with no second detection request (check the log with `debug_logging: true`)
- [ ] `source_language: "auto"` with no network → the card still speaks, using `speech_language`
- [ ] Pin `front_speech_language` to a language → no detection happens at all
- [ ] Set `tts_provider: "system"` → card auto-pronounce stops (needs a user gesture the browser will not grant)
- [ ] Default (`tts_provider: "google_unofficial"`) → every pronunciation says *Spoken by Google (online voice)*, selections and cards alike
- [ ] A selection and a card of the same word → the **same voice** for both
- [ ] Gear → **Voice source** → *System only* → card auto-pronounce stops, selections use an installed voice
- [ ] Set `enable_google_unofficial: false` → no new audio is fetched, with a message naming the switch
- [ ] Same text again after disabling it → the clip already in `user_files/tts/` still plays
- [ ] Press Pronounce again on the same text → instant (served from `user_files/tts/`)
- [ ] With a **German system voice installed** → uses it, status names the voice, nothing goes online
- [ ] Press Pronounce **twice quickly** → the first stops, no overlap
- [ ] Select text **while the card is being auto-pronounced** → the card audio stops, only the selection is heard
- [ ] Speak a selection, then reveal the answer → the leftover speech stops as the new side appears
- [ ] Press **x** while a card's own `[sound:]` is playing → the clip stops and the side is spoken, not both at once
- [ ] Close the popup while a card's `[sound:]` plays → the clip keeps going; the popup only cancels what it started
- [ ] Pronounce **after translating** → the **original German** is spoken, not the English
- [ ] Set the pair to **EN → EN** and press Pronounce → an English voice speaks it, not the German one
- [ ] Set `speech_language: "de-AT"` with a **DE → EN** pair → still the Austrian voice, not a bare `de` one
- [ ] Source **auto**, select German, translate, then Pronounce → the detected language picks the voice
- [ ] Change the pair in the header, then press Pronounce immediately → the new language is used, not the old
- [ ] Source **auto**: select a German word, then an English one → each is spoken in its own language, not both in the first
- [ ] Source **auto**: the header reads **AUTO·DE** after a German lookup, and **AUTO** again on the next selection
- [ ] Source **auto** with `auto_translate: false` → nothing is sent merely to detect a language; speech uses `speech_language`
- [ ] Press Escape while the status reads *Detecting language…* → nothing is spoken when the translation lands
- [ ] Select the same word twice → the **same voice** both times, never male one time and female the next
- [ ] Gear → **Prefer a voice** → *Male* → a male voice is used for a language that has one
- [ ] Gear → **Prefer a voice** → *Female* → back to a female voice
- [ ] A language with only one installed voice → still speaks, whichever gender that voice is
- [ ] Set `preferred_voice` to an installed voice → it wins over the gender preference
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
   add-on bug — and it is one reason `tts_provider` defaults to
   `google_unofficial` rather than to a system voice that may not exist. Use the
   `Add-WindowsCapability` command in `config.md` to install a classic voice if
   you want `system` or `auto` to be worth choosing.
2. **Online TTS is unofficial, and now the default.** Every pronunciation
   goes through it unless you change `tts_provider`, so the caveats are no
   longer a fallback's caveats: undocumented endpoint, no service agreement,
   may break or
   rate-limit. Audio is cached in `user_files/tts/`; `tts_cache_max_mb` limits
   its size.
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
8. **Reviewer and previewer only.** Not the note editor or the card-layout
   editor: those are text-editing surfaces where a selection popup would fight
   with typing. Turn the previewer off with `enable_in_previewer`.
9. **Selection is mouse-driven.** Anki's reviewer has no text caret, so
   Shift+arrow selection is not possible in the first place. `lookup_shortcut`
   re-opens the popup for a selection you already made; it cannot create one.
10. **A Qt-side TTS provider would buy nothing.** `QTextToSpeech` was probed on
    both its Windows engines and reports exactly the same voices the webview
    already sees — `sapi` gives `['en_US']` (David, Zira) and `winrt` gives
    `['en_US']` (David, Zira, Mark). Neither exposes a German voice, so routing
    speech through Qt would not reach the Narrator natural voices either. Only
    installing a classic voice, or the online provider, actually helps.
11. **Examples are phrase-level only.** Tatoeba is searched for selections of
    up to 3 words / 40 characters, or 8 characters for unspaced Chinese. Whole
    sentences are skipped because they return nothing useful.
12. **Off-focus system speech cannot be synthesized through Qt.** The Qt
    fallback after Sync/Edit/More can use online-capable modes, but strict
    `tts_provider: system` needs the keypress inside Chromium. Click the card to
    restore focus; the fallback never weakens the no-network promise.
13. **The pronounce keys cannot detect a language on their own.** Under an
    `auto` pair, `x` and `c` use a detection the card's own auto-pronounce
    already paid for. With `auto_pronounce_card` off there is nothing in the
    cache and they fall back to `speech_language`, because they are handled on
    the UI thread where a network call would freeze the reviewer. Pin
    `front_speech_language` / `back_speech_language`, or name a real
    `source_language`, if you want them exact without card auto-pronounce.
14. **Auto-lookup changes the privacy posture.** With the defaults, selecting
    text transmits it immediately — no button press gates it any more. This was
    an explicit request; `auto_translate`, `auto_pronounce` and `show_examples`
    each turn their own request off.

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
| `user_files/` | Local translation, example, and speech caches |
| `__pycache__/`, `*.pyc` | Build artefacts |

To do it by hand instead: select the *contents* of the `anki_translate_popup`
folder (not the folder itself), send to a zip archive, and rename it to
`.ankiaddon`.

Install with **Tools → Add-ons → Install from file…**

To publish on AnkiWeb, upload the `.ankiaddon` at
<https://ankiweb.net/shared/addons/> — the `package` field in `manifest.json`
must stay stable across versions, and `human_version` should be bumped.

### Cutting a release

`python release.py` does the whole sequence — tests, version bump, build,
commit, tag, push, GitHub release with the package attached:

```powershell
python release.py          # 1.0.0 -> 1.0.1
python release.py 1.1.0    # or say which version
```

Any `python` on your PATH will do, from any directory. The suite needs Anki's
own `aqt`, which a system Python does not have, so the script locates Anki's
bundled interpreter itself rather than making you type its path.

It refuses to start unless the tree is clean, the branch is `main`, the version
is newer than the released one, and no commit since the last tag carries a
co-author trailer. Tests run *before* the bump, so a failure leaves the tree
untouched.

AnkiWeb is not automated — it has no API. The script ends by printing which
file to upload to which listing. Re-upload on the **existing** listing rather
than creating a second one, or nobody receives the update.

---

## Licence

AGPL-3.0-or-later — the same licence as Anki itself, which this add-on imports
at runtime. The full text is in `LICENSE`, and a copy ships inside every
`.ankiaddon` build.
