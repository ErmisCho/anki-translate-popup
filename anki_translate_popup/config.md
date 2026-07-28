## Translate & Pronounce Popup — Configuration

Select text on a card while reviewing and a popup shows the translation, plus
real example sentences using the word. The header has a **translate**,
**speaker** and **clipboard** icon.

By default the lookup happens automatically on selection, which means the
selected text is transmitted as soon as you select it — see `auto_translate`
and `auto_pronounce` below to turn that off.

Changes take effect immediately — you do not need to restart Anki.

Every change takes effect at once — from this dialog or from the gear — with no
restart. Turning card speech on speaks the card already on screen rather than
waiting for the next one.

The switches you are most likely to change are also on the **gear icon** in the
popup itself — auto-translate selection, auto-pronounce selection,
auto-pronounce card and its answer, abbreviation expansion, show examples —
along with the **front and back voice languages**. Changing one there writes it
here.

**Out of the box** this uses the unofficial Google Translate endpoint, so it
works with no API key and no signup. That endpoint is undocumented and using it
may breach Google's Terms of Service — see [Privacy](#privacy) below, and switch
`translation_provider` to `deepl` or `libretranslate` if you would rather not.

---

### `translation_provider`

Which backend performs the translation. One of:

| Value | Notes |
| --- | --- |
| `google_unofficial` | No API key needed. Unofficial endpoint — see the warning below. |
| `deepl` | Best German→English quality. Requires an API key. Free tier available. |
| `libretranslate` | Open source. Use your own server for full privacy. |

**Default:** `google_unofficial`

### `fallback_provider`

A second backend to try automatically when the first one fails — a missing API
key, an exhausted quota, a rate limit, no network, or the unofficial Google
endpoint breaking. Must be empty or a different provider from
`translation_provider`.

Useful combinations:

```json
"translation_provider": "deepl",
"fallback_provider": "google_unofficial"
```

Best quality when your DeepL quota allows, still working when it does not.

```json
"translation_provider": "google_unofficial",
"fallback_provider": "deepl"
```

Free by default, with DeepL as insurance if Google's unofficial endpoint stops
responding.

When the fallback answers, the popup says **via DeepL (fallback)** — you are
always told which service received your text. Nothing is retried silently. Both
providers cache separately, so a fallback result is never served later as if it
came from your primary provider.

Leave empty to disable. A failure then simply reports what went wrong.

**Default:** `""` (disabled)

### `source_language`

Language of the text you select, e.g. `de`. Set it to `auto` to let the
provider detect the language.

**Default:** `de`

### `target_language`

Language to translate into, e.g. `en`. DeepL also accepts regional variants
such as `en-GB` or `en-US`; LibreTranslate and the unofficial Google provider
use the two-letter part only.

**Default:** `en`

### `deck_language_pairs`

Optional per-deck overrides, keyed by Anki's stable numeric deck ID. Each value
is `[source, target]`:

```json
"deck_language_pairs": {
  "1234567890": ["es", "en"],
  "9876543210": ["auto", "zh-TW"]
}
```

The popup header writes the current card's deck entry automatically. Decks not
listed here use the global `source_language` / `target_language` pair above;
edit those globals in the Config dialog.

**Default:** `{}`

### `api_key`

Your provider API key. Required for DeepL, optional for LibreTranslate
(some instances require one), **unused by the default Google provider** — leave
it empty unless you switch to DeepL.

The key is stored in Anki's `meta.json` for this add-on **in plain text**, and
is never written to the log or sent to the reviewer page. Do not share your
`meta.json`.

**Default:** `""` (empty)

### `libretranslate_endpoint`

Base URL of the LibreTranslate instance, without a trailing `/translate`.
Examples: `http://localhost:5000`, `https://libretranslate.com`.

**Default:** `https://libretranslate.com`

### `enable_google_unofficial`

Safety switch for the unofficial Google endpoint, covering **both** translation
and audio — they are the same endpoint, so one switch governs both. Set it to
`false` and selecting that translation backend produces a clear error instead
of sending anything, and online speech refuses to fetch new audio.

Clips already in `user_files/tts/` still play: the guarantee is that no traffic
reaches the endpoint, and a file on disk generates none. Delete that folder to
be rid of them.

Note what this leaves you with, given the defaults: no translation and no new
audio at all until you pick a different provider or install a system voice.

