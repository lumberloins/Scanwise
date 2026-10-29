#!/usr/bin/env node
/**
 * ScanWise end-to-end tests: real key events in headless Chromium.
 *
 *   node tools/e2e_cdp.mjs [suite ...]      suites: tech, engineering, agent, harness (default: all)
 *   SCANWISE_SHOTS=/dir saves screenshots.
 *
 * Env: CHROMIUM=/path/to/chromium, SCANWISE_URL=http://host:port (skip starting Flask).
 */
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { launchChromium, startServer, startAgent, Scanner, waitFor } from './cdp.mjs';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const results = [];

function assert(cond, msg) { if (!cond) throw new Error(msg); }
function eq(a, b, msg) { assert(a === b, `${msg}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`); }

async function test(name, fn) {
    try { await fn(); results.push([name, true]); console.log(`  ok   ${name}`); }
    catch (e) { results.push([name, false]); console.log(`  FAIL ${name}\n       ${e.message}`); }
}

/** Play keystrokes, then wait for the n-th scan result recorded by the page under `window.__scans`. */
async function scanAndWait(cdp, build, opts = {}) {
    const before = await cdp.eval('window.__scans.length');
    const s = new Scanner(cdp, opts);
    build(s);
    await s.play();
    await waitFor(() => cdp.eval(`window.__scans.length > ${before}`), { what: 'scan result' });
    return cdp.eval('window.__scans[window.__scans.length - 1]');
}

async function screenshot(cdp, name) {
    const dir = process.env.SCANWISE_SHOTS;
    if (!dir) return;
    await new Promise(r => setTimeout(r, 400));  // let CSS transitions settle
    const { data } = await cdp.send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
    const { writeFileSync } = await import('node:fs');
    writeFileSync(join(dir, `${name}.png`), Buffer.from(data, 'base64'));
}

const text = (cdp, sel) => cdp.eval(`document.querySelector(${JSON.stringify(sel)}).textContent`);
const badges = (cdp, sel) => cdp.eval(`[...document.querySelectorAll(${JSON.stringify(sel + ' .char-badge')})].map(b => b.textContent).join(',')`);

