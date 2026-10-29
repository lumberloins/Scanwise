/**
 * ScanWise browser key capture.
 *
 * Records raw keydown/keyup events as canonical key events (see BUILD_PLAN.md
 * section 3) and groups them into scans by idle gap. It never interprets
 * characters: decoding happens server-side so browser and agent captures are
 * decoded identically.
 *
 * Keys are received through a hidden, always-focused text box (the "sink").
 * Some browser/input-method combinations (seen: Firefox on Wayland with fcitx5)
 * deliver fast keystrokes reliably only while a text field has focus; with
 * focus on the bare page, everything after the first few keys was dropped.
 * Printable keys are allowed to type into the sink (blocking them is not
 * needed and is what text fields never see); text that arrives as input
 * without a matching key press (IME commits, paste-style injection) is
 * recorded as code-less key events, so nothing is lost either way.
 */

const FORM_TAGS = new Set(['INPUT', 'SELECT', 'TEXTAREA']);

/** Keys a scanner sends as a suffix: Enter, Tab, or Ctrl+M / Ctrl+J / Ctrl+I (CR / LF / HT). */
function isTerminatorKey(ev) {
    if (ev.type !== 'down') return false;
    const code = ev.code || '';
    if (['Enter', 'NumpadEnter', 'Tab'].includes(code) || ['Enter', 'Tab'].includes(ev.key)) return true;
    return !!(ev.mods && ev.mods.ctrl) && ['KeyM', 'KeyJ', 'KeyI'].includes(code);
}

function isModifierKey(ev) {
    return /^(Shift|Control|Alt|Meta|OS)/.test(ev.code || '') || ['Shift', 'Control', 'Alt', 'Meta', 'OS'].includes(ev.key);
}

/** A plain character key the sink may type (everything else is blocked). */
function isPlainChar(e) {
    return e.key && e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey;
}

function makeSink() {
    const sink = document.createElement('textarea');
    sink.id = 'scan-sink';
    sink.dataset.scanSink = '';
    sink.setAttribute('aria-hidden', 'true');
    sink.setAttribute('tabindex', '-1');
    for (const [k, v] of Object.entries({ autocomplete: 'off', autocorrect: 'off', autocapitalize: 'off', spellcheck: 'false' })) sink.setAttribute(k, v);
    Object.assign(sink.style, { position: 'fixed', top: '0', left: '0', width: '1px', height: '1px', opacity: '0',
        border: '0', padding: '0', margin: '0', resize: 'none', pointerEvents: 'none', zIndex: '-1' });
    return sink;
}

function isFormTarget(target) {
    if (!target || target === document.body) return false;
    if (target.dataset && 'scanSink' in target.dataset) return false;
    if (target.closest && target.closest('[data-scan-ignore]')) return true;
    return FORM_TAGS.has(target.tagName) || target.isContentEditable;
}

export class KeyCapture {
    /**
     * @param {object} opts
     * @param {number} [opts.gapMs=120]  idle time that ends a scan after a suffix key (Enter, Tab, LF)
     * @param {number} [opts.idleMs=1000] idle time that ends a scan otherwise. Scanners stall
     *        mid-barcode (Bluetooth buffers, keystroke-delay settings, a busy PC); a short gap
     *        there would split one barcode into several scans and show only the last piece.
     * @param {(scan: {events: object[], meta: object}) => void} opts.onScan
     * @param {(ev: object) => void} [opts.onEvent]  every recorded event (live view)
     * @param {string} [opts.src='browser']
     */
    constructor({ gapMs = 120, idleMs = 1000, onScan, onEvent, src = 'browser' } = {}) {
        this.gapMs = gapMs;
        this.idleMs = idleMs;
        this.lastKeyWasTerminator = false;
        this.onScan = onScan;
        this.onEvent = onEvent;
        this.src = src;
        this.armed = false;
        this.events = [];
        this.meta = null;
        this.timer = null;
        this.lastEventAt = -Infinity;

        this._onKey = this._onKey.bind(this);
        this._onBlur = this._onBlur.bind(this);
        this._onVisibility = this._onVisibility.bind(this);
        this._onBeforeUnload = this._onBeforeUnload.bind(this);
        this._onInput = this._onInput.bind(this);
        this._onCompositionEnd = this._onCompositionEnd.bind(this);
        this._onFocusOut = this._onFocusOut.bind(this);
        this._onPageHide = () => { if (this.sink) this.sink.value = ''; };
        this.sink = null;
        this.pendingKeys = [];   // printable keys whose text has not arrived as input yet
    }