**Default:** `true` (because `google_unofficial` is the default for both)

### `request_timeout_seconds`

How long to wait for the provider before giving up. Allowed range: 1–120.

**Default:** `10`

### `cache_enabled`

Cache translations and Tatoeba examples on disk so the same selection is not
requested twice. The cache lives in `user_files/cache.sqlite` inside the add-on
folder and survives restarts and add-on updates. Delete that file to clear it.

**Default:** `true`

### `cache_lifetime_days`

How long cached translations and examples stay valid. Use `0` to keep entries
forever.

**Default:** `30`

### `auto_translate`

Translate as soon as you select text, with no click.

**This changes when your text is transmitted.** With `auto_translate` on, the
selection is sent to your translation provider the moment you release the
mouse. Set it to `false` to go back to translating only when you press the
translate button.

**Default:** `true`

### `auto_pronounce`

Speak the selection as soon as you select it. Combined with `tts_provider`
resolving to online audio, this also transmits the selection on every
selection. Set to `false` if you would rather press the speaker yourself.

**Default:** `true`

### `auto_pronounce_card`

Speak the card as soon as it appears, before you touch anything. Shows the
German, hears the German.

It is queued behind the card's own `[sound:]` rather than replacing it, so
neither is cut off. A side is spoken **once**: Anki rebuilds the reviewer
page after a sync, an edit, or the More menu, and re-emits the hooks that
started the audio, but a rebuild is not you asking for the card again. Starting
a sync also stops whatever is playing. Answering the card and meeting it again
does speak it, because that is a genuine second showing. Starting a new pronunciation yourself — selecting text, or
pressing a pronounce key — does stop it: only one thing speaks at a time.

By default only the **question side** is spoken, and only its **first line** —
see `card_speech_scope` and `auto_pronounce_answer` below.

Toggleable from the **gear icon** in the popup, so you can silence it mid-review
without opening this file.

Two things to know:

* **It only works with online audio.** The browser's speech API requires a user
  gesture, and a card appearing is not one, so this is driven from Python
  through Anki's own audio player. If `tts_provider` is `system`, card
  auto-pronounce does nothing.
* **Each new card is a network request** unless its audio is already cached.
  Re-reviews are free; a fresh deck is one request per card.

It never interrupts a card's own `[sound:]` audio — the clip is queued after it,
not played over it.

**Default:** `true`

### `card_speech_scope`

How much of the card side to speak.

| Value | Behaviour |
| --- | --- |
| `first-line` | Only the first visible line — on a vocabulary card, the headword. |
| `full` | The whole side. |

A typical vocabulary card is laid out as headword, then a label, then an
example sentence:

```
der Gesichtspunkt, -e
Example
```

`full` would read *"der Gesichtspunkt, -e Example"* — the layout label included,
and on richer cards the sample sentence and even the answer. `first-line` reads
just `der Gesichtspunkt, -e`.

Lines are split on block boundaries (`<div>`, `<br>`, `<p>`, …), which is what
you see as a line break on the card. Inline markup like `<b>` does not split a
line, so **der _Gesichtspunkt_, -e** stays one line and keeps its punctuation.

Use `full` for sentence cards, where the whole side is the thing to hear.

**Default:** `first-line`

### `auto_pronounce_answer`

Also speak the answer side when you reveal it. Off by default: the answer is
what you are trying to recall, so speaking it hands it to you.

When on, only the part after the answer divider is spoken, never a repeat of
the question. Also on the gear menu, as *Also speak the answer*.

**Default:** `false`

### `front_speech_language` / `back_speech_language`

Which language each side of a card is spoken in. A deck has a language per
side — the front is the word you are learning, the back its translation — so
reading both with one voice gives an English answer a German accent.

| Value | Meaning |
| --- | --- |
| `auto` | Follow the translation pair: front = `source_language`, back = `target_language`. |
| a code | Always that language, e.g. `en`, `de-AT`, `el`. |

`auto` is right whenever the deck matches the pair in the popup header, which
is the normal case — swap the pair and the voices swap with it. Pin a side when
your deck does not match, for instance a German deck you translate into English
but whose backs are written in Greek.

Both are on the **gear menu** as *Voice for the front* and *Voice for the back*, with **Auto**
at the top of each list.

Two details:

