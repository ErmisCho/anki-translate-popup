/*
 * Translate & Pronounce Popup - reviewer front-end.
 *
 * Security note: every value that originates outside this file (the user's
 * selection, translations coming back from a provider, error strings) is
 * written with `textContent` or `.value`, never `innerHTML`. The only
 * innerHTML assignment builds a constant skeleton with no interpolation, so
 * neither selected text nor a hostile provider response can inject markup or
 * script into the reviewer page.
 */
(function () {
    "use strict";

    var NS = "ankiTranslatePopup";
    if (globalThis[NS]) {
        return; // The reviewer page was rebuilt; keep the existing instance.
    }

    var BRIDGE = "anki_translate_popup:";

    var DEFAULTS = {
        sourceLanguage: "de",
        targetLanguage: "en",
        speechLanguage: "de-DE",
        ttsProvider: "google_unofficial",
        voiceGender: "female",
        preferredVoice: "",
        speechRate: 0.9,
        fontSize: 14,
        debug: false,
        autoTranslate: true,
        autoPronounce: true,
        autoPronounceCard: true,
        autoPronounceAnswer: false,
        expandAbbreviations: true,
        showExamples: true,
        lookupShortcut: "Ctrl+Shift+T",
        pronouncePromptShortcut: "x",
        pronounceAnswerShortcut: "c",
        stopSpeechShortcut: "z",
        frontSpeechLanguage: "auto",
        backSpeechLanguage: "auto",
        pickerLanguages: ["de", "en", "fr", "es", "it", "nl", "pt", "pl", "tr", "el", "ru", "zh"],
        sourcePickerLanguages: ["de", "en", "fr", "es", "it", "nl", "pt", "pl", "tr", "el", "ru", "zh"],
        targetPickerLanguages: ["de", "en", "fr", "es", "it", "nl", "pt", "pl", "tr", "el", "ru", "zh"],
    };

    var config = Object.assign({}, DEFAULTS, globalThis.ankiTranslatePopupConfig || {});

    var popup = null;
    var el = {};
    var selectedText = "";
    var lastTranslation = "";
    var lastRect = null;
    // The element whose picker is open, or null. Doubles as the "is a dropdown
    // open?" flag, which Escape needs so it closes the menu before the popup.
    var pickerTrigger = null;
    // Last language the provider actually reported, so a swap away from "auto"
    // has something concrete to make the new target.
    var detectedSource = "";
    // Set when Pronounce fired before the provider had named the language.
    var speakWhenDetected = false;
    var requestCounter = 0;
    var pendingRequestId = 0;
    var pendingSpeechId = 0;
    var pendingCopyId = 0;
    var onlineSpeechActive = false;
    var activeUtterance = null;
    var copyResetTimer = null;
    // Spoken text for the card on screen, pushed by Python as each side
    // appears. `answer` is empty until the answer is actually shown.
    var cardText = { prompt: "", promptLang: "", answer: "", answerLang: "" };

    function log() {
        if (!config.debug) {
            return;
        }
        var args = Array.prototype.slice.call(arguments);
        console.log.apply(console, ["[translate-popup]"].concat(args));
    }

    // -- popup construction ---------------------------------------------------

    /*
     * Inline SVG rather than emoji: QtWebEngine's emoji coverage depends on the
     * host font, whereas these draw identically everywhere and inherit the
     * popup's colour through `currentColor`, so they follow light/dark mode
     * with no extra rules.
     */
    var SVG_OPEN =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" ' +
        'aria-hidden="true" focusable="false"';

    // The conventional "languages" glyph, drawn in the same stroke weight as
    // the others so the three read as one set.
    var ICON_TRANSLATE =
        SVG_OPEN +
        ' class="atp-glyph">' +
        '<path d="m5 8 6 6"></path>' +
        '<path d="m4 14 6-6 2-3"></path>' +
        '<path d="M2 5h12"></path>' +
        '<path d="M7 2h1"></path>' +
        '<path d="m22 22-5-10-5 10"></path>' +
        '<path d="M14 18h6"></path>' +
        "</svg>";

    var ICON_SPEAKER =
        SVG_OPEN +
        ' class="atp-glyph">' +
        '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>' +
        '<path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>' +
        '<path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>' +
        "</svg>";

    var ICON_COPY =
        SVG_OPEN +
        ' class="atp-glyph atp-glyph--copy">' +
        '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>' +
        '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>' +
        "</svg>";

    var ICON_GEAR =
        SVG_OPEN +
        ' class="atp-glyph">' +
        '<circle cx="12" cy="12" r="3"></circle>' +
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06' +
        "a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09" +
        "A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83" +
        "l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09" +
        "A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83" +
        "l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09" +
        "a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83" +
        "l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09" +
        'a1.65 1.65 0 0 0-1.51 1z"></path>' +
        "</svg>";

    var ICON_CHECK =
        SVG_OPEN +
        ' class="atp-glyph atp-glyph--check">' +
        '<polyline points="20 6 9 17 4 12"></polyline>' +
        "</svg>";

    // Constant markup only. All dynamic values are assigned via textContent.
    var SKELETON = [
        '<div class="atp-header">',
        '  <span class="atp-langs">',
        '    <span class="atp-lang-source" tabindex="0" role="button"',
        '          aria-haspopup="listbox" aria-expanded="false"',
        '          title="Change source language" aria-label="Change source language"></span>',
        '    <span class="atp-lang-swap" tabindex="0" role="button"',
        '          title="Swap languages" aria-label="Swap languages">&rarr;</span>',
        '    <span class="atp-lang-target" tabindex="0" role="button"',
        '          aria-haspopup="listbox" aria-expanded="false"',
        '          title="Change target language" aria-label="Change target language"></span>',
        "  </span>",
        '  <div class="atp-actions">',
        '    <button type="button" class="atp-btn atp-translate"',
        '            title="Translate" aria-label="Translate">' + ICON_TRANSLATE + "</button>",
        '    <button type="button" class="atp-btn atp-pronounce"',
        '            title="Pronounce" aria-label="Pronounce">' + ICON_SPEAKER + "</button>",
        '    <button type="button" class="atp-btn atp-copy"',
        '            title="Copy" aria-label="Copy">' + ICON_COPY + ICON_CHECK + "</button>",
        '    <button type="button" class="atp-btn atp-settings" aria-haspopup="true"',
        '            aria-expanded="false" title="Settings"',
        '            aria-label="Settings">' + ICON_GEAR + "</button>",
        "  </div>",
        '  <button type="button" class="atp-close" title="Close (Esc)" aria-label="Close">&times;</button>',
        "</div>",
        '<div class="atp-result" hidden></div>',
        '<div class="atp-status" hidden></div>',
        '<div class="atp-examples" hidden></div>',
        // Inside the popup on purpose: the popup swallows mousedown/mouseup, so
        // a click in the dropdown must not look like a click on the card.
        '<div class="atp-menu" role="listbox" hidden></div>',
    ].join("");

    function build() {
        var root = document.createElement("div");
        root.className = "atp-popup";
        root.setAttribute("role", "dialog");
        root.setAttribute("aria-label", "Translate and pronounce");
        root.setAttribute("dir", "ltr");
        root.lang = "en";
        root.innerHTML = SKELETON;

        el = {
            langSource: root.querySelector(".atp-lang-source"),
            langSwap: root.querySelector(".atp-lang-swap"),
            langTarget: root.querySelector(".atp-lang-target"),
            menu: root.querySelector(".atp-menu"),
            close: root.querySelector(".atp-close"),
            result: root.querySelector(".atp-result"),
            status: root.querySelector(".atp-status"),
            examples: root.querySelector(".atp-examples"),
            translate: root.querySelector(".atp-translate"),
            pronounce: root.querySelector(".atp-pronounce"),
            copy: root.querySelector(".atp-copy"),
            settings: root.querySelector(".atp-settings"),
        };

        el.settings.addEventListener("click", function (event) {
            event.preventDefault();
            toggleSettings();
        });

        el.close.addEventListener("click", function (event) {
            event.preventDefault();
            hide();
        });
        el.translate.addEventListener("click", function (event) {
            event.preventDefault();
            requestTranslation();
        });
        el.pronounce.addEventListener("click", function (event) {
            event.preventDefault();
            pronounce();
        });
        el.copy.addEventListener("click", function (event) {
            event.preventDefault();
            copyToClipboard();
        });

        onActivate(el.langSource, function () {
            togglePicker("source", el.langSource);
        });
        onActivate(el.langTarget, function () {
            togglePicker("target", el.langTarget);
        });
        onActivate(el.langSwap, function () {
            closePicker();
            swapLanguages();
        });

        // Selecting inside the popup must not re-trigger the selection flow.
        root.addEventListener("mousedown", function (event) {
            event.stopPropagation();
            // A click elsewhere in the popup dismisses an open dropdown, but
            // clicking its own trigger has to reach the toggle below.
            if (
                pickerTrigger &&
                !el.menu.contains(event.target) &&
                !pickerTrigger.contains(event.target)
            ) {
                closePicker();
            }
        });
        root.addEventListener("mouseup", function (event) {
            event.stopPropagation();
        });

        document.body.appendChild(root);
        return root;
    }

    function applyFontSize() {
        var size = Number(config.fontSize);
        if (!isFinite(size) || size <= 0) {
            size = DEFAULTS.fontSize;
        }
        popup.style.setProperty("--atp-font-size", size + "px");
    }

    // -- state helpers --------------------------------------------------------

    function setStatus(message, kind) {
        if (!el.status) {
            return; // spoken from a shortcut with no popup open: nowhere to report
        }
        if (!message) {
            el.status.hidden = true;
            el.status.textContent = "";
            el.status.className = "atp-status";
            return;
        }
        el.status.textContent = message; // escaped by assignment
        el.status.className = "atp-status atp-status--" + (kind || "info");
        el.status.hidden = false;
    }

    function setResult(text) {
        lastTranslation = text || "";
        if (!lastTranslation) {
            el.result.hidden = true;
            el.result.textContent = "";
            return;
        }
        el.result.textContent = lastTranslation; // escaped by assignment
        el.result.hidden = false;
    }

    function setLanguages(source, target) {
        el.langSource.textContent = sourceLabel(source);
        el.langTarget.textContent = languageLabel(target);
    }

    /**
     * "AUTO" stays on the header while auto is configured, with what was
     * detected beside it: the setting is sticky, the detection is per selection,
     * and a header that simply read "DE" looked as though the pair had changed.
     */
    function sourceLabel(source) {
        if (String(source == null ? "" : source).toLowerCase() !== "auto") {
            return languageLabel(source);
        }
        return detectedSource ? "AUTO·" + languageLabel(detectedSource) : "AUTO";
    }

    // -- language pair --------------------------------------------------------

    function languageLabel(code) {
        return String(code == null ? "" : code).toUpperCase();
    }

    /** "en-GB" -> "en". Every "same language?" comparison goes through here. */
    function baseLanguage(code) {
        return String(code == null ? "" : code)
            .trim()
            .replace("_", "-")
            .split("-")[0]
            .toLowerCase();
    }

    /** Enter and Space must do what a click does on the role="button" spans. */
    function onActivate(node, handler) {
        node.addEventListener("click", function (event) {
            event.preventDefault();
            handler();
        });
        node.addEventListener("keydown", function (event) {
            if (event.key !== "Enter" && event.key !== " " && event.key !== "Spacebar") {
                return; // never swallow another key
            }
            event.preventDefault();
            handler();
        });
    }

    /**
     * Codes offered for one side of the pair: the configured list, plus the
     * current value so it is always selectable, plus "auto" for the source
     * only - "auto" as a target is not a valid configuration.
     */
    function languageOptions(which) {
        var configured =
            which === "source"
                ? config.sourcePickerLanguages
                : which === "target"
                  ? config.targetPickerLanguages
                  : config.pickerLanguages;
        var current =
            which === "source"
                ? config.sourceLanguage
                : which === "target"
                  ? config.targetLanguage
                  : "";
        var wanted = (which === "source" ? ["auto"] : []).concat(
            Array.isArray(configured) ? configured : [],
            current ? [current] : []
        );
        var seen = Object.create(null);
        var out = [];
        wanted.forEach(function (value) {
            var code = String(value == null ? "" : value).trim().toLowerCase();
            if (!code || seen[code]) {
                return;
            }
            if (code === "auto" && which !== "source") {
                return;
            }
            seen[code] = true;
            out.push(code);
        });
        return out;
    }

    function togglePicker(which, trigger) {
        if (pickerTrigger === trigger) {
            closePicker();
            return;
        }
        openPicker(which, trigger);
    }

    function openPicker(which, trigger) {
        closePicker();
        var current = String(
            which === "source" ? config.sourceLanguage : config.targetLanguage
        ).toLowerCase();

        el.menu.textContent = "";
        el.menu.className = "atp-menu"; // drop the settings menu's full height
        clearMenuHeightOverride();
        el.menu.setAttribute("role", "listbox"); // the settings menu sets "menu"
        languageOptions(which).forEach(function (code) {
            var item = document.createElement("div");
            item.className = "atp-menu-item";
            item.setAttribute("role", "option");
            item.setAttribute("aria-selected", code === current ? "true" : "false");
            item.tabIndex = 0;
            item.textContent = code === "auto" ? "Auto" : languageLabel(code);
            onActivate(item, function () {
                closePicker();
                if (which === "source") {
                    applyLanguages(code, config.targetLanguage);
                } else {
                    applyLanguages(config.sourceLanguage, code);
                }
            });
            el.menu.appendChild(item);
        });

        // Anchored under its own trigger; the popup is positioned, so these
        // offsets are already relative to it.
        el.menu.style.left = trigger.offsetLeft + "px";
        el.menu.style.top = trigger.offsetTop + trigger.offsetHeight + 4 + "px";
        el.menu.hidden = false;
        trigger.setAttribute("aria-expanded", "true");
        pickerTrigger = trigger;
    }

    function closePicker() {
        if (!pickerTrigger) {
            return;
        }
        var trigger = pickerTrigger;
        pickerTrigger = null;
        var focusWasInside = !!document.activeElement && el.menu.contains(document.activeElement);
        el.menu.hidden = true;
        el.menu.textContent = "";
        trigger.setAttribute("aria-expanded", "false");
        if (focusWasInside) {
            trigger.focus();
        }
    }

    function isPickerOpen() {
        return !!pickerTrigger;
    }

    // -- settings menu --------------------------------------------------------

    /*
     * Each entry maps the webview's camelCase config field to the snake_case
     * key Python stores. Python re-checks the key against its own allowlist, so
     * a wrong name here is refused rather than written.
     */
    var SETTING_ITEMS = [
        { key: "auto_translate", field: "autoTranslate", label: "Translate on selection" },
        { key: "auto_pronounce", field: "autoPronounce", label: "Speak on selection" },
        { key: "auto_pronounce_card", field: "autoPronounceCard", label: "Speak the card as it appears" },
        { key: "auto_pronounce_answer", field: "autoPronounceAnswer", label: "Also speak the answer" },
        { key: "expand_abbreviations", field: "expandAbbreviations", label: "Say Akk./Dat./Gen. in full" },
        { key: "show_examples", field: "showExamples", label: "Show example sentences" },
    ];

    /*
     * The two voice languages. Not toggles: each opens a language list in the
     * same menu. "Auto" follows the translation pair, which is what a deck
     * already declares - the front is the source language, the back the target.
     */
    var VOICE_ITEMS = [
        { key: "front_speech_language", field: "frontSpeechLanguage", label: "Voice for the front" },
        { key: "back_speech_language", field: "backSpeechLanguage", label: "Voice for the back" },
        {
            key: "tts_provider",
            field: "ttsProvider",
            label: "Voice source",
            options: ["google_unofficial", "auto", "system"],
            names: {
                google_unofficial: "Online",
                auto: "System, else online",
                system: "System only",
            },
        },
        {
            key: "voice_gender",
            field: "voiceGender",
            label: "Prefer a voice",
            options: ["female", "male", "any"],
            names: { female: "Female", male: "Male", any: "Any" },
        },
    ];

    /** The menu element is shared, so a height forced onto one must not outlive it. */
    function clearMenuHeightOverride() {
        el.menu.style.maxHeight = "";
        el.menu.style.overflowY = "";
    }

    /**
     * Drop an open menu above its trigger when it would otherwise run off the
     * bottom of the window - the same flip the popup performs for a selection
     * near the bottom edge. Only when there is room above: a menu taller than
     * the window scrolls instead, which beats one whose top is unreachable.
     */
    function keepMenuOnScreen(trigger) {
        var margin = 4;
        clearMenuHeightOverride(); // measure the menu at its natural height
        if (el.menu.getBoundingClientRect().bottom <= globalThis.innerHeight - margin) {
            return;
        }
        var below = el.menu.style.top;
        el.menu.style.top = trigger.offsetTop - el.menu.offsetHeight - margin + "px";
        if (el.menu.getBoundingClientRect().top < margin) {
            el.menu.style.top = below; // no room either way
            el.menu.style.maxHeight =
                globalThis.innerHeight - el.menu.getBoundingClientRect().top - margin + "px";
            el.menu.style.overflowY = "auto";
        }
    }

    function toggleSettings() {
        if (pickerTrigger === el.settings) {
            closePicker();
            return;
        }
        openSettings();
    }

    /** A row's value as shown: its own wording where it has some, else a code. */
    function voiceLabel(code, item) {
        if (item && item.names && item.names[code]) {
            return item.names[code];
        }
        return code === "auto" || !code ? "Auto" : languageLabel(code);
    }

    /** A row offering a fixed set of choices lists those; the rest list languages. */
    function voiceOptions(item, current) {
        if (item.options) {
            return item.options.slice();
        }
        var options = ["auto"].concat(languageOptions("voice"));
        if (current !== "auto" && options.indexOf(current) === -1) {
            options.push(current); // never hide the value that is actually set
        }
        return options;
    }

    /**
     * Replace the gear menu with the language list for one side. The menu is a
     * single element, so this is a replacement rather than a nested submenu -
     * picking a language or pressing Escape returns to the settings list.
     */
    function openVoicePicker(voice) {
        var fallback = voice.options ? voice.options[0] : "auto";
        var current = String(config[voice.field] || fallback).toLowerCase();
        el.menu.textContent = "";
        el.menu.className = "atp-menu"; // a language list scrolls, unlike the settings
        el.menu.setAttribute("role", "listbox");

        voiceOptions(voice, current).forEach(function (code) {
            var item = document.createElement("div");
            item.className = "atp-menu-item";
            item.setAttribute("role", "option");
            item.setAttribute("aria-selected", code === current ? "true" : "false");
            item.tabIndex = 0;
            item.textContent = voiceLabel(code, voice);
            onActivate(item, function () {
                config[voice.field] = code;
                if (typeof pycmd === "function") {
                    pycmd(
                        BRIDGE + "set_option:" +
                        JSON.stringify({ key: voice.key, value: code })
                    );
                }
                openSettings(); // back to the list the user came from
            });
            el.menu.appendChild(item);
        });

        el.menu.hidden = false;
        pickerTrigger = el.settings;
    }

    function openSettings() {
        closePicker();
        el.menu.textContent = "";
        // Every switch visible at once: this list is short and fixed, unlike a
        // language list, and a settings menu you have to scroll hides settings.
        el.menu.className = "atp-menu atp-menu-settings";
        el.menu.setAttribute("role", "menu");

        SETTING_ITEMS.forEach(function (setting) {
            var item = document.createElement("div");
            item.className = "atp-menu-item atp-menu-toggle";
            item.setAttribute("role", "menuitemcheckbox");
            item.tabIndex = 0;

            var tick = document.createElement("span");
            tick.className = "atp-toggle-tick";
            var label = document.createElement("span");
            label.className = "atp-toggle-label";
            label.textContent = setting.label;
            item.appendChild(tick);
            item.appendChild(label);

            function render() {
                var on = !!config[setting.field];
                // A tick glyph rather than a checkbox: no form control to
                // inherit a card's input styling.
                tick.textContent = on ? "✓" : "";
                item.setAttribute("aria-checked", on ? "true" : "false");
            }
            render();

            onActivate(item, function () {
                config[setting.field] = !config[setting.field];
                render();
                if (typeof pycmd === "function") {
                    pycmd(
                        BRIDGE + "set_option:" +
                        JSON.stringify({ key: setting.key, value: !!config[setting.field] })
                    );
                }
                // Deliberately stays open: flipping two switches is common.
            });
            el.menu.appendChild(item);
        });

        VOICE_ITEMS.forEach(function (voice) {
            var item = document.createElement("div");
            item.className = "atp-menu-item atp-menu-voice";
            item.setAttribute("role", "menuitem");
            item.tabIndex = 0;

            var label = document.createElement("span");
            label.className = "atp-toggle-label";
            label.textContent = voice.label;
            var value = document.createElement("span");
            value.className = "atp-voice-value";
            value.textContent = voiceLabel(config[voice.field], voice);
            item.appendChild(label);
            item.appendChild(value);

            onActivate(item, function () {
                openVoicePicker(voice);
            });
            el.menu.appendChild(item);
        });

        el.menu.hidden = false;
        // Right-aligned under the gear, then clamped so a wide menu opened from
        // the rightmost button cannot hang outside the popup.
        var left = el.settings.offsetLeft + el.settings.offsetWidth - el.menu.offsetWidth;
        el.menu.style.left = Math.max(0, Math.min(left, popup.clientWidth - el.menu.offsetWidth)) + "px";
        el.menu.style.top = el.settings.offsetTop + el.settings.offsetHeight + 4 + "px";
        keepMenuOnScreen(el.settings);
        el.settings.setAttribute("aria-expanded", "true");
        pickerTrigger = el.settings;
    }

    /**
     * Adopt a pair, persist it, and look the selection up again. The old
     * answer is dropped first: a stale translation under a new language pair
     * would read as a genuine result.
     */
    function applyLanguages(source, target) {
        config.sourceLanguage = source;
        config.targetLanguage = target;
        setLanguages(source, target);
        setResult("");
        setExamples(null);
        setStatus("");
        if (typeof pycmd === "function") {
            pycmd(
                BRIDGE + "set_languages:" + JSON.stringify({ source: source, target: target })
            );
        }
        requestTranslation();
        reposition();
        log("languages set to", source, "->", target);
    }

    function swapLanguages() {
        var source = config.sourceLanguage;
        var target = config.targetLanguage;
        if (source !== "auto") {
            applyLanguages(target, source);
            return;
        }
        // "auto" cannot become a target, so it is resolved to whatever the
        // provider last reported. Before the first translation nothing is
        // known, so the source stays automatic rather than becoming invalid.
        if (!detectedSource || detectedSource === "auto") {
            applyLanguages("auto", target);
            return;
        }
        applyLanguages(target, detectedSource);
    }

    /**
     * Render usage examples.
     *
     * Built with createElement/textContent rather than markup: these sentences
     * come from a third-party corpus, and this keeps them un-parseable as HTML.
     */
    function setExamples(list) {
        el.examples.textContent = "";
        if (!list || !list.length) {
            el.examples.hidden = true;
            return;
        }

        var heading = document.createElement("div");
        heading.className = "atp-examples-title";
        heading.textContent = "Examples · Tatoeba"; // inline CC-BY attribution
        el.examples.appendChild(heading);

        list.forEach(function (example) {
            if (!example || !example.text) {
                return;
            }
            var item = document.createElement("div");
            item.className = "atp-example";

            var original = document.createElement("div");
            original.className = "atp-example-src";
            original.textContent = example.text;
            item.appendChild(original);

            if (example.translation) {
                var translated = document.createElement("div");
                translated.className = "atp-example-tr";
                translated.textContent = example.translation;
                item.appendChild(translated);
            }
            el.examples.appendChild(item);
        });
        el.examples.hidden = false;
    }

    function setBusy(busy) {
        el.translate.disabled = busy;
        popup.classList.toggle("atp-busy", !!busy);
    }

    // -- show / hide ----------------------------------------------------------

    function show(text, rect) {
        if (!popup) {
            popup = build();
        }
        applyFontSize();

        selectedText = text;
        pendingRequestId = 0;
        // A detection belongs to the selection it was made for. Keeping it would
        // read the next selection in the last one's language.
        detectedSource = "";
        speakWhenDetected = false;
        closePicker();
        setResult("");
        setStatus("");
        setExamples(null);
        setBusy(false);
        setLanguages(config.sourceLanguage, config.targetLanguage);
        clearTimeout(copyResetTimer);
        el.copy.classList.remove("atp-copied");
        el.copy.title = "Copy";

        popup.hidden = false;
        popup.classList.add("atp-visible");
        position(rect);
        log("shown for", text);

        // The popup no longer echoes the selection back - it is already
        // highlighted on the card - so it opens straight into the answer.
        if (config.autoTranslate) {
            requestTranslation();
        }
        if (config.autoPronounce) {
            pronounce();
        }
    }

    /**
     * True while the language of this selection is still unknown and on its way.
     *
     * Only "auto" needs this: any other source is already the answer. Speaking
     * before the provider replies would use the *previous* selection's language,
     * which is how a German word and the English one after it both came out in
     * German.
     */
    function awaitingDetection() {
        return config.sourceLanguage === "auto" && !detectedSource && !!pendingRequestId;
    }

    function hide() {
        if (!popup || popup.hidden) {
            return;
        }
        stopSpeech();
        closePicker();
        pendingRequestId = 0;
        popup.hidden = true;
        popup.classList.remove("atp-visible");
    }

    function isOpen() {
        return !!popup && !popup.hidden;
    }

    /** Re-anchor to the remembered selection after the content changed size. */
    function reposition() {
        if (isOpen() && lastRect) {
            position(lastRect);
        }
    }

    /** Place the popup near `rect`, fully inside the visible reviewer area. */
    function position(rect) {
        lastRect = rect;
        var margin = 8;
        var box = popup.getBoundingClientRect();
        var viewportWidth = document.documentElement.clientWidth;
        var viewportHeight = document.documentElement.clientHeight;

        var left = rect.left + rect.width / 2 - box.width / 2;
        left = Math.max(margin, Math.min(left, viewportWidth - box.width - margin));

        // Prefer below the selection; flip above when there is no room.
        var top = rect.bottom + margin;
        if (top + box.height > viewportHeight - margin) {
            var above = rect.top - box.height - margin;
            top = above >= margin ? above : Math.max(margin, viewportHeight - box.height - margin);
        }

        popup.style.left = Math.round(left) + "px";
        popup.style.top = Math.round(top) + "px";
    }

    // -- translation ----------------------------------------------------------

    function requestTranslation() {
        if (!selectedText) {
            return;
        }
        if (typeof pycmd !== "function") {
            setStatus("Anki's JavaScript bridge is unavailable. Restart Anki.", "error");
            return;
        }

        requestCounter += 1;
        pendingRequestId = requestCounter;
        setBusy(true);
        setResult("");
        setStatus("Translating…", "loading");

        // Text leaves the machine only from here - never on selection alone.
        pycmd(
            BRIDGE +
                "translate:" +
                JSON.stringify({ id: pendingRequestId, text: selectedText })
        );
    }

    var PROVIDER_LABELS = {
        deepl: "DeepL",
        libretranslate: "LibreTranslate",
        google_unofficial: "Google",
    };

    function providerLabel(name) {
        return PROVIDER_LABELS[name] || String(name);
    }

    /** Called from Python via web.eval once a translation finishes or fails. */
    function onTranslationResponse(payload) {
        if (!payload || payload.id !== pendingRequestId) {
            log("ignoring stale response", payload && payload.id, "expected", pendingRequestId);
            return;
        }
        pendingRequestId = 0;
        setBusy(false);

        if (payload.ok) {
            // Name the backend whenever it is not the configured one: the user
            // must never be left guessing which service received their text.
            var notes = [];
            if (payload.usedFallback && payload.provider) {
                notes.push("via " + providerLabel(payload.provider) + " (fallback)");
            }
            if (payload.cached) {
                notes.push("from cache");
            }
            setStatus(notes.join(" · "), "info");
            // Remember the resolved source: with "auto" configured this is the
            // only place the real language is ever named, and a swap needs it.
            if (payload.sourceLang && payload.sourceLang !== "auto") {
                detectedSource = String(payload.sourceLang);
            }
            setLanguages(config.sourceLanguage, payload.targetLang);
            setResult(payload.text);
            setExamples(payload.examples);
        } else {
            setResult("");
            setExamples(null);
            setStatus(payload.error || "Translation failed.", "error");
        }
        // Speech held back for the language now has it - or knows it never
        // arrived, in which case it falls back rather than staying silent.
        if (speakWhenDetected) {
            speakWhenDetected = false;
            pronounce();
        }
        // The popup was placed while empty; it is much taller now, so it has to
        // be re-anchored or a selection near the bottom pushes it off-screen.
        reposition();
    }

    /** Called from Python when the user edits the add-on configuration. */
    function onConfigChanged(next) {
        config = Object.assign({}, DEFAULTS, next || {});
        shortcut = parseShortcut(config.lookupShortcut);
        promptShortcut = parseShortcut(config.pronouncePromptShortcut);
        answerShortcut = parseShortcut(config.pronounceAnswerShortcut);
        stopShortcut = parseShortcut(config.stopSpeechShortcut);
        if (popup) {
            applyFontSize();
            if (isOpen() && !lastTranslation) {
                setLanguages(config.sourceLanguage, config.targetLanguage);
            }
        }
        log("config updated", config);
    }

    /** Called from Python each time a card side is shown, and on request. */
    function onCardText(next) {
        // A side has appeared, so anything still being said belongs to the card
        // before it. Only the page's own speech is cancelled: Python is queueing
        // this card's audio as we speak, and clearing the queue would take that
        // with it.
        stopBrowserSpeech();
        cardText = {
            prompt: (next && next.prompt) || "",
            promptLang: (next && next.promptLang) || "",
            answer: (next && next.answer) || "",
            answerLang: (next && next.answerLang) || "",
        };
        log("card text", cardText);

        // Answering a request made because a key was pressed with nothing to
        // say. Speak straight from here rather than calling speakCardSide
        // again, which would ask a second time and never stop.
        var wanted = (next && next.speak) || "";
        if (!wanted) {
            return;
        }
        var side = cardSide(wanted);
        if (side.text) {
            speakText(side.text, side.lang);
        } else {
            log("nothing to speak for the", wanted, "side");
        }
    }

    // -- pronunciation --------------------------------------------------------

    /**
     * Cancel only what the page itself is saying. Anki's audio queue is left
     * alone, which matters while it is mid-way through a card's own [sound:].
     */
    function stopBrowserSpeech() {
        if (globalThis.speechSynthesis) {
            globalThis.speechSynthesis.cancel();
        }
        activeUtterance = null;
        pendingSpeechId = 0;
        // Also cancels speech that is only waiting for a language: stopping
        // means stopping, and a closed popup must not speak on a late reply.
        speakWhenDetected = false;
    }

    /** Closing the popup silences what the popup started, and nothing else. */
    function stopSpeech() {
        stopBrowserSpeech();
        // Only reach across the bridge if the popup's own online audio could
        // actually be playing: a card's [sound:] is not the popup's to cancel.
        if (onlineSpeechActive && typeof pycmd === "function") {
            onlineSpeechActive = false;
            pycmd(BRIDGE + "stop_speech:");
        }
    }

    /**
     * Silence everything, whoever started it: the stop key, and every new
     * pronunciation.
     *
     * Unconditional where stopSpeech is not, because card auto-pronounce is
     * queued by Python through av_player without the page ever hearing about
     * it - onlineSpeechActive is false for exactly the audio most likely to be
     * playing underneath. The cost is that a card's own [sound:] is cut off
     * too, which is the point: one pronunciation at a time.
     */
    function stopAllSpeech() {
        stopBrowserSpeech();
        onlineSpeechActive = false;
        if (typeof pycmd === "function") {
            pycmd(BRIDGE + "stop_speech:");
        }
    }

    /**
     * Resolve the voice list. QtWebEngine populates it asynchronously - it was
     * still empty ~3s after page load in Anki 25.09 on Windows - so wait for
     * `voiceschanged` instead of trusting the first synchronous call.
     *
     * This is also why `warmVoices()` runs at startup: `speak()` needs a
     * transient user activation, which Chromium expires a few seconds after
     * the click. Waiting for a cold voice list inside the click handler can
     * outlive that window and fail with "not-allowed", so the list must
     * already be warm by the time the user presses Pronounce.
     */
    function loadVoices(timeoutMs) {
        return new Promise(function (resolve) {
            var synth = globalThis.speechSynthesis;
            if (!synth) {
                resolve([]);
                return;
            }
            var voices = synth.getVoices();
            if (voices && voices.length) {
                resolve(voices);
                return;
            }

            var settled = false;
            function finish() {
                if (settled) {
                    return;
                }
                settled = true;
                synth.removeEventListener("voiceschanged", onChange);
                clearTimeout(timer);
                clearInterval(poll);
                resolve(synth.getVoices() || []);
            }
            function onChange() {
                finish();
            }

            synth.addEventListener("voiceschanged", onChange);
            // Belt and braces: some builds never fire the event.
            var poll = setInterval(function () {
                var current = synth.getVoices();
                if (current && current.length) {
                    finish();
                }
            }, 250);
            var timer = setTimeout(finish, timeoutMs || 3000);
        });
    }

    /** Start voice enumeration now so the Pronounce click never has to wait. */
    function warmVoices() {
        if (!globalThis.speechSynthesis) {
            return;
        }
        loadVoices(10000).then(function (voices) {
            log("voices ready:", voices.length);
        });
    }

    /** Exact preferred name > exact locale > same base language > none. */
    /*
     * The Web Speech API exposes no gender, so it is read off the name. Google's
     * voices say so outright ("Google UK English Female"); Microsoft's are first
     * names, which is what the tables are for.
     *
     * ponytail: a name table only knows the voices in it - an unlisted voice
     * counts as neither gender and simply loses the tie-break. Extend it when
     * one turns up, or name the voice outright with preferred_voice.
     */
    var FEMALE_VOICE_NAMES = [
        "zira", "hazel", "susan", "linda", "heera", "catherine", "eva", "michelle",
        "katja", "hedda", "marlene", "hortense", "julie", "helena", "laura",
        "sabina", "elsa", "hanna", "maria", "helia", "paulina", "irina",
        "huihui", "yaoyao", "tracy", "melina",
    ];
    var MALE_VOICE_NAMES = [
        "david", "mark", "james", "george", "ravi", "richard", "sean", "guy",
        "stefan", "paul", "pablo", "raul", "cosimo", "frank", "daniel", "adam",
        "tolga", "pavel", "kangkang", "stefanos", "nestoras",
    ];

    /** "female", "male", or "" when the name says nothing either way. */
    function voiceGenderOf(voice) {
        var name = String((voice && voice.name) || "").toLowerCase();
        // Before the "male" test: "female" contains it.
        if (name.indexOf("female") !== -1) {
            return "female";
        }
        if (name.indexOf("male") !== -1) {
            return "male";
        }
        var words = name.split(/[^a-zà-ÿ]+/);
        for (var i = 0; i < words.length; i++) {
            if (FEMALE_VOICE_NAMES.indexOf(words[i]) !== -1) {
                return "female";
            }
            if (MALE_VOICE_NAMES.indexOf(words[i]) !== -1) {
                return "male";
            }
        }
        return "";
    }

    function normaliseLang(code) {
        return String(code || "").toLowerCase().replace("_", "-");
    }

    /**
     * The best voice for a language, chosen the same way every time.
     *
     * The old version returned the first match, so enumeration order decided
     * which voice spoke - the same word could come out male, then female. Every
     * candidate is now scored and ties break on the name, which is stable.
     */
    function pickVoice(voices, wantedLang, preferredName, gender) {
        if (!voices || !voices.length) {
            return null;
        }
        var i;
        if (preferredName) {
            // An explicitly named voice outranks every preference.
            var wantedName = preferredName.toLowerCase();
            for (i = 0; i < voices.length; i++) {
                if (String(voices[i].name).toLowerCase() === wantedName) {
                    return voices[i];
                }
            }
        }
        var lang = normaliseLang(wantedLang);
        var base = lang.split("-")[0];
        var wanted = gender || "any";
        var best = null;
        var bestScore = -1;
        for (i = 0; i < voices.length; i++) {
            var voice = voices[i];
            var voiceLang = normaliseLang(voice.lang);
            if (voiceLang.split("-")[0] !== base) {
                continue; // wrong language: never traded away for a gender
            }
            // Region beats gender: an en-GB request wants a British voice more
            // than it wants a female one.
            var score =
                (voiceLang === lang ? 2 : 0) +
                (wanted === "any" || voiceGenderOf(voice) === wanted ? 1 : 0);
            if (score > bestScore || (score === bestScore && best && voice.name < best.name)) {
                best = voice;
                bestScore = score;
            }
        }
        return best;
    }

    /*
     * German vocabulary cards are full of "Akk.", "Dat.", "Gen." - a speech
     * engine reads those as letters, so expand them to the words. Mirrors
     * expand_german_abbreviations() in __init__.py, which handles the online
     * voice path; this one covers the system voice.
     *
     * Word-bounded, so "Akku" (battery) and an already-written "Genitiv" are
     * both left alone.
     */
    var GERMAN_ABBREVIATIONS = {
        akk: "Akkusativ",
        dat: "Dativ",
        gen: "Genitiv",
        nom: "Nominativ",
    };
    var ABBREVIATION_RE = /\b(akk|dat|gen|nom)\b/gi;

    function prepareSpeechText(text, lang) {
        // Only for German: "Gen" is an English word, and expanding it there
        // would be wrong - which is what an English answer side would get if
        // this looked at the global speechLanguage instead of its own.
        if (!config.expandAbbreviations) {
            return text;
        }
        if (String(lang || config.speechLanguage || "").toLowerCase().indexOf("de") !== 0) {
            return text;
        }
        return text.replace(ABBREVIATION_RE, function (match) {
            return GERMAN_ABBREVIATIONS[match.toLowerCase()];
        });
    }

    /** Ask Python to synthesise and play the audio. */
    function speakOnline(text, lang) {
        if (typeof pycmd !== "function") {
            setStatus("Anki's JavaScript bridge is unavailable. Restart Anki.", "error");
            return;
        }
        requestCounter += 1;
        pendingSpeechId = requestCounter;
        onlineSpeechActive = true;
        setStatus("Fetching audio…", "loading");
        pycmd(
            BRIDGE + "speak:" +
            JSON.stringify({ id: pendingSpeechId, text: text, lang: lang || "" })
        );
    }

    /** Called from Python via web.eval once audio starts or fails. */
    function onSpeechResponse(payload) {
        if (!payload || payload.id !== pendingSpeechId) {
            return; // superseded by a newer request
        }
        pendingSpeechId = 0;
        if (payload.ok) {
            // Name the source: with an online voice the text left the machine.
            setStatus("Spoken by Google (online voice)", "info");
        } else {
            setStatus(payload.error || "Pronunciation failed.", "error");
        }
    }

    function pronounce() {
        if (awaitingDetection()) {
            // Not a delay for its own sake: the language is seconds away and
            // speaking now would use the previous selection's.
            speakWhenDetected = true;
            setStatus("Detecting language…", "loading");
            return;
        }
        speakText(selectedText, selectionSpeechLanguage());
    }

    /**
     * Which language the selection is spoken in.
     *
     * The pair is what says the selection is German or English; speech_language
     * is a single global that knows nothing about the deck in front of you, so
     * reading the selection with it gives an EN -> EN pair a German voice.
     *
     * The configured language still wins when it is the same language, so a
     * user who asked for de-AT keeps de-AT rather than the bare "de" a pair is
     * written in. This mirrors AddonConfig.speech_language_for, which applies
     * the same rule to the card sides; it is repeated here rather than pushed
     * from Python because the header can change the pair between two keystrokes
     * and a round trip would speak with the previous language.
     */
    function selectionSpeechLanguage() {
        var source = config.sourceLanguage;
        if (source === "auto") {
            source = detectedSource; // whatever the provider last reported
        }
        if (!source || source === "auto") {
            return config.speechLanguage; // nothing translated yet, nothing known
        }
        return baseLanguage(source) === baseLanguage(config.speechLanguage)
            ? config.speechLanguage
            : source;
    }

    /**
     * Speak arbitrary text in a given language: the selection from the popup,
     * or a card side from the pronounce shortcuts. Both go through here so a
     * card side gets the same voice, rate and online fallback the Pronounce
     * button already has - only the language differs.
     */
    function speakText(text, lang) {
        if (!text) {
            return;
        }
        lang = lang || config.speechLanguage;

        // Never overlap two pronunciations - including one Python queued for the
        // card, which the page is otherwise unaware of.
        stopAllSpeech();

        var mode = config.ttsProvider || DEFAULTS.ttsProvider;
        if (mode === "google_unofficial") {
            speakOnline(text, lang);
            return;
        }

        var synth = globalThis.speechSynthesis;
        if (!synth || typeof globalThis.SpeechSynthesisUtterance !== "function") {
            if (mode === "auto") {
                speakOnline(text, lang);
                return;
            }
            setStatus(
                "Speech synthesis is not available in this Anki build. " +
                    "Pronunciation cannot be used.",
                "error"
            );
            return;
        }

        setStatus("Preparing speech…", "loading");

        loadVoices(6000).then(function (voices) {
            // preferredVoice names one specific voice, so it only applies to
            // the language it was chosen for - never to the other card side.
            var preferred =
                baseLanguage(lang) === baseLanguage(config.speechLanguage)
                    ? config.preferredVoice
                    : "";
            var voice = pickVoice(voices, lang, preferred, config.voiceGender);
            if (!voice) {
                // Windows may report the language as installed while exposing
                // no usable voice (Narrator-only "natural voices" do this), so
                // "auto" quietly goes online rather than dead-ending.
                if (mode === "auto") {
                    speakOnline(text, lang);
                    return;
                }
                setStatus(voiceMissingMessage(voices, lang), "error");
                log("no voice for", lang);
                return;
            }

            // Always the original text, never the translation.
            var utterance = new globalThis.SpeechSynthesisUtterance(
                prepareSpeechText(text, lang)
            );
            utterance.voice = voice;
            utterance.lang = voice.lang || lang;
            var rate = Number(config.speechRate);
            utterance.rate = isFinite(rate) && rate > 0 ? rate : DEFAULTS.speechRate;

            utterance.onstart = function () {
                setStatus("Speaking… (" + voice.name + ")", "info");
            };
            utterance.onend = function () {
                if (activeUtterance === utterance) {
                    setStatus("");
                    activeUtterance = null;
                }
            };
            utterance.onerror = function (event) {
                if (event && event.error === "interrupted") {
                    return; // superseded by a newer request
                }
                setStatus(
                    "Pronunciation failed" + (event && event.error ? ": " + event.error : "."),
                    "error"
                );
                activeUtterance = null;
            };

            activeUtterance = utterance;
            // Chromium leaves speechSynthesis paused when the page is put in
            // the background - a sync, the editor and the More menu all do
            // that - and nothing resumes it, so every later speak() queues
            // silently and the voice never comes back. A no-op when it is not
            // paused, so it is safe to call on every utterance.
            synth.resume();
            synth.speak(utterance);
        });
    }

    // Having the language listed in Windows is not enough: the text-to-speech
    // pack is a separate optional feature, and that is the usual reason this
    // message appears even when the language itself is already installed.
    var INSTALL_HINT =
        "Windows Settings > Time & language > Language & region > ⋯ next to " +
        "the language > Language options > Speech. Adding the language alone " +
        "does not install a voice. Restart Anki afterwards.";

    function voiceMissingMessage(voices, lang) {
        if (!voices || !voices.length) {
            return "No speech voices are available at all. Install one: " + INSTALL_HINT;
        }
        var available = voices
            .map(function (v) {
                return v.lang;
            })
            .filter(function (value, index, list) {
                return list.indexOf(value) === index;
            })
            .slice(0, 6)
            .join(", ");
        return (
            'No "' +
            (lang || config.speechLanguage) +
            '" voice is installed (available: ' +
            available +
            "). Install it via " +
            INSTALL_HINT
        );
    }

    // -- clipboard ------------------------------------------------------------

    /*
     * The copy is done by Python, not by the browser.
     *
     * Anki never enables QWebEngineSettings.JavascriptCanAccessClipboard, and
     * with it off `navigator.clipboard.writeText()` returns a promise that
     * never settles - it neither resolves nor rejects, so a `.catch()` fallback
     * is never reached - while `document.execCommand("copy")` simply returns
     * false. Both browser routes are dead here, so the text goes over the
     * bridge to Qt's clipboard instead.
     */
    function copyToClipboard() {
        var text = lastTranslation || selectedText;
        if (!text) {
            return;
        }
        if (typeof pycmd !== "function") {
            setStatus("Anki's JavaScript bridge is unavailable. Restart Anki.", "error");
            return;
        }
        requestCounter += 1;
        pendingCopyId = requestCounter;
        pycmd(BRIDGE + "copy:" + JSON.stringify({ id: pendingCopyId, text: text }));
    }

    /** Called from Python via web.eval once the clipboard has been written. */
    function onCopyResponse(payload) {
        if (!payload || payload.id !== pendingCopyId) {
            return;
        }
        pendingCopyId = 0;
        if (payload.ok) {
            confirmCopy(); // only confirm once the clipboard really holds the text
        } else {
            setStatus(payload.error || "Could not copy to the clipboard.", "error");
        }
    }

    /** Swap the clipboard glyph for a tick briefly; the button has no label. */
    function confirmCopy() {
        el.copy.classList.add("atp-copied");
        el.copy.title = "Copied";
        clearTimeout(copyResetTimer);
        copyResetTimer = setTimeout(function () {
            if (el.copy) {
                el.copy.classList.remove("atp-copied");
                el.copy.title = "Copy";
            }
        }, 1200);
    }

    // -- selection handling ---------------------------------------------------

    function selectionRect(selection) {
        var range = selection.getRangeAt(0);
        var rect = range.getBoundingClientRect();
        if (rect && (rect.width || rect.height)) {
            return rect;
        }
        // Collapsed/zero-size rects happen across line breaks; use the first client rect.
        var rects = range.getClientRects();
        return rects.length ? rects[0] : null;
    }

    // Elements whose boundaries imply a line break in the rendered card.
    var BLOCK_SELECTOR =
        "address,article,aside,blockquote,br,dd,div,dl,dt,figure,footer," +
        "h1,h2,h3,h4,h5,h6,header,hr,li,main,nav,ol,p,pre,section,table," +
        "tbody,td,th,thead,tr,ul";

    /*
     * Read the selection from the DOM instead of Selection.toString(), which
     * returns the *rendered* text. A card styled with `text-transform:
     * uppercase` would otherwise hand "groß" to the translator as "GROSS" and
     * "Grüße" as "GRÜSSE", losing exactly the German characters we must keep.
     */
    function selectionText(selection) {
        try {
            var fragment = selection.getRangeAt(0).cloneContents();
            var i;

            // <style> and <script> are never rendered but *are* part of
            // textContent, and Anki injects the card's stylesheet inside #qa.
            // Without this, dragging across the card captures the entire CSS
            // and posts it to the translation provider.
            var unrendered = fragment.querySelectorAll("style,script,template,noscript");
            for (i = 0; i < unrendered.length; i++) {
                unrendered[i].remove();
            }

            // textContent ignores layout, so re-introduce the line breaks the
            // reader sees; otherwise "Das Haus" and "ist groß" in sibling divs
            // arrive as "Das Hausist groß".
            var blocks = fragment.querySelectorAll(BLOCK_SELECTOR);
            for (i = 0; i < blocks.length; i++) {
                blocks[i].after(document.createTextNode("\n"));
            }

            var text = fragment.textContent;
            if (text && text.trim()) {
                return text;
            }
        } catch (err) {
            log("cloneContents failed, falling back to toString", err);
        }
        return String(selection.toString());
    }

    /** Collapse layout whitespace so the same phrase always hits one cache key. */
    function normaliseWhitespace(text) {
        return text.replace(/\s+/g, " ").trim();
    }

    function insidePopup(node) {
        return !!popup && !!node && popup.contains(node.nodeType === 1 ? node : node.parentNode);
    }

    /**
     * Open the popup for whatever is selected right now. Shared by the mouse
     * and the keyboard shortcut so both see exactly the same text and anchor.
     */
    function lookupSelection() {
        var selection = globalThis.getSelection ? getSelection() : null;
        if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
            return;
        }
        var text = normaliseWhitespace(selectionText(selection));
        if (!text) {
            return; // empty or whitespace-only
        }
        if (insidePopup(selection.anchorNode)) {
            return;
        }
        var rect = selectionRect(selection);
        if (!rect) {
            return;
        }
        show(text, rect);
    }

    function handleMouseUp(event) {
        if (insidePopup(event.target)) {
            return;
        }
        // Let Anki handle the click first; read the selection afterwards.
        setTimeout(lookupSelection, 0);
    }

    function handleMouseDown(event) {
        if (insidePopup(event.target)) {
            return;
        }
        hide(); // "click outside closes"; a drag-select re-opens it on mouseup
    }

    // -- keyboard -------------------------------------------------------------

    var MODIFIER_ALIASES = {
        ctrl: "ctrl",
        control: "ctrl",
        alt: "alt",
        option: "alt",
        shift: "shift",
        meta: "meta",
        cmd: "meta",
        command: "meta",
        super: "meta",
        win: "meta",
    };

    /**
     * "Ctrl+Shift+T" -> {ctrl: true, shift: true, alt: false, meta: false,
     * key: "t"}. Anything without exactly one non-modifier key yields null,
     * which simply disables the shortcut.
     */
    function parseShortcut(spec) {
        var parts = String(spec == null ? "" : spec).split("+");
        var parsed = { ctrl: false, alt: false, shift: false, meta: false, key: "" };
        for (var i = 0; i < parts.length; i++) {
            var part = parts[i].trim().toLowerCase();
            if (!part) {
                continue;
            }
            if (Object.prototype.hasOwnProperty.call(MODIFIER_ALIASES, part)) {
                parsed[MODIFIER_ALIASES[part]] = true;
            } else if (parsed.key) {
                return null; // two plain keys: not a shortcut we can honour
            } else {
                parsed.key = part;
            }
        }
        return parsed.key ? parsed : null;
    }

    var shortcut = parseShortcut(config.lookupShortcut);
    var promptShortcut = parseShortcut(config.pronouncePromptShortcut);
    var answerShortcut = parseShortcut(config.pronounceAnswerShortcut);
    var stopShortcut = parseShortcut(config.stopSpeechShortcut);

    function matchesShortcut(event, combo) {
        if (!combo) {
            return false;
        }
        return (
            event.ctrlKey === combo.ctrl &&
            event.altKey === combo.alt &&
            event.shiftKey === combo.shift &&
            event.metaKey === combo.meta &&
            String(event.key || "").toLowerCase() === combo.key
        );
    }

    /**
     * The defaults are bare letters, so a type-in-the-answer card would lose
     * every "x" and "c" the user tries to type. Never claim a key from a field.
     */
    function isEditableTarget(node) {
        if (!node || node.nodeType !== 1) {
            return false;
        }
        var tag = String(node.tagName || "").toLowerCase();
        return tag === "input" || tag === "textarea" || !!node.isContentEditable;
    }

    /** The text and language Python last sent for one side of the card. */
    function cardSide(side) {
        var answer = side === "answer";
        return {
            text: answer ? cardText.answer : cardText.prompt,
            lang: answer ? cardText.answerLang : cardText.promptLang,
        };
    }

    /** Speak one side of the card on screen. */
    function speakCardSide(side) {
        var wanted = cardSide(side);
        if (wanted.text) {
            speakText(wanted.text, wanted.lang);
            return;
        }
        // Nothing to say - either the answer is still hidden, or this page was
        // rebuilt since Python last pushed the text, which a sync, the editor
        // and the More menu all do. Ask again rather than staying mute until
        // the next card; Python decides whether the answer may be sent yet.
        if (typeof pycmd === "function") {
            log("no card text for the", side, "side - asking Python");
            pycmd(BRIDGE + "card_text:" + side);
        }
    }

    function handleKeyDown(event) {
        if (event.key === "Escape") {
            // One Escape per layer: the dropdown first, the popup second.
            if (isPickerOpen()) {
                event.preventDefault();
                event.stopPropagation();
                closePicker();
                return;
            }
            if (isOpen()) {
                event.preventDefault();
                event.stopPropagation();
                hide();
            }
            return;
        }
        if (isEditableTarget(event.target)) {
            return;
        }
        // Everything else falls through untouched unless it is exactly one of
        // the configured shortcuts - Anki's reviewer keys must keep working.
        if (matchesShortcut(event, promptShortcut)) {
            event.preventDefault();
            log("shortcut: pronounce prompt");
            speakCardSide("prompt");
            return;
        }
        if (matchesShortcut(event, answerShortcut)) {
            event.preventDefault();
            log("shortcut: pronounce answer");
            speakCardSide("answer");
            return;
        }
        if (matchesShortcut(event, stopShortcut)) {
            event.preventDefault();
            log("shortcut: stop speech");
            stopAllSpeech();
            return;
        }
        if (matchesShortcut(event, shortcut)) {
            event.preventDefault();
            lookupSelection();
        }
    }

    document.addEventListener("mousedown", handleMouseDown, true);
    document.addEventListener("mouseup", handleMouseUp, true);
    document.addEventListener("keydown", handleKeyDown, true);
    globalThis.addEventListener("resize", function () {
        if (isOpen()) {
            hide();
        }
    });

    warmVoices();

    globalThis[NS] = {
        onTranslationResponse: onTranslationResponse,
        onSpeechResponse: onSpeechResponse,
        onCopyResponse: onCopyResponse,
        onConfigChanged: onConfigChanged,
        onCardText: onCardText,
        hide: hide,
        // Exposed for manual poking from Anki's debug console.
        _pickVoice: pickVoice,
        _prepareSpeechText: prepareSpeechText,
        _selectionSpeechLanguage: selectionSpeechLanguage,
        _voiceGenderOf: voiceGenderOf,
    };

    log("initialised", config);
})();
