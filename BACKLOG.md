# Backlog — Translate & Pronounce Popup

Ordered roughly by value. Anything here is deliberately *not* built yet.

---

## 1. Make the language pair interactive

**Status:** next up
**Touches:** `web/reviewer.js`, `web/reviewer.css`, `__init__.py`, `config.py`

Today `DE → EN` in the popup header is a static label. Make it a control.

**Wanted**

- Clicking **DE** opens a small picker to change the source language for this
  lookup, without opening Anki's add-on config.
- Clicking **EN** does the same for the target language.
- Clicking the **→** arrow swaps the two languages and re-runs the lookup, so
  reading an English card in a German deck is one click.

**Design notes**

- The swap must re-translate, not just relabel — the cached result under the
  old pair is not the answer for the new one. Cache keys already include both
  languages (`cache.make_key`), so a swap is a clean miss rather than a wrong
  hit.
- `source_language` accepts `auto`; the target must not. A swap while the
  source is `auto` needs a rule — probably resolve `auto` to the language the
  provider actually detected (the response carries it as `sourceLang`) and swap
  that, rather than refusing.
- Decide whether a change is per-lookup or persisted. Persisting means writing
  through `mw.addonManager.writeConfig`, which fires `setConfigUpdatedAction`
  and re-pushes config to the webview — that path already exists but would need
  a guard against a feedback loop.
- The picker list should come from Python (it knows what each provider
  supports) rather than being hard-coded in JS. DeepL, LibreTranslate and
  Google support different sets.
- Keyboard access: the header controls need `tabindex` and Enter/Space
  handling, and Escape must still close the popup rather than the picker only.

---

## 2. Cache size limit

`user_files/cache.sqlite` and `user_files/tts/` grow without bound. Entries
expire by age (`cache_lifetime_days`) but nothing caps total size. Add a row
count / byte ceiling with LRU eviction, or at least surface the size in the
config screen.

---

## 3. Offline TTS fallback via Qt

`tts_provider: "system"` depends on the webview seeing a voice, and Chromium
cannot see Narrator "natural voices". `QTextToSpeech` on the Python side may
reach voices the webview cannot. Worth probing before building: on this
machine Qt reported the same `en_US`-only list, so it may buy nothing.

---

## 4. Selection in other screens

The popup only exists in the reviewer. The card browser and the previewer use
different webviews and would need their own `webview_will_set_content` wiring.

---

## 5. Keyboard-driven selection

Selection is mouse-only by design — the add-on listens to `mouseup` rather than
binding keys Anki reserves. A safe opt-in shortcut (something unbound, checked
against `Reviewer._shortcutKeys()`) would let keyboard users trigger a lookup.
