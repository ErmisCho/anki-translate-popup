# Backlog — Translate & Pronounce Popup

---

## Done

### ✅ 1. Interactive language pair

`DE → EN` in the header is now three controls: click the source or target code
to pick a language, click the **→** to swap and re-translate. Choices persist
through a `set_languages` bridge command, validated in Python before it is
written so an invalid pair can never be saved. Swapping while the source is
`auto` uses the language the provider actually detected, because `auto` is not
a legal target. Languages offered come from `picker_languages`.

### ✅ 2. Cache size limits

`cache_max_entries` (default 5000) caps the translation cache, evicting oldest
first; `tts_cache_max_mb` (default 100) caps the synthesised-audio folder.
Both accept `0` for unlimited. Eviction runs as a single indexed `DELETE`
inside the write that `set()` already performs, so the table sits exactly at
the limit rather than sawtoothing above it.

### ✅ 4. Previewer support

The popup now works in the browser's card previewer as well as the reviewer —
both render a card with `Reviewer.revHtml()`, so one implementation covers
them. Gated by `enable_in_previewer`. Deliberately **not** added to the
card-layout or note editors: those are text-editing surfaces where a selection
popup fights with typing.

### ✅ 6. Settings gear, with card auto-pronounce

A gear icon in the popup header opens a menu of four toggles — auto-translate
selection, auto-pronounce selection, auto-pronounce card, show examples — each
written straight back to the add-on config through a `set_option` bridge
command. Python re-checks the key against its own allowlist, so the webview
cannot reach a setting the menu was never meant to touch.

**Auto-pronounce card** speaks each side as it appears, with no interaction.
Driven from Python via `reviewer_did_show_question` / `..._answer` and Anki's
own audio player, because the browser's `speechSynthesis` needs a user gesture
that a card appearing does not provide — so it is unavailable when
`tts_provider` is `system`. The answer side speaks only the part after the
`<hr id=answer>` divider, and the clip is *appended* to the audio queue so a
card's own `[sound:]` is never cut off.

Anki emits the show hook more than once per side (measured: two clips for one
card), so repeats of the same side within 2s are ignored.

### ✅ 12. Pronounce either side of the card by key

`pronounce_prompt_shortcut` (default `x`) speaks the side you are shown;
`pronounce_answer_shortcut` (default `c`) speaks the side you are predicting.
Both take the same spelling as `lookup_shortcut`, and `""` disables either.

Neither key knows which way round the card is, and neither needs to:
`card.question()` renders whichever side is the prompt for that template and
`card.answer()` the other, so a reversed card swaps them by itself.

The text is **pushed to the webview as each side appears**, not fetched when a
key is pressed. That keypress is the transient user activation that lets the
page use an installed system voice at all — spending it on a bridge round trip
risks Chromium expiring it first. It is also why these work with
`tts_provider: system`, which card auto-pronounce cannot.

`answer` is left empty until the answer is actually on screen, so `c` is silent
rather than spoiling a card you are still recalling. Both speak through the
same path as the Pronounce button, so a second press interrupts the first
instead of queueing, and the auto-pronounce dedupe window never sees them.

The defaults are bare letters, so `keydown` ignores anything typed into an
input, textarea or contenteditable — otherwise a type-in-the-answer card would
lose every `x` and `c`. Whether they collide with an Anki reviewer key is
checked in the README's manual pass, not here: it needs a running Anki.

### ✅ 5. Keyboard shortcut

`lookup_shortcut` (default `Ctrl+Shift+T`, `""` disables) re-opens the popup
for the current selection.

Note the original framing — "keyboard-driven *selection*" — was not achievable:
Anki's reviewer has no text caret, so Shift+arrow cannot create a selection in
the first place. The shortcut acts on a selection you already made.

---

## Closed without building

### ❌ 3. Offline TTS fallback via Qt

**Rejected on evidence.** The item said to probe before building, and the probe
says it would buy nothing. `QTextToSpeech` reports the same voices the webview
already sees, on both Windows engines:

```
sapi:  locales=['en_US']  voices=['Microsoft Zira Desktop', 'Microsoft David Desktop']
winrt: locales=['en_US']  voices=['Microsoft David', 'Microsoft Zira', 'Microsoft Mark']
```

Neither reaches the Narrator "natural voices" (`MicrosoftWindows.Voice.de-DE.Katja`),
which are registered nowhere any third-party app can see. A Qt provider would
add a config option and a code path that fail in exactly the cases the existing
system voice already fails in. Only installing a classic SAPI/OneCore voice, or
the online provider, actually helps.

Revisit only if Qt gains access to natural voices.

---

## Open

### 7. Cache the example lookups

Translations and audio are cached; Tatoeba lookups are not, so the same word
re-queries the corpus (~0.2s) every time. Reuse `TranslationCache` or add a
small sibling table.

### 8. Examples when the source language is `auto`

Tatoeba needs a concrete ISO 639-3 code, so examples are skipped entirely while
`source_language` is `auto`. The translation response already carries the
detected language — fetch examples with that instead of skipping.

### 9. Per-deck or per-notetype language pairs

A German deck and a Spanish deck currently share one global pair. Anki exposes
the current deck via `mw.col.decks.current()`; a mapping would remove most
manual swapping.

### 10. Hide unsupported languages from the dropdowns

`picker_languages` is a hand-written list that nothing checks against the active
provider, so the dropdown happily offers a language the provider will refuse —
the failure only shows up as an error after you pick it. `Translator` has no
capability surface at all today; both DeepL and LibreTranslate expose a
`/languages` endpoint, so add a `supported_languages()` to the ABC and filter
the list in `config.py::as_payload` before `pickerLanguages` reaches the
webview. Fall back to the unfiltered list when the probe fails, and keep the
currently-selected language visible either way, as `config.md` already
promises.

### 11. Support English, German, Chinese and Greek

`el` is already in the picker defaults, `zh` is not — add it. Chinese needs more
than a list entry:

- DeepL splits the target into `ZH-HANS` / `ZH-HANT` while the source stays
  `ZH`; the config validator treats codes as opaque, so it will accept a target
  the provider rejects.
- `ISO_639_1_TO_3` maps `zh → cmn`, so Tatoeba examples work once the code is
  offered.
- `is_example_worthy` counts words with `str.split()`. Chinese has no spaces, so
  any sentence under 40 characters counts as one word and gets sent as an
  example query. Gate on character count for scripts that do not space-separate.
- Confirm a `zh-CN` voice exists before promising pronunciation — the same
  Windows voice gap that closed item 3.