* **`auto` with an `auto` source asks the provider.** When neither this setting
  nor the pair names a language, the card side is sent to your translation
  provider to be identified, and the answer decides the voice. Only the first
  200 characters go, and the result is cached, so a card costs at most one
  detection however often it comes round.

  The **whole side** is what gets identified, even when only its first line is
  spoken. A headword on its own — `die Aktie, -n` is thirteen characters of
  noun and plural ending — is routinely called Dutch or English; the side it
  came from is not.

  Lines are then spoken in **their own** languages. A German headword followed
  by an English definition is read by two voices rather than one, with
  consecutive lines of a language staying in a single clip. A line under 25
  characters is not judged alone: it follows the side. This applies only when
  the pair leaves the language open — a configured pair is your own statement
  about the deck, and is not second-guessed line by line. If the detection fails, the voice
  falls back to `speech_language` rather than staying silent.

  This is the one case where card auto-pronounce transmits text you did not
  select. Two switches already prevent it: set `source_language` to a real
  language, or turn `auto_pronounce_card` off.
* **Your region survives.** With `speech_language: de-AT` and a pair of
  `de → en`, the front is spoken in `de-AT`, not the bare `de` the pair is
  written in. `preferred_voice` works the same way — it names one specific
  voice, so it only applies to the side whose language it was chosen for.

Which side is "front" follows the card, not the note: on a reversed card the
prompt is the note's Back field, and the *Front voice* setting applies to it.

**A card laid out against the pair is checked, not assumed.** `auto` starts from
the pair — front is the source, back is the target — but that only holds for a
card built the way the pair describes. A reversed card puts the English on the
front, and the assumption is then exactly backwards. So when you press a
pronounce key on a side you have not pinned, the text is identified before it is
spoken, on a worker thread, cached, and only for a key you actually pressed.
Pinning a side to a real language skips that entirely and is taken at its word.

**Defaults:** `"auto"` and `"auto"`

### `expand_abbreviations`

Speak German grammatical abbreviations as full words. A speech engine reads
`Akk.` as three letters; this turns it into *Akkusativ*.

| On the card | Spoken |
| --- | --- |
| `Akk.` | Akkusativ |
| `Dat.` | Dativ |
| `Gen.` | Genitiv |
| `Nom.` | Nominativ |

So `warten auf + Akk.` is read as *"warten auf plus Akkusativ"*.

Matching is whole-word, so `Akku` (battery) and an already-written `Genitiv`
are left alone, and case does not matter. The trailing full stop is kept, which
gives a natural pause.

Only applied when `speech_language` is German — `Gen` is an ordinary English
word, and expanding it there would be wrong.

Also on the gear menu, as *Say Akk./Dat./Gen. in full*.

**Default:** `true`

### `show_examples`

Show real sentences using the selected word, with translations, so you can see
how it is actually used.