    /** Put focus back on the sink unless the user is in a real form control or selecting text. */
    focusSink() {
        if (!this.sink) return;
        const a = document.activeElement;
        if (a && a !== document.body && a !== this.sink && a !== document.documentElement) return;
        const sel = window.getSelection && window.getSelection();
        if (sel && !sel.isCollapsed) return;
        this.sink.focus({ preventScroll: true });
    }

    _onFocusOut() {
        setTimeout(() => this.focusSink(), 0);
    }

    arm() {
        if (this.armed) return;
        this.armed = true;
        window.addEventListener('keydown', this._onKey, true);
        window.addEventListener('keyup', this._onKey, true);
        window.addEventListener('blur', this._onBlur);
        document.addEventListener('visibilitychange', this._onVisibility);
        window.addEventListener('beforeunload', this._onBeforeUnload);
        if (!this.sink) {
            this.sink = makeSink();
            document.body.appendChild(this.sink);
        }
        this.sink.addEventListener('input', this._onInput);
        this.sink.addEventListener('compositionend', this._onCompositionEnd);
        document.addEventListener('focusout', this._onFocusOut);
        window.addEventListener('focus', this._onFocusOut);
        document.addEventListener('pointerup', this._onFocusOut);
        window.addEventListener('pagehide', this._onPageHide);
        this.focusSink();
    }

    disarm() {
        if (!this.armed) return;
        this.armed = false;
        window.removeEventListener('keydown', this._onKey, true);
        window.removeEventListener('keyup', this._onKey, true);
        window.removeEventListener('blur', this._onBlur);
        document.removeEventListener('visibilitychange', this._onVisibility);
        window.removeEventListener('beforeunload', this._onBeforeUnload);
        document.removeEventListener('focusout', this._onFocusOut);
        window.removeEventListener('focus', this._onFocusOut);
        document.removeEventListener('pointerup', this._onFocusOut);
        window.removeEventListener('pagehide', this._onPageHide);
        if (this.sink) {
            this.sink.removeEventListener('input', this._onInput);
            this.sink.removeEventListener('compositionend', this._onCompositionEnd);
        }
        this.flush();
    }

    get scanActive() {
        return this.events.length > 0;
    }

    _onKey(e) {
        if (isFormTarget(e.target)) return;
        // Everything the scanner types is data: stop Tab moving focus, Enter
        // clicking buttons, F5 reloading, PageDown scrolling, and so on. Plain
        // characters may type into the sink (that is what keeps them flowing).
        const inSink = e.target === this.sink;
        if (!(inSink && isPlainChar(e))) e.preventDefault();
        e.stopPropagation();
        // IME "Process" keys (keyCode 229) carry no character; their text arrives as input.
        if (e.key === 'Process' || (e.keyCode === 229 && e.type === 'keydown' && !e.code)) return;
        if (inSink && e.type === 'keydown' && isPlainChar(e)) this.pendingKeys.push(e.key);

        // e.timeStamp is when the event was created, on the performance.now() timeline.
        const t = e.timeStamp || performance.now();
        const ev = {
            t: Math.round(t * 1000) / 1000,
            type: e.type === 'keydown' ? 'down' : 'up',
            code: e.code || '',
            key: e.key,
            mods: { ctrl: e.ctrlKey, shift: e.shiftKey, alt: e.altKey, meta: e.metaKey },
            repeat: e.repeat,
            location: e.location,
            keyCode: e.keyCode,   // 229 = IME composition, 231 = Windows VK_PACKET (Unicode injection)
            src: this.src,
        };
        if (!this.meta) {
            this.meta = { startedAt: new Date().toISOString(), interrupted: false, interruption_reason: null };
        }
        this._record(ev);
    }

    /** Text that reached the sink. Characters with no matching key press become code-less key events. */
    _onInput(e) {
        const sink = this.sink;
        const data = e.data != null ? e.data : '';
        if (e.inputType && !/^insert(Text|FromComposition|CompositionText|ReplacementText|FromPaste|FromDrop)?$/.test(e.inputType)) {
            sink.value = '';
            return;
        }
        if (e.isComposing || e.inputType === 'insertCompositionText') return;  // committed text comes via compositionend
        this._ingestText(data, e.timeStamp);
        // The text is already recorded; never leave scanned data sitting in a form field (browsers
        // can save field contents to disk for session restore).
        sink.value = '';
    }

