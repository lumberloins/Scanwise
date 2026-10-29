/**
 * Minimal Chrome DevTools Protocol driver for ScanWise e2e tests.
 * Uses only Node built-ins (fetch, WebSocket, child_process). No npm install.
 *
 * Key events are dispatched with Input.dispatchKeyEvent, which delivers real
 * keydown/keyup events (with .code, .key and modifier flags) to the page, as
 * closely as possible to how a HID scanner's keystrokes arrive.
 */
import { spawn } from 'node:child_process';
import { mkdtempSync, readFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const sleep = ms => new Promise(r => setTimeout(r, ms));

export async function waitFor(fn, { timeout = 10000, interval = 50, what = 'condition' } = {}) {
    const end = Date.now() + timeout;
    let last;
    while (Date.now() < end) {
        try { last = await fn(); if (last) return last; } catch (e) { last = e; }
        await sleep(interval);
    }
    throw new Error(`Timed out waiting for ${what}${last instanceof Error ? `: ${last.message}` : ''}`);
}

export async function launchChromium({ bin = process.env.CHROMIUM || 'chromium', tmpRoot } = {}) {
    const dir = mkdtempSync(join(tmpRoot || tmpdir(), 'scanwise-chrome-'));
    const proc = spawn(bin, [
        '--headless=new', '--remote-debugging-port=0', `--user-data-dir=${dir}`,
        '--no-first-run', '--no-default-browser-check', '--disable-gpu', 'about:blank',
    ], { stdio: ['ignore', 'ignore', 'pipe'] });
    const portFile = join(dir, 'DevToolsActivePort');
    await waitFor(() => existsSync(portFile) && readFileSync(portFile, 'utf8').split('\n')[0], { what: 'DevToolsActivePort' });
    const port = readFileSync(portFile, 'utf8').split('\n')[0].trim();
    const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    const page = targets.find(t => t.type === 'page');
    const cdp = await CDP.connect(page.webSocketDebuggerUrl);
    return {
        cdp, port,
        async close() {
            try { cdp.close(); } catch {}
            proc.kill('SIGTERM');
            await sleep(200);
            try { rmSync(dir, { recursive: true, force: true }); } catch {}
        },
    };
}

export class CDP {
    static async connect(url) {
        const ws = new WebSocket(url);
        await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
        return new CDP(ws);
    }

    constructor(ws) {
        this.ws = ws;
        this.id = 0;
        this.pending = new Map();
        this.listeners = [];
        this.dialogs = [];
        ws.onmessage = msg => {
            const data = JSON.parse(msg.data);
            if (data.id && this.pending.has(data.id)) {
                const { resolve, reject } = this.pending.get(data.id);
                this.pending.delete(data.id);
                data.error ? reject(new Error(data.error.message)) : resolve(data.result);
            } else if (data.method === 'Page.javascriptDialogOpening') {
                this.dialogs.push(data.params);
                this.send('Page.handleJavaScriptDialog', { accept: true });
            } else if (data.method) {
                this.listeners.forEach(l => l(data));
            }
        };
    }

    send(method, params = {}) {
        const id = ++this.id;
        this.ws.send(JSON.stringify({ id, method, params }));
        return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
    }

    close() { this.ws.close(); }

    async navigate(url) {
        await this.send('Page.enable');
        const loaded = new Promise(res => {
            const l = d => { if (d.method === 'Page.loadEventFired') { this.listeners = this.listeners.filter(x => x !== l); res(); } };
            this.listeners.push(l);
        });
        await this.send('Page.navigate', { url });
        await loaded;
    }

    async eval(expression) {
        const r = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
        if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
        return r.result.value;
    }
}

// ---- Scanner keystroke synthesis -------------------------------------------------

const MOD_BITS = { alt: 1, ctrl: 2, meta: 4, shift: 8 };
const MOD_KEYS = {
    ShiftLeft: ['Shift', 'shift', 16], ControlLeft: ['Control', 'ctrl', 17], AltLeft: ['Alt', 'alt', 18],
};
const SYMBOLS = {
    '`': ['Backquote', false, 192], '~': ['Backquote', true, 192], '-': ['Minus', false, 189], '_': ['Minus', true, 189],
    '=': ['Equal', false, 187], '+': ['Equal', true, 187], '[': ['BracketLeft', false, 219], '{': ['BracketLeft', true, 219],
    ']': ['BracketRight', false, 221], '}': ['BracketRight', true, 221], '\\': ['Backslash', false, 220],
    '|': ['Backslash', true, 220], ';': ['Semicolon', false, 186], ':': ['Semicolon', true, 186],
    "'": ['Quote', false, 222], '"': ['Quote', true, 222], ',': ['Comma', false, 188], '<': ['Comma', true, 188],
    '.': ['Period', false, 190], '>': ['Period', true, 190], '/': ['Slash', false, 191], '?': ['Slash', true, 191],
    ' ': ['Space', false, 32], '!': ['Digit1', true, 49], '@': ['Digit2', true, 50], '#': ['Digit3', true, 51],
    '$': ['Digit4', true, 52], '%': ['Digit5', true, 53], '^': ['Digit6', true, 54], '&': ['Digit7', true, 55],
    '*': ['Digit8', true, 56], '(': ['Digit9', true, 57], ')': ['Digit0', true, 48],
};
const NAMED = { Enter: 13, Tab: 9, Backspace: 8, Escape: 27, Delete: 46, PageDown: 34, PageUp: 33, F5: 116, F12: 123 };

function charToKey(ch) {
    if (/[a-z]/.test(ch)) return { code: `Key${ch.toUpperCase()}`, shift: false, vk: ch.toUpperCase().charCodeAt(0) };
    if (/[A-Z]/.test(ch)) return { code: `Key${ch}`, shift: true, vk: ch.charCodeAt(0) };
    if (/[0-9]/.test(ch)) return { code: `Digit${ch}`, shift: false, vk: ch.charCodeAt(0) };
    if (SYMBOLS[ch]) { const [code, shift, vk] = SYMBOLS[ch]; return { code, shift, vk }; }
    throw new Error(`Cannot type ${JSON.stringify(ch)}`);
}

/** Builds and plays a keystroke sequence the way a HID scanner types it. */
export class Scanner {
    constructor(cdp, { stepMs = 3 } = {}) {
        this.cdp = cdp;
        this.stepMs = stepMs;
        this.mods = { alt: false, ctrl: false, meta: false, shift: false };
        this.ops = [];
    }

    _bits() { return Object.entries(this.mods).reduce((b, [k, v]) => b | (v ? MOD_BITS[k] : 0), 0); }

    _push(type, code, key, vk) {
        this.ops.push(() => this.cdp.send('Input.dispatchKeyEvent', {
            type: type === 'down' ? 'rawKeyDown' : 'keyUp', code, key, modifiers: this._bits(),
            windowsVirtualKeyCode: vk, nativeVirtualKeyCode: vk,
        }));
    }

    modDown(code) { const [key, m, vk] = MOD_KEYS[code]; this.ops.push(() => { this.mods[m] = true; }); this._push('down', code, key, vk); return this; }
    modUp(code) { const [key, m, vk] = MOD_KEYS[code]; this.ops.push(() => { this.mods[m] = false; }); this._push('up', code, key, vk); return this; }

    press(code, key, vk) { this._push('down', code, key, vk); this._push('up', code, key, vk); return this; }

    type(text) {
        for (const ch of text) {
            const { code, shift, vk } = charToKey(ch);
            if (shift) this.modDown('ShiftLeft');
            this.press(code, ch, vk);
            if (shift) this.modUp('ShiftLeft');
        }
        return this;
    }

    key(name) { return this.press(name, name, NAMED[name] || 0); }
    enter() { return this.key('Enter'); }
    tab() { return this.key('Tab'); }

    /** Ctrl + key, e.g. ctrl('BracketRight') = GS, ctrl('KeyJ') = LF. */
    ctrl(code, { shift = false } = {}) {
        this.modDown('ControlLeft');
        if (shift) this.modDown('ShiftLeft');
        const ch = code.startsWith('Key') ? code.slice(3).toLowerCase() : (Object.entries(SYMBOLS).find(([, v]) => v[0] === code && v[1] === shift) || [''])[0];
        const vk = code.startsWith('Key') ? code.charCodeAt(3) : (SYMBOLS[ch] ? SYMBOLS[ch][2] : 0);
        this.press(code, ch, vk);
        if (shift) this.modUp('ShiftLeft');
        return this.modUp('ControlLeft');
    }

    /** Alt + numpad digits, e.g. alt('0029') = GS. */
    alt(digits) {
        this.modDown('AltLeft');
        for (const d of digits) this.press(`Numpad${d}`, d, 96 + Number(d));
        return this.modUp('AltLeft');
    }

    async play() {
        for (const op of this.ops) {
            await op();
            if (this.stepMs) await sleep(this.stepMs / 2);
        }
        this.ops = [];
    }
}

// ---- Flask server ------------------------------------------------------------------

export async function startServer({ port = 5055, cwd } = {}) {
    const proc = spawn('mise', ['exec', 'python', '--', 'python', 'run.py'], {
        cwd, env: { ...process.env, SCANWISE_PORT: String(port), SCANWISE_HOST: '127.0.0.1', FLASK_DEBUG: 'false' },
        stdio: ['ignore', 'ignore', 'pipe'],
    });
    let stderr = '';
    proc.stderr.on('data', d => { stderr += d; });
    const base = `http://127.0.0.1:${port}`;
    await waitFor(async () => (await fetch(`${base}/health`)).ok, { what: `Flask on ${base}`, timeout: 20000 })
        .catch(e => { proc.kill(); throw new Error(`${e.message}\n${stderr}`); });
    return { base, stop: () => proc.kill('SIGTERM') };
}

// ---- scanwise-agent (replay mode) ------------------------------------------------------

export async function startAgent({ root, origin, replayFile, port = 47811, tmpRoot }) {
    const { execFileSync } = await import('node:child_process');
    const bin = join(tmpRoot || tmpdir(), `scanwise-agent-e2e-${process.pid}`);
    execFileSync('go', ['build', '-o', bin, '.'], { cwd: join(root, 'agent'), stdio: 'inherit' });
    const proc = spawn(bin, ['-listen', `127.0.0.1:${port}`, '-allow-origin', origin, '-no-native', '-replay', replayFile],
        { stdio: ['ignore', 'ignore', 'pipe'] });
    let stderr = '';
    proc.stderr.on('data', d => { stderr += d; });
    const base = `http://127.0.0.1:${port}`;
    await waitFor(async () => (await fetch(`${base}/status`, { headers: { Origin: origin } })).ok, { what: 'agent' })
        .catch(e => { proc.kill(); throw new Error(`${e.message}\n${stderr}`); });
    return { base, stop: () => { proc.kill('SIGTERM'); try { rmSync(bin); } catch {} } };
}