Examples come from [Tatoeba](https://tatoeba.org), an open corpus of
human-translated sentences (CC-BY 2.0 FR). They are looked up only for a word
or short phrase — up to 3 words, or 8 characters for unspaced Chinese — because
searching a corpus for a whole sentence returns nothing useful. With a source
of `auto`, the detected language from the translation is used.

Independent of your translation provider: no translation provider still offers
usage examples. If Tatoeba is unreachable or has no match, the translation is
shown on its own.

**Default:** `true`

### `tts_provider`

Where pronunciation audio comes from.

| Value | Behaviour |
| --- | --- |
| `auto` | Use an installed system voice if one matches; otherwise fetch audio online. |
| `system` | System voices only. Shows an error when none matches — nothing ever leaves your computer. |
| `google_unofficial` | Always fetch audio online, even if a system voice exists. |

**Why `google_unofficial` is the default:** it is the only setting under which
everything sounds the same. A card cannot use a system voice at all — Chromium
only lets the browser speak inside a user gesture, and a card appearing is not
one — so card audio is always online. Under `auto` a selection would find an
installed voice and a card would not, and the same word came out in two
different voices depending on how you asked for it. The online voice is also
the better one: the classic SAPI voices Anki can see are markedly more robotic.

There is a real cost, and it is the whole cost of this add-on's default
posture: **nothing is spoken offline any more**, and every pronunciation
reaches the same undocumented Google endpoint the translation backend uses,
which can rate-limit or break without notice. `voice_gender` and
`preferred_voice` also stop applying, because that endpoint offers one voice
per language.

Windows makes `system` less attractive than it sounds. Classic SAPI5/OneCore
voices are visible to every application, but Narrator **"natural voices"** —
the ones Settings pushes hardest — are reserved for Narrator and are *never*
registered as voice tokens. You can install German speech, have Windows list
it, and still have no German voice here.

When online audio is used the popup says **Spoken by Google (online voice)**,
so you always know the text left your computer. Audio is cached in
`user_files/tts/`, so repeating a card makes no further requests, and
`enable_google_unofficial: false` blocks any new ones outright.

Set this to `system` if you want pronunciation to stay strictly offline,
accepting that card auto-pronounce then stops entirely. `auto` sits between the
two: a system voice for selections when one exists, online for everything else.

Also on the gear menu, as *Voice source*.

**Default:** `google_unofficial`

### `cache_max_entries`

Maximum number of cached translations and example lookups, per cache table.
Once exceeded, the oldest are dropped. Use `0` for no limit.

**Default:** `5000`

### `tts_cache_max_mb`

Maximum size in megabytes of the cached pronunciation audio in
`user_files/tts/`. Once exceeded, the oldest clips are deleted. Use `0` for no
limit.

**Default:** `100`

### `enable_in_previewer`

Also show the popup in the card **previewer** — the window the browser opens
when you preview a card. The reviewer always has it.

Deliberately not offered in the card-layout/template editor or the note editor:
those are text-editing surfaces where a selection popup would fight with
typing.

**Default:** `true`

### `lookup_shortcut`

Keyboard shortcut that looks up the current selection, for when you have
already selected text and want the popup back after closing it.

Written as `Ctrl+Shift+T`, `Alt+D`, and so on. Set it to `""` to disable.
Choose something Anki does not already use — `Ctrl+Shift+T` is free in the
reviewer as of 25.09.4.

**Default:** `"Ctrl+Shift+T"`

### `pronounce_prompt_shortcut` / `pronounce_answer_shortcut`

Speak one side of the card you are reviewing, without selecting anything.

| Key | Speaks |
| --- | --- |
| `x` | the side you are shown — the front of a normal card |
| `c` | the side you are predicting — the back of a normal card |

On a reversed card the two swap round by themselves: each key follows the
card's own prompt and answer, not the note's Front and Back fields.

`c` stays silent until you have revealed the answer, so it cannot read out the
thing you are still trying to recall. Both accept the same spelling as
`lookup_shortcut` (`Alt+P`, `F8`, …) and `""` disables either one.

`card_speech_scope` applies here too: on `first-line` these speak only the
headword. If Sync, Edit, or More leaves focus outside the card, matching Qt
shortcuts keep the default online-capable modes working. Strict `system` mode
stays silent off-focus rather than sending text online; click the card to
restore its system-voice shortcut.

**Defaults:** `"x"` and `"c"`

### `stop_speech_shortcut`

Silences whatever is being spoken right now — a card that auto-pronounced
itself, a selection, or either of the keys above.

It stops that one clip and nothing else: the next card, and the next press of
`x` or `c`, speak as usual. There is no muted state to remember to undo.

**Default:** `"z"`

### `picker_languages`

Languages considered for the dropdowns when you click **DE** or **EN** in the
popup header. A list of language codes.

DeepL and LibreTranslate probe their `/languages` APIs in the background and
hide entries unsupported on that side. If the probe fails, this full list is
used. The source dropdown also offers `auto`; the current pair always remains
visible. The voice menus are not filtered because installed speech voices are
independent of translation-provider support.

`zh` means simplified Chinese by default. Use `zh-TW`, `zh-HK`, or `zh-HANT`
for traditional Chinese with DeepL.

**Default:** `["de", "en", "fr", "es", "it", "nl", "pt", "pl", "tr", "el", "ru", "zh"]`

### `speech_language`

Language tag used for pronunciation, e.g. `de-DE`, `de-AT`, `en-US`.
The add-on prefers an exactly matching voice, then any voice for the same base
language.

**Default:** `de-DE`

### `preferred_voice`

Exact name of a voice to use, e.g. `Microsoft Katja - German (Germany)`.
Leave empty to pick automatically from `speech_language`. If the named voice is
not installed, the add-on falls back to `speech_language` matching.

**Default:** `""` (empty)

### `speak_only_language`

Hold **automatic** pronunciation to one language. Empty — the default — speaks
everything.

A German deck whose backs are English definitions does not need the definition
read out: set `"de"` and only the German is spoken, whether it is a whole card
side or one line of a mixed one. It is also the answer to a language being
misidentified — an English line wrongly called German is simply not spoken,
rather than spoken wrongly.

Only automatic speech is filtered. Pressing **Pronounce**, or a pronounce key,
speaks whatever is there: asking out loud is the explicit answer to the
question this setting asks in general.

Regions count as their language, so `"de"` still allows a `de-AT` voice.

Also on the gear menu, as *Speak only*, with **All** at the top of the list.

**Default:** `""` (every language)

### `voice_gender`

Which voice to prefer when a language offers more than one: `female`, `male`,
or `any`.

The browser speech API does not report a voice's gender, so this is read from
the voice's name — Google's say so outright, Microsoft's are first names the
add-on knows a table of. A voice it cannot place counts as neither, and simply
loses the tie-break.

It is a preference, not a guarantee. A language with only one installed voice
speaks with that voice whichever gender it is, and online audio has a single
voice per language that cannot be chosen at all. To pin one exact voice, use
`preferred_voice`, which outranks this.

Also on the gear menu, as *Prefer a voice*.

**Default:** `"female"`

### `speech_rate`

Speaking speed. `1.0` is normal, `0.5` is half speed, `2.0` is double.
Allowed range: 0.1–10.

**Default:** `0.9`

### `theme`

Which palette the popup uses.

| Value | Meaning |
| --- | --- |
| `auto` | Follow Anki's own light/dark, switching live when you switch Anki's. |
| `dark` | Always dark, even on a light collection. |
| `light` | Always light, even in night mode. |

Only the popup and its menu are affected — the card behind them belongs to
Anki, and an add-on has no business restyling it.

Also on the gear menu, as *Theme*, with **Follow Anki** at the top.

**Default:** `"auto"`

### `popup_font_size`

Base font size of the popup in pixels. Allowed range: 8–40.

**Default:** `14`

### `debug_logging`

Write extra detail to the add-on log and the reviewer's JavaScript console.
API keys are never logged.

**Default:** `false`

---

### Pronunciation and Windows voices

With the default `tts_provider: "auto"`, pronunciation works with no setup —
it uses an installed system voice when one exists and fetches audio online
otherwise.

If you want it fully offline (`tts_provider: "system"`), you need a **classic**
voice, not a Narrator natural voice. In an **Administrator** PowerShell:

```powershell
Get-WindowsCapability -Online -Name "*de-DE*" | Select-Object Name, State
Add-WindowsCapability -Online -Name "Language.TextToSpeech~~~de-DE~0.0.1.0"
```

Then restart Anki. Adding the language in Settings, or adding a Narrator
"natural voice", does **not** make a voice available to Anki.

---

### Privacy

With the shipped defaults, selecting text transmits it immediately —
`auto_translate` sends it to your translation provider, `auto_pronounce` fetches
audio, and `show_examples` queries Tatoeba. Set those three to `false` for a
click-to-act popup that sends no selected text until you ask it to. DeepL and
LibreTranslate still probe their language-list endpoint when the reviewer opens
(the DeepL probe authenticates with your API key, but sends no card text).

The popup always says *Spoken by Google (online voice)* when audio came from
the network, and labels a fallback provider when one answered. **Copy** is
always local, and so is Pronounce when a system voice is used or
`tts_provider` is `system`.

* **DeepL** — text is sent over HTTPS to `api.deepl.com` (or
  `api-free.deepl.com` for free keys). DeepL states that API text is not used
  for model training and is deleted after translation. Check their current
  policy before sending sensitive material.
* **LibreTranslate** — text is sent to whichever endpoint you configure. Point
  it at a server you run yourself and no text leaves your network. Public
  instances are run by third parties whose logging you should verify.
* **Google (unofficial) — the default.** **Not a supported API.** It calls an
  undocumented endpoint intended for Google's own web widget. There is no
  service agreement, no rate-limit guarantee, and no stated retention policy
  for this use. It may stop working at any time, and using it may breach
  Google's Terms of Service. It is the default because it needs no signup;
  switch to `deepl` or a self-hosted `libretranslate` if you would rather rely
  on a supported API, and set `enable_google_unofficial` to `false` to block it
  entirely.
