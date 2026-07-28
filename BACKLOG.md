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

### 6. Cache the example lookups

Translations and audio are cached; Tatoeba lookups are not, so the same word
re-queries the corpus (~0.2s) every time. Reuse `TranslationCache` or add a
small sibling table.

### 7. Examples when the source language is `auto`

Tatoeba needs a concrete ISO 639-3 code, so examples are skipped entirely while
`source_language` is `auto`. The translation response already carries the
detected language — fetch examples with that instead of skipping.

### 8. Per-deck or per-notetype language pairs

A German deck and a Spanish deck currently share one global pair. Anki exposes
the current deck via `mw.col.decks.current()`; a mapping would remove most
manual swapping.