    _onCompositionEnd(e) {
        this._ingestText(e.data || '', e.timeStamp);
    }

    _ingestText(data, timeStamp) {
        const t = Math.round((timeStamp || performance.now()) * 1000) / 1000;
        for (const ch of data) {
            const i = this.pendingKeys.indexOf(ch);
            if (i !== -1) { this.pendingKeys.splice(0, i + 1); continue; }
            if (!this.meta) this.meta = { startedAt: new Date().toISOString(), interrupted: false, interruption_reason: null };
            const base = { code: '', key: ch, mods: { ctrl: false, shift: false, alt: false, meta: false }, repeat: false,
                location: 0, keyCode: 0, src: this.src, from_input: true };
            this._record({ ...base, t, type: 'down' });
            this._record({ ...base, t, type: 'up' });
        }
    }

    /** Feed an externally captured event (e.g. from the native agent) through the same segmentation. */
    push(ev) {
        if (!this.meta) {
            this.meta = { startedAt: new Date().toISOString(), interrupted: false, interruption_reason: null };
        }
        this._record(ev);
    }

    _record(ev) {
        this.events.push(ev);
        this.lastEventAt = performance.now();
        if (ev.type === 'down' && !isModifierKey(ev)) this.lastKeyWasTerminator = isTerminatorKey(ev);
        if (this.onEvent) this.onEvent(ev);
        this._schedule();
    }

    _schedule() {
        clearTimeout(this.timer);
        const wait = this.lastKeyWasTerminator ? this.gapMs : Math.max(this.gapMs, this.idleMs);
        this.timer = setTimeout(() => this.flush(), wait);
    }

    _markInterrupted(reason) {
        if (this.scanActive && this.meta && !this.meta.interrupted) {
            this.meta.interrupted = true;
            this.meta.interruption_reason = reason;
        }
    }

    _onBlur() {
        this._markInterrupted('window lost focus (blur)');
    }

    _onVisibility() {
        if (document.visibilityState === 'hidden') this._markInterrupted('tab hidden (visibilitychange)');
    }

    _onBeforeUnload(e) {
        // A scanner in Ctrl-ASCII mode sends ETB as Ctrl+W. Ask before the tab closes mid-scan.
        if (this.scanActive) {
            this._markInterrupted('page unload requested (Ctrl+W = ETB?)');
            e.preventDefault();
            e.returnValue = '';
        }
    }

    flush() {
        clearTimeout(this.timer);
        const events = this.events;
        const meta = this.meta;
        this.events = [];
        this.meta = null;
        this.lastKeyWasTerminator = false;
        this.pendingKeys = [];
        if (this.sink) this.sink.value = '';
        const hasKey = events.some(ev => ev.type === 'down' && !/^(Shift|Control|Alt|Meta|OS)/.test(ev.code));
        if (!hasKey || !this.onScan) return;
        meta.endedAt = new Date().toISOString();
        meta.gap_ms = this.gapMs;
        meta.idle_ms = this.idleMs;
        this.onScan({ events, meta });
    }
}

/**
 * Fullscreen + Keyboard Lock (Chromium). Lets the page receive Ctrl+W/T/N
 * (ETB/DC4/SO in Ctrl-ASCII mode) instead of the browser acting on them.
 */
export async function enableKeyboardLock() {
    const result = { fullscreen: false, locked: false, supported: !!(navigator.keyboard && navigator.keyboard.lock) };
    try {
        if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
        result.fullscreen = !!document.fullscreenElement;
        if (result.supported) {
            await navigator.keyboard.lock();
            result.locked = true;
        }
    } catch (err) {
        result.error = String(err && err.message || err);
    }
    return result;
}

export function disableKeyboardLock() {
    if (navigator.keyboard && navigator.keyboard.unlock) navigator.keyboard.unlock();
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
}

export function keyboardLockState() {
    return { supported: !!(navigator.keyboard && navigator.keyboard.lock), fullscreen: !!document.fullscreenElement };
}
