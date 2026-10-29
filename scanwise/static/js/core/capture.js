/**
 * ScanWise browser key capture.
 *
 * Records raw keydown/keyup events as canonical key events (see BUILD_PLAN.md
 * section 3) and groups them into scans by idle gap. It never interprets
 * characters: decoding happens server-side so browser and agent captures are
 * decoded identically.
 */

const FORM_TAGS = new Set(['INPUT', 'SELECT', 'TEXTAREA']);

function isFormTarget(target) {
    if (!target || target === document.body) return false;
    if (target.closest && target.closest('[data-scan-ignore]')) return true;
    return FORM_TAGS.has(target.tagName) || target.isContentEditable;
}

export class KeyCapture {
    /**
     * @param {object} opts
     * @param {number} [opts.gapMs=120]  idle time that ends a scan
     * @param {(scan: {events: object[], meta: object}) => void} opts.onScan
     * @param {(ev: object) => void} [opts.onEvent]  every recorded event (live view)
     * @param {string} [opts.src='browser']
     */
    constructor({ gapMs = 120, onScan, onEvent, src = 'browser' } = {}) {
        this.gapMs = gapMs;
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
    }

    arm() {
        if (this.armed) return;
        this.armed = true;
        window.addEventListener('keydown', this._onKey, true);
        window.addEventListener('keyup', this._onKey, true);
        window.addEventListener('blur', this._onBlur);
        document.addEventListener('visibilitychange', this._onVisibility);
        window.addEventListener('beforeunload', this._onBeforeUnload);
    }

    disarm() {
        if (!this.armed) return;
        this.armed = false;
        window.removeEventListener('keydown', this._onKey, true);
        window.removeEventListener('keyup', this._onKey, true);
        window.removeEventListener('blur', this._onBlur);
        document.removeEventListener('visibilitychange', this._onVisibility);
        window.removeEventListener('beforeunload', this._onBeforeUnload);
        this.flush();
    }

    get scanActive() {
        return this.events.length > 0;
    }

    _onKey(e) {
        if (isFormTarget(e.target)) return;
        // Everything the scanner types is data: stop Tab moving focus, Enter
        // clicking buttons, F5 reloading, PageDown scrolling, and so on.
        e.preventDefault();
        e.stopPropagation();

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
            src: this.src,
        };
        if (!this.meta) {
            this.meta = { startedAt: new Date().toISOString(), interrupted: false, interruption_reason: null };
        }
        this.events.push(ev);
        this.lastEventAt = performance.now();
        if (this.onEvent) this.onEvent(ev);
        this._schedule();
    }

    /** Feed an externally captured event (e.g. from the native agent) through the same segmentation. */
    push(ev) {
        if (!this.meta) {
            this.meta = { startedAt: new Date().toISOString(), interrupted: false, interruption_reason: null };
        }
        this.events.push(ev);
        this.lastEventAt = performance.now();
        if (this.onEvent) this.onEvent(ev);
        this._schedule();
    }

    _schedule() {
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.flush(), this.gapMs);
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
        const hasKey = events.some(ev => ev.type === 'down' && !/^(Shift|Control|Alt|Meta|OS)/.test(ev.code));
        if (!hasKey || !this.onScan) return;
        meta.endedAt = new Date().toISOString();
        meta.gap_ms = this.gapMs;
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
