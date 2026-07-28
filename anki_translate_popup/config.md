## Translate & Pronounce Popup — Configuration

Select text on a card while reviewing and a popup shows the translation, plus
real example sentences using the word. The header has a **translate**,
**speaker** and **clipboard** icon.

By default the lookup happens automatically on selection, which means the
selected text is transmitted as soon as you select it — see `auto_translate`
and `auto_pronounce` below to turn that off.

Changes take effect immediately — you do not need to restart Anki.

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

Safety switch for the unofficial Google provider. Set it to `false` to hard-
disable that backend — selecting it then produces a clear error instead of
sending anything. Useful if you want to guarantee no traffic ever reaches an
undocumented endpoint.

**Default:** `true` (because `google_unofficial` is the default provider)

### `request_timeout_seconds`

How long to wait for the provider before giving up. Allowed range: 1–120.

**Default:** `10`

### `cache_enabled`

Cache translations on disk so the same selection is never paid for twice.
The cache lives in `user_files/cache.sqlite` inside the add-on folder and
survives restarts and add-on updates. Delete that file to clear the cache.

**Default:** `true`

### `cache_lifetime_days`

How long a cached translation stays valid. Use `0` to keep entries forever.

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

### `show_examples`

Show real sentences using the selected word, with translations, so you can see
how it is actually used.

Examples come from [Tatoeba](https://tatoeba.org), an open corpus of
human-translated sentences (CC-BY 2.0 FR). They are looked up only for a word
or short phrase — up to 3 words — because searching a corpus for a whole
sentence returns nothing useful.

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

**Why `auto` is the default:** Windows 11 has two unrelated kinds of voice.
Classic SAPI5/OneCore voices are visible to every application. Narrator
**"natural voices"** — the ones Settings pushes hardest — are reserved for
Narrator and are *never* registered as voice tokens, so Anki's webview cannot
see them. You can install German speech, have Windows list it, and still have
no German voice available here. `auto` makes pronunciation work anyway.

When online audio is used, the popup says **Spoken by Google (online voice)**,
so you always know the text left your computer. Audio is cached in
`user_files/tts/`, so repeating a card makes no further requests.

Set this to `system` if you want pronunciation to stay strictly offline.

**Default:** `auto`

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

### `speech_rate`

Speaking speed. `1.0` is normal, `0.5` is half speed, `2.0` is double.
Allowed range: 0.1–10.

**Default:** `0.9`

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
click-to-act popup that sends nothing until you ask it to.

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