export const suites = {
    async tech(cdp, base) {
        await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1100, height: 900, deviceScaleFactor: 1, mobile: false });
        await cdp.navigate(`${base}/`);
        await waitFor(() => cdp.eval('window.__ready === true'), { what: 'tech ready' });

        await test('Epic GS1 scan: configured for Epic, PASS, CR suffix badge', async () => {
            const r = await scanAndWait(cdp, s => s.type('\\]d2010030123456789610LOT1').ctrl('BracketRight').type('21SER9\\').enter());
            eq(r.verdict.category, 'PASS', 'verdict');
            assert((await text(cdp, '#cfg-configured-for')).includes('Epic'), 'configured for Epic');
            eq(await badges(cdp, '#cfg-suffix'), 'CR', 'suffix badges');
            assert((await text(cdp, '#cfg-gs1')).startsWith('Present'), 'GS1 separators present');
            eq(await cdp.eval("document.getElementById('verdict-banner').className.includes('verdict-success')"), true, 'green banner');
            eq(await cdp.eval("document.querySelector('details.details').open"), false, 'details collapsed (no hex by default)');
            await screenshot(cdp, 'tech-epic-pass');
        });

        await test('Epic \\data\\ wrapping, GS1, no Enter/Tab (real DENSO format): GS1 recognised, PASS', async () => {
            const r = await scanAndWait(cdp, s => s.type('\\0100301234567896' + '17271231' + '10LOT1').ctrl('BracketRight').type('21SER9\\'));
            eq(r.gs1_detection.is_gs1, true, 'GS1 detected');
            eq(r.verdict.category, 'PASS', 'verdict');
            assert((await text(cdp, '#cfg-configured-for')).includes('Epic'), 'configured for Epic');
            assert((await text(cdp, '#cfg-configured-for')).includes('no Enter or Tab'), 'tells the tech there is no Enter/Tab');
            eq(await text(cdp, '#status-scanner .status-word'), 'Working', 'scanner pill is not "Needs setup"');
            assert((await text(cdp, '#contents')).includes('LOT1'), 'lot shown in contents');
        });

        await test('Scanner stalls mid-barcode: still one scan, full data shown', async () => {
            const before = await cdp.eval('window.__scans.length');
            const r = await scanAndWait(cdp, s => s.type('010030123456789610LOT').pause(450).type('1').ctrl('BracketRight').pause(450).type('21SER9').enter());
            eq(await cdp.eval('window.__scans.length'), before + 1, 'one scan, not split');
            eq(r.text, '010030123456789610LOT1\x1d21SER9\r', 'full text');
            eq(await text(cdp, '#scan-stream'), '010030123456789610LOT1GS21SER9CR', 'stream shows everything');
        });

        await test('Keys are received through the focused hidden text box', async () => {
            eq(await cdp.eval('document.activeElement && document.activeElement.id'), 'scan-sink', 'sink focused on load');
            await cdp.eval("document.getElementById('clear-btn').click()");
            await new Promise(r => setTimeout(r, 50));
            eq(await cdp.eval('document.activeElement && document.activeElement.id'), 'scan-sink', 'sink refocused after a button click');
        });

        await test('Real key presses that type text: no duplicates, full data', async () => {
            const r = await scanAndWait(cdp, s => s.type('IS2216121').ctrl('BracketRight').type('x').enter(), { withText: true });
            eq(r.text, 'IS2216121\x1dx\r', 'text');
            eq(await cdp.eval("document.getElementById('scan-sink').value"), '', 'sink emptied after the scan');
        });

        await test('Characters that arrive only as text (no key press) are still captured', async () => {
            const r = await scanAndWait(cdp, s => s.type('IS').insertText('2216121').enter());
            eq(r.text, 'IS2216121\r', 'text');
            eq(await text(cdp, '#scan-stream'), 'IS2216121CR', 'stream');
        });

        await test('Tab suffix: shown as TAB badge; Epic check fails (not wrapped in \\ \\)', async () => {
            await scanAndWait(cdp, s => s.type('MRN0042').tab());
            eq(await badges(cdp, '#cfg-suffix'), 'TAB', 'suffix badges');
            const epic = await cdp.eval("[...document.querySelectorAll('#cfg-profiles li')].find(li => li.textContent.includes('Epic')).className");
            eq(epic, 'no', 'Epic check');
        });

        await test('CR+LF suffix: CR,LF badges and words', async () => {
            await scanAndWait(cdp, s => s.type('MRN0042').enter().ctrl('KeyJ'));
            eq(await badges(cdp, '#cfg-suffix'), 'CR,LF', 'suffix badges');
            assert((await text(cdp, '#cfg-suffix')).includes('Enter + Line feed'), 'suffix words');
        });

        await test('Expected Epic, scan not wrapped in \\ \\ -> fault banner with programming hint', async () => {
            await cdp.eval("(() => { const s = document.getElementById('profile-select'); s.value = 'epic_emr'; s.dispatchEvent(new Event('change')); })()");
            const r = await scanAndWait(cdp, s => s.type('MRN0042').tab());
            eq(r.verdict.category, 'SCANNER_CONFIG_FAULT', 'verdict');
            eq(await cdp.eval("document.getElementById('verdict-banner').className.includes('verdict-error')"), true, 'red banner');
            assert((await text(cdp, '#verdict-recommendation')).includes('Program the scanner for Epic'), 'actionable hint');
            await screenshot(cdp, 'tech-epic-fail');
            await cdp.eval("document.getElementById('profile-select').value = 'auto'");
        });

        await test('GS1 out of order, no AIM: detected, data shown inline, fields in received order', async () => {
            const r = await scanAndWait(cdp, s => s.type('21SER99').ctrl('BracketRight').type('0100301234567896').type('17270630').type('10L1').enter());
            eq(r.gs1_detection.is_gs1, true, 'detected as GS1');
            eq(await badges(cdp, '#scan-stream'), 'GS,CR', 'raw stream shows GS and CR in place');
            eq(await cdp.eval("document.getElementById('gs1-box').hidden"), false, 'GS1 box shown');
            const labels = await cdp.eval("[...document.querySelectorAll('#gs1-segments .seg-el .seg-label')].map(n => n.textContent.trim())");
            eq(labels.map(l => l.match(/\((\d+)\)/)[1]).join(','), '21,01,17,10', 'field order');
            const kinds = await cdp.eval("[...document.querySelectorAll('#gs1-segments .seg')].map(n => n.className.replace('seg seg-', '').split(' ')[0])");
            eq(kinds.join(','), 'el,sep,el,el,el,suffix', 'segment sequence with separator in place');
            assert((await text(cdp, '#gs1-order')).includes('(21) → (01) → (17) → (10)'), 'order line');
            eq(r.verdict.category, 'PASS', 'order alone is not a fault');
            await screenshot(cdp, 'tech-gs1-order');
        });

        await test('GS1 components shown as plain cards (GTIN, expiry, lot, serial) with PASS pills', async () => {
            const r = await scanAndWait(cdp, s => s.type(']d2').type('0100301234567896').type('17270630').type('10A1B2').ctrl('BracketRight').type('21XYZ').enter());
            eq(r.verdict.category, 'PASS', 'verdict');
            const labels = await cdp.eval("[...document.querySelectorAll('#contents .comp-label')].map(n => n.textContent)");
            eq(labels.join('|'), 'Product (GTIN)|Expiration date|Lot / Batch|Serial number', 'component order');
            const values = await cdp.eval("[...document.querySelectorAll('#contents .comp-value')].map(n => n.textContent)");
            eq(values[0], '00301234567896', 'GTIN'); eq(values[2], 'A1B2', 'lot'); eq(values[3], 'XYZ', 'serial');
            assert(values[1].includes('2027'), `expiry shown as a date: ${values[1]}`);
            assert((await text(cdp, '#contents')).includes('NDC 0123456789'), 'NDC derived from 03-prefixed GTIN');
            eq(await cdp.eval("document.getElementById('status-scanner').className"), 'status status-ok', 'scanner pill');
            eq(await cdp.eval("document.getElementById('status-barcode').className"), 'status status-ok', 'barcode pill');
            await screenshot(cdp, 'tech-gs1-components');
        });

        await test('Keystrokes without key codes (RDP/Citrix/Unicode mode) still decode GS1', async () => {
            const r = await scanAndWait(cdp, s => s.unicode('0100301234567896' + '10LOT9' + '\x1d' + '21SER').key('Enter'));
            eq(r.text, '010030123456789610LOT9\x1d21SER\r', 'decoded text');
            eq(r.gs1_detection.is_gs1, true, 'GS1 detected');
            eq(await badges(cdp, '#scan-stream'), 'GS,CR', 'stream');
            const labels = await cdp.eval("[...document.querySelectorAll('#contents .comp-label')].map(n => n.textContent)");
            eq(labels.join('|'), 'Product (GTIN)|Lot / Batch|Serial number', 'components');
        });

        await test('Key presses with nothing readable: clear message instead of a blank page', async () => {
            await scanAndWait(cdp, s => s.key('F5').key('PageDown'));
            assert((await text(cdp, '#verdict-headline')).includes('no characters could be read'), 'message');
            eq(await cdp.eval("document.getElementById('contents-card').hidden"), true, 'no empty cards');
        });

        await test('GS1 missing separator: field flagged in the field view', async () => {
            const r = await scanAndWait(cdp, s => s.type(']d20100301234567896').type('10ABCDEFGHIJKLMNO17270630').type('21XY').enter());
            assert(r.findings.some(f => f.id === 'missing_gs1_separator'), 'finding');
            eq(await cdp.eval("document.querySelectorAll('#gs1-segments .seg-bad').length"), 1, 'one bad field box');
            assert((await text(cdp, '#gs1-segments')).includes('GS MISSING'), 'marked GS MISSING');
            await screenshot(cdp, 'tech-gs1-missing');
        });

        await test('Form feed + rogue BEL are flagged as problem characters', async () => {
            const r = await scanAndWait(cdp, s => s.type('AB').ctrl('KeyG').type('C').ctrl('KeyL'));
            assert(r.findings.some(f => f.id === 'rogue_control_in_data'), 'BEL finding');
            const cls = await cdp.eval("[...document.querySelectorAll('#scan-stream .char-badge')].map(b => b.className).join('|')");
            assert(cls.includes('cat-control'), 'red badge class');
            eq(await badges(cdp, '#scan-stream'), 'BEL,FF', 'stream badges');
        });
    },

    async engineering(cdp, base) {
        await cdp.send('Emulation.setDeviceMetricsOverride', { width: 1300, height: 1000, deviceScaleFactor: 1, mobile: false });
        await cdp.navigate(`${base}/engineering`);
        await waitFor(() => cdp.eval('window.__ready === true'), { what: 'engineering ready' });
        await cdp.eval("localStorage.clear(); window.scanwise.state.history = [];");

        await test('PHI: old stored history is deleted on load; new scans never touch storage', async () => {
            await cdp.eval("localStorage.setItem('scanwise.engineering.history.v1', '[{\"id\":\"old\"}]')");
            await cdp.navigate(`${base}/engineering`);
            await waitFor(() => cdp.eval('window.__ready === true'), { what: 'engineering ready' });
            eq(await cdp.eval("localStorage.getItem('scanwise.engineering.history.v1')"), null, 'legacy history purged');
            await scanAndWait(cdp, s => s.type('MRN0042SMITH').enter());
            const stored = await cdp.eval("JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage })");
            assert(!stored.includes('SMITH') && !stored.includes('KeyS'), `scan data in browser storage: ${stored}`);
            eq(await cdp.eval("document.getElementById('scan-sink').value"), '', 'hidden text box empty');
            eq(await cdp.eval('window.scanwise.state.history.length'), 1, 'history kept in memory');
        });

        await test('PHI: exports are redacted by default; full data needs a second click', async () => {
            const labels = await cdp.eval("[...document.querySelectorAll('.export-buttons button')].map(b => b.textContent)");
            assert(labels.includes('Export scan (redacted)') && labels.includes('Export all (redacted)'), `labels: ${labels}`);
            const full = "[...document.querySelectorAll('#stream-tools .export-buttons button')][1]";
            await cdp.eval(`${full}.click()`);
            assert((await cdp.eval(`${full}.textContent`)).includes('Click again'), 'first click only asks to confirm');
            const red = await cdp.eval("fetch('/api/redact', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key_events: window.scanwise.state.current.events }) }).then(r => r.json())");
            const text = (await cdp.eval(`fetch('/api/analyze', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key_events: ${JSON.stringify(red.key_events)} }) }).then(r => r.json())`)).text;
            eq(text, 'XXX0000XXXXX\r', 'redacted file decodes to placeholders');
            await cdp.eval("localStorage.clear(); window.scanwise.state.history = [];");
        });

        await test('Alt+numpad GS, FF, F5 token: stream, char table, key events', async () => {
            const r = await scanAndWait(cdp, s => s.type('AB').alt('0029').type('CD').ctrl('KeyL').key('F5').enter());
            eq(r.text, 'AB\x1dCD\x0c\r', 'decoded text');
            eq(await badges(cdp, '#stream-box'), 'GS,FF,[F5],CR', 'stream badges');
            const via = await cdp.eval("[...document.querySelectorAll('#pane-chars tbody tr')][2].children[7].textContent");
            eq(via, 'Alt+numpad', 'GS produced by');
            const evRows = await cdp.eval("document.querySelectorAll('#pane-events tbody tr').length");
            eq(evRows, r.decode.event_count, 'one row per key event');
            assert(Number(await text(cdp, '#findings-count')) > 0, 'findings counted');
            await screenshot(cdp, 'eng-chars');
        });

        await test('GS1 field view in engineering stream card', async () => {
            await scanAndWait(cdp, s => s.type(']d2').type('17270630').type('10LOT1').ctrl('BracketRight').type('0100301234567896').enter());
            eq(await cdp.eval("document.querySelectorAll('#eng-gs1-segments .seg-el').length"), 3, 'three fields');
            await cdp.eval("document.querySelector('.eng-tab[data-tab=parsed]').click()");
            assert((await text(cdp, '#pane-parsed')).includes('(17) → (10) → (01)'), 'order in parsed pane');
            await screenshot(cdp, 'eng-gs1');
            await cdp.eval("document.querySelector('.eng-tab[data-tab=chars]').click()");
            await scanAndWait(cdp, s => s.type('AB').alt('0029').type('CD').ctrl('KeyL').key('F5').enter());
        });

        await test('Click a badge selects it in every panel', async () => {
            await cdp.eval("document.querySelector('#stream-box .char-badge').click()");
            const n = await cdp.eval("document.querySelectorAll('.selected').length");
            assert(n >= 3, `expected stream+table+hex selection, got ${n}`);
        });

        await test('Timing chart: one bar per inter-character gap', async () => {
            await cdp.eval("document.querySelector('.eng-tab[data-tab=timing]').click()");
            const r = await cdp.eval('window.__scans[window.__scans.length - 1]');
            const bars = await cdp.eval("document.querySelectorAll('#pane-timing .bar').length");
            eq(bars, r.decode.char_count - 1, 'bars');
            await screenshot(cdp, 'eng-timing');
        });

        await test('History + compare two scans', async () => {
            await scanAndWait(cdp, s => s.type('MRN42').enter());
            await scanAndWait(cdp, s => s.type('MRN42').enter().ctrl('KeyJ'));
            const ids = await cdp.eval('window.scanwise.state.history.map(h => h.id)');
            assert(ids.length >= 2, 'history has entries');
            await cdp.eval(`document.querySelector('.eng-tab[data-tab=compare]').click()`);
            await cdp.eval(`(() => { const st = window.scanwise.state; st.compareA = ${JSON.stringify(ids[1])}; st.compareB = ${JSON.stringify(ids[0])}; window.scanwise.renderCompare(); })()`);
            await waitFor(() => cdp.eval("!!document.querySelector('#pane-compare .diff-stream')"), { what: 'diff rendered' });
            const summary = await text(cdp, '#pane-compare .compare-out p');
            assert(summary.includes('0 only in A, 1 only in B'), `diff summary: ${summary}`);
            eq(await cdp.eval("document.querySelectorAll('#pane-compare .diff-add').length"), 1, 'one added unit (LF)');
            await screenshot(cdp, 'eng-compare');
        });

        await test('Import a replay file re-analyses it', async () => {
            const before = await cdp.eval('window.__scans.length');
            const n = await cdp.eval(`window.scanwise.importDocument({format: 'scanwise-capture', version: 1, scans: [{events: [
                {t: 0, type: 'down', code: 'KeyX'}, {t: 1, type: 'up', code: 'KeyX'},
                {t: 2, type: 'down', code: 'ControlLeft'}, {t: 3, type: 'down', code: 'BracketRight'}, {t: 4, type: 'up', code: 'BracketRight'}, {t: 5, type: 'up', code: 'ControlLeft'},
                {t: 6, type: 'down', code: 'Enter'}, {t: 7, type: 'up', code: 'Enter'}], source: {kind: 'agent', device: {name: 'Test scanner'}}}]})`);
            eq(n, 1, 'imported scans');
            const r = await cdp.eval('window.__scans[window.__scans.length - 1]');
            eq(await cdp.eval('window.__scans.length'), before + 1, 'analysed');
            eq(r.text, 'x\x1d\r', 'agent-style events decode (no key/mods)');
        });
    },

    async agent(cdp, base) {
        // Replay capture "AB<CR>" typed with Shift, as evdev would report it (no key/mods fields).
        const ev = [];
        let t = 0;
        const k = (type, code) => ev.push({ t: (t += 4), type, code });
        for (const c of ['KeyA', 'KeyB']) { k('down', 'ShiftLeft'); k('down', c); k('up', c); k('up', 'ShiftLeft'); }
        k('down', 'Enter'); k('up', 'Enter');
        const dir = mkdtempSync(join(tmpdir(), 'scanwise-e2e-'));
        const file = join(dir, 'replay.json');
        writeFileSync(file, JSON.stringify({ format: 'scanwise-capture', version: 1, scans: [{ events: ev }] }));
        const agent = await startAgent({ root: ROOT, origin: base, replayFile: file });
        try {
            await cdp.navigate(`${base}/engineering`);
            await waitFor(() => cdp.eval('window.__ready === true'), { what: 'engineering ready' });
            await cdp.eval(`localStorage.setItem('scanwise.agent.url', ${JSON.stringify(agent.base)})`);

            const pickDevice = async () => {
                await waitFor(() => cdp.eval("!!document.querySelector('#agent-device option[value=\"replay:0\"]')"), { what: 'agent device list' });
                await cdp.eval("(() => { const s = document.getElementById('agent-device'); s.value = 'replay:0'; s.dispatchEvent(new Event('change')); })()");
            };
            const waitScan = async before => {
                await waitFor(() => cdp.eval(`window.__scans.length > ${before}`), { what: 'agent scan', timeout: 8000 });
                return cdp.eval('window.__scans[window.__scans.length - 1]');
            };

            await test('Agent mode: replayed evdev-style events decode to AB<CR>', async () => {
                await cdp.eval("window.scanwise.setMode('agent')");
                const before = await cdp.eval('window.__scans.length');
                await pickDevice();
                const r = await waitScan(before);
                eq(r.text, 'AB\r', 'decoded text');
                eq(await cdp.eval('window.scanwise.state.current.source.kind'), 'agent', 'source');
                assert((await text(cdp, '#source-panel')).includes('Streaming'), 'source panel shows streaming');
                await screenshot(cdp, 'eng-agent');
            });

            await test('Both mode: agent saw the scan, browser received nothing', async () => {
                await cdp.eval("window.scanwise.setMode('both')");
                const before = await cdp.eval('window.__scans.length');
                await pickDevice();
                await waitScan(before);
                eq(await cdp.eval('!!window.scanwise.state.current.pair.missing'), true, 'pair missing');
                assert((await text(cdp, '#summary')).includes('Browser received nothing'), 'summary flags it');
            });

            await test('Both mode: browser dropped a character -> diff shows it', async () => {
                const before = await cdp.eval('window.__scans.length');
                await pickDevice();
                const s = new Scanner(cdp);
                s.type('A').enter();   // browser sees "A<CR>"; agent replays "AB<CR>"
                await s.play();
                await waitScan(before);
                await waitFor(() => cdp.eval("!!window.scanwise.state.current.pair && !!window.scanwise.state.current.pair.res"), { what: 'paired result' });
                const summary = await text(cdp, '#summary');
                assert(summary.includes('1 lost, 0 extra in browser'), `summary: ${summary}`);
                eq(await cdp.eval('window.scanwise.state.current.res.verdict.finding_id'), 'browser_lost_chars', 'headline verdict');
                await cdp.eval("document.querySelector('.eng-tab[data-tab=compare]').click()");
                await waitFor(() => cdp.eval("!!document.querySelector('.pair-out .diff-stream')"), { what: 'pair diff' });
                eq(await cdp.eval("[...document.querySelectorAll('.pair-out .diff-del')].map(n => n.textContent).join('')"), 'B', 'lost character');
                await screenshot(cdp, 'eng-pair');
            });
        } finally {
            agent.stop();
            rmSync(dir, { recursive: true, force: true });
        }
    },

    async harness(cdp, base) {
        await cdp.navigate(`${base}/static/dev/capture-harness.html`);
        await waitFor(() => cdp.eval('window.__ready === true'), { what: 'harness ready' });

        await test('Shift+A, Ctrl+], Enter -> A <GS> <CR>', async () => {
            const r = await scanAndWait(cdp, s => s.type('A').ctrl('BracketRight').enter());
            eq(r.text, 'A\x1d\r', 'decoded text');
            eq(await cdp.eval("document.getElementById('out').textContent"), 'A<GS><CR>', 'visual text');
            const badges = await cdp.eval("[...document.querySelectorAll('#stream .char-badge')].map(b => b.textContent)");
            eq(badges.join(','), 'GS,CR', 'badges in DOM');
        });

        await test('Alt+0029 decodes to GS via alt_numpad', async () => {
            const r = await scanAndWait(cdp, s => s.type('10AB').alt('0029').type('21X').enter());
            eq(r.text, '10AB\x1d21X\r', 'decoded text');
            eq(r.units.find(u => u.abbr === 'GS').via, 'alt_numpad', 'via');
        });

        await test('Tab and FF never move focus or leak; LF via Ctrl+J', async () => {
            const r = await scanAndWait(cdp, s => s.type('X').tab().ctrl('KeyL').enter().ctrl('KeyJ'));
            eq(r.text, 'X\t\x0c\r\n', 'decoded text');
            eq(await cdp.eval("['scan-sink', ''].includes(document.activeElement.id) && !document.activeElement.matches('button, a, select, input')"), true, 'focus did not move to a control');
        });

        await test('Shift capitals do not leak modifier names', async () => {
            const r = await scanAndWait(cdp, s => s.type('ABCdef').enter());
            eq(r.text, 'ABCdef\r', 'decoded text');
        });

        await test('Markup in barcode data is shown as text, not parsed', async () => {
            const r = await scanAndWait(cdp, s => s.type('<b>x</b>').enter());
            eq(r.text, '<b>x</b>\r', 'decoded text');
            eq(await cdp.eval("document.querySelectorAll('#stream b').length"), 0, 'no injected element');
        });
    },
};

async function main() {
    const wanted = process.argv.slice(2);
    const names = wanted.length ? wanted : Object.keys(suites);
    const server = process.env.SCANWISE_URL ? { base: process.env.SCANWISE_URL, stop() {} } : await startServer({ cwd: ROOT });
    const browser = await launchChromium();
    try {
        for (const name of names) {
            if (!suites[name]) throw new Error(`Unknown suite ${name}`);
            console.log(`suite: ${name}`);
            await suites[name](browser.cdp, server.base);
        }
    } finally {
        await browser.close();
        server.stop();
    }
    const failed = results.filter(r => !r[1]).length;
    console.log(`\n${results.length - failed} passed, ${failed} failed`);
    process.exit(failed ? 1 : 0);
}

main().catch(e => { console.error(e); process.exit(1); });
