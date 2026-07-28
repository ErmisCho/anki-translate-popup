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

### ✅ 13. A voice per card side

Item 12 exposed a bug it did not cause: `speech_language` is one setting, so
pressing `c` read an English answer with a German voice. A deck has a language
per side, not one language.

`front_speech_language` and `back_speech_language` (both `auto`) fix it, on the
gear menu as *Front voice* and *Back voice*. `auto` follows the pair the popup
header already declares — front = `source_language`, back = `target_language` —
so swapping the pair swaps the voices, and pinning a side handles a deck whose
backs are not in the target language.

Regions survive: `de-AT` with a `de → en` pair speaks the front in `de-AT`, not
the bare `de`. `preferred_voice` names one specific voice, so it now applies
only to the side whose language it was chosen for.

The language reaches the engine on every path — the cache key already included
it, so the two sides never share a clip. Abbreviation expansion moved onto the
side's own language too: it keyed off `speech_language`, which would have
turned an English *gen* into *Genitiv* the moment the back was spoken.

This is also the gear menu's first non-boolean setting. `set_option` takes the
type from the key rather than the payload, so a webview sending a string at a
toggle still cannot store one.

### 14. Speech dies after a sync, an edit, or the More menu

**Partly fixed — needs a report from a real Anki to finish.**

Reported: after syncing, editing a card, or using the **More** menu,
pronunciation stops and never starts again. Could not be reproduced here (no
Anki in this environment), so this was attacked as three separate causes, two
of which are provable from the code and are now fixed.

**Fixed — the page loses the pushed text.** Item 12 pushes each card side's
text into the webview once, as it appears. Anything that rebuilds the reviewer
page after that push leaves the page holding nothing to say, with no way to ask
for it, so `x` and `c` stay dead until the *next* card. The page now asks
Python for the text when it has none (`card_text` bridge command). Python
answers from `mw.reviewer.card` and, crucially, decides for itself whether the
answer may be sent — asking is not a way to hear the answer early.

**Fixed — Chromium leaves `speechSynthesis` paused.** Backgrounding the page
pauses the synthesiser, and nothing resumes it, so every later `speak()` queues
silently. A sync dialog, the editor and the More menu all background the page.
`synth.resume()` now runs before each utterance; it is a no-op when nothing is
paused.

**Open — the webview may simply not have keyboard focus.** All three actions
move focus to a Qt widget, and the reviewer's webview may not get it back.
Anki's own keys keep working because they are Qt shortcuts; ours are a `keydown`
listener on the page, so they would go silently dead in exactly this pattern.
Unproven, and the fix is structural: register the keys through
`gui_hooks.state_shortcuts_will_change` as well, which costs the system-voice
support that the webview path exists for.

**How to tell them apart**, if it recurs: set `debug_logging: true`, press the
key, open the console. A `shortcut:` line means the key arrived and this is not
a focus problem. No line means the page never saw the key, and the remaining
cause above is the one to build.

### ✅ 15. A key to stop the current pronunciation

`stop_speech_shortcut` (default `z`) silences whatever is speaking right now —
an auto-pronounced card, a selection, or either pronounce key.

It stops that one clip and nothing else: the next card and the next `x` or `c`
speak as usual, so there is no muted state to undo. Unlike the internal stop
used when one pronunciation supersedes another, it always reaches across the
bridge, because card auto-pronounce is queued by Python without the webview
knowing — which is exactly the audio a user most wants to cut off.

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
