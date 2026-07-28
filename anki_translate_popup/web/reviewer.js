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
        preferredVoice: "",
        speechRate: 0.9,
        fontSize: 14,
        debug: false,
    };

    var config = Object.assign({}, DEFAULTS, globalThis.ankiTranslatePopupConfig || {});

    var popup = null;
    var el = {};
    var selectedText = "";
    var lastTranslation = "";
    var lastRect = null;
    var requestCounter = 0;
    var pendingRequestId = 0;
    var pendingSpeechId = 0;
    var pendingCopyId = 0;
    var onlineSpeechActive = false;
    var activeUtterance = null;
    var copyResetTimer = null;

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

    var ICON_CHECK =
        SVG_OPEN +
        ' class="atp-glyph atp-glyph--check">' +
        '<polyline points="20 6 9 17 4 12"></polyline>' +
        "</svg>";

    // Constant markup only. All dynamic values are assigned via textContent.
    var SKELETON = [
        '<div class="atp-header">',
        '  <span class="atp-langs"></span>',
        '  <div class="atp-actions">',
        '    <button type="button" class="atp-btn atp-translate"',
        '            title="Translate" aria-label="Translate">' + ICON_TRANSLATE + "</button>",
        '    <button type="button" class="atp-btn atp-pronounce"',
        '            title="Pronounce" aria-label="Pronounce">' + ICON_SPEAKER + "</button>",
        '    <button type="button" class="atp-btn atp-copy"',
        '            title="Copy" aria-label="Copy">' + ICON_COPY + ICON_CHECK + "</button>",
        "  </div>",
        '  <button type="button" class="atp-close" title="Close (Esc)" aria-label="Close">&times;</button>',
        "</div>",
        '<div class="atp-result" hidden></div>',
        '<div class="atp-status" hidden></div>',
        '<div class="atp-examples" hidden></div>',
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
            langs: root.querySelector(".atp-langs"),
            close: root.querySelector(".atp-close"),
            result: root.querySelector(".atp-result"),
            status: root.querySelector(".atp-status"),
            examples: root.querySelector(".atp-examples"),
            translate: root.querySelector(".atp-translate"),
            pronounce: root.querySelector(".atp-pronounce"),
            copy: root.querySelector(".atp-copy"),
        };

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

        // Selecting inside the popup must not re-trigger the selection flow.
        root.addEventListener("mousedown", function (event) {
            event.stopPropagation();
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
        el.langs.textContent = String(source) + " → " + String(target);
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

    function hide() {
        if (!popup || popup.hidden) {
            return;
        }
        stopSpeech();
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
            setLanguages(payload.sourceLang, payload.targetLang);
            setResult(payload.text);
            setExamples(payload.examples);
        } else {
            setResult("");
            setExamples(null);
            setStatus(payload.error || "Translation failed.", "error");
        }
        // The popup was placed while empty; it is much taller now, so it has to
        // be re-anchored or a selection near the bottom pushes it off-screen.
        reposition();
    }

    /** Called from Python when the user edits the add-on configuration. */
    function onConfigChanged(next) {
        config = Object.assign({}, DEFAULTS, next || {});
        if (popup) {
            applyFontSize();
            if (isOpen() && !lastTranslation) {
                setLanguages(config.sourceLanguage, config.targetLanguage);
            }
        }
        log("config updated", config);
    }

    // -- pronunciation --------------------------------------------------------

    function stopSpeech() {
        if (globalThis.speechSynthesis) {
            globalThis.speechSynthesis.cancel();
        }
        activeUtterance = null;
        pendingSpeechId = 0;
        // Only reach across the bridge if online audio could actually be playing.
        if (onlineSpeechActive && typeof pycmd === "function") {
            onlineSpeechActive = false;
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
    function pickVoice(voices, wantedLang, preferredName) {
        if (!voices || !voices.length) {
            return null;
        }
        var i;
        if (preferredName) {
            var wantedName = preferredName.toLowerCase();
            for (i = 0; i < voices.length; i++) {
                if (String(voices[i].name).toLowerCase() === wantedName) {
                    return voices[i];
                }
            }
        }
        var lang = String(wantedLang || "").toLowerCase().replace("_", "-");
        var base = lang.split("-")[0];
        for (i = 0; i < voices.length; i++) {
            if (String(voices[i].lang).toLowerCase().replace("_", "-") === lang) {
                return voices[i];
            }
        }
        for (i = 0; i < voices.length; i++) {
            if (String(voices[i].lang).toLowerCase().replace("_", "-").split("-")[0] === base) {
                return voices[i];
            }
        }
        return null;
    }

    /** Ask Python to synthesise and play the audio. */
    function speakOnline() {
        if (typeof pycmd !== "function") {
            setStatus("Anki's JavaScript bridge is unavailable. Restart Anki.", "error");
            return;
        }
        requestCounter += 1;
        pendingSpeechId = requestCounter;
        onlineSpeechActive = true;
        setStatus("Fetching audio…", "loading");
        pycmd(
            BRIDGE + "speak:" + JSON.stringify({ id: pendingSpeechId, text: selectedText })
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
        if (!selectedText) {
            return;
        }

        stopSpeech(); // requirement: never overlap two pronunciations

        var mode = config.ttsProvider || "auto";
        if (mode === "google_unofficial") {
            speakOnline();
            return;
        }

        var synth = globalThis.speechSynthesis;
        if (!synth || typeof globalThis.SpeechSynthesisUtterance !== "function") {
            if (mode === "auto") {
                speakOnline();
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
            var voice = pickVoice(voices, config.speechLanguage, config.preferredVoice);
            if (!voice) {
                // Windows may report the language as installed while exposing
                // no usable voice (Narrator-only "natural voices" do this), so
                // "auto" quietly goes online rather than dead-ending.
                if (mode === "auto") {
                    speakOnline();
                    return;
                }
                setStatus(voiceMissingMessage(voices), "error");
                return;
            }

            // Always the original selection, never the translation.
            var utterance = new globalThis.SpeechSynthesisUtterance(selectedText);
            utterance.voice = voice;
            utterance.lang = voice.lang || config.speechLanguage;
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

    function voiceMissingMessage(voices) {
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
            config.speechLanguage +
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

    function handleMouseUp(event) {
        if (insidePopup(event.target)) {
            return;
        }
        // Let Anki handle the click first; read the selection afterwards.
        setTimeout(function () {
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
        }, 0);
    }

    function handleMouseDown(event) {
        if (insidePopup(event.target)) {
            return;
        }
        hide(); // "click outside closes"; a drag-select re-opens it on mouseup
    }

    function handleKeyDown(event) {
        if (event.key !== "Escape" || !isOpen()) {
            return; // never swallow any other key - Anki's shortcuts must work
        }
        event.preventDefault();
        event.stopPropagation();
        hide();
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
        hide: hide,
        // Exposed for manual poking from Anki's debug console.
        _pickVoice: pickVoice,
    };

    log("initialised", config);
})();
