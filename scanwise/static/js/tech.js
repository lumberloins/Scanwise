/**
 * Tech Mode: one scan proves whether the scanner and the barcode work,
 * in words simple enough to show a nurse.
 */
import { KeyCapture } from './core/capture.js';
import { analyze } from './core/api.js';
import {
    el, clear, streamView, unitNode, hexDump, segmentedView, gs1OrderLine, gs1Table, copyButton,
    unitsToVisualText, componentsView,
} from './core/render.js';

const $ = id => document.getElementById(id);
window.__scans = [];  // read by the e2e tests

const profileSelect = $('profile-select');
const soundToggle = $('sound-toggle');

// Form controls keep focus after use, and capture ignores keys while a form
// control is focused. Hand focus back so the next scan is captured.
for (const ctl of [profileSelect, soundToggle]) ctl.addEventListener('change', () => ctl.blur());

function setZone(state, title, sub) {
    // Once a result is on screen, shrink the scan zone so the answer sits near the top.
    $('scan-zone').className = `scan-zone ${state}${state === 'waiting' ? '' : ' compact'}`;
    $('scan-zone-title').textContent = title;
    $('scan-zone-sub').textContent = sub;
}

function setStatus(id, state, word) {
    const node = $(id);
    node.className = `status status-${state}`;
    node.querySelector('.status-icon').textContent = { ok: '✓', bad: '✗', warn: '!', unknown: '?' }[state];
    node.querySelector('.status-word').textContent = word;
}

/** Turn findings into two plain answers: is the scanner OK, is the barcode OK. */
function judge(res) {
    const serious = res.findings.filter(f => f.severity === 'error' || f.severity === 'warning');
    const scanner = serious.filter(f => f.category === 'SCANNER_CONFIG_FAULT');
    const barcode = serious.filter(f => f.category === 'BARCODE_DATA_FAULT');
    const env = serious.filter(f => f.category === 'ENVIRONMENT_FAULT');
    return {
        scanner: scanner.length ? ['warn', 'Needs setup'] : env.length ? ['warn', 'Working (computer issue)'] : ['ok', 'Working'],
        barcode: barcode.length ? ['bad', 'Problem with label'] : ['ok', 'Read OK'],
    };
}

function framingCell(units, region, framing = {}) {
    const parts = units.filter(u => u.region === region);
    if (!parts.length) {
        const fine = region === 'suffix' && framing.suffix_required === false;
        return [el('span', { class: 'muted', text: fine ? 'Nothing (not needed for this setup)' : 'Nothing' })];
    }
    const words = parts.map(u => u.visible ? u.char : ({ CR: 'Enter', TAB: 'Tab', LF: 'Line feed', GS: 'GS' }[u.abbr] || u.abbr));
    return [el('span', { class: 'framing-badges' }, parts.map(u => unitNode(u))),
        parts.some(u => !u.visible) ? el('span', { class: 'muted', text: `  = ${words.join(' + ')}` }) : null];
}

function renderNothingRead(res) {
    const banner = $('verdict-banner');
    banner.hidden = false;
    banner.className = 'result verdict-error';
    setStatus('status-scanner', 'unknown', 'Keys received, no text');
    setStatus('status-barcode', 'unknown', 'Not read');
    $('verdict-headline').textContent = 'The scanner sent key presses, but no characters could be read from them';
    const keys = [...new Set(res.units.map(u => u.token).filter(Boolean))].slice(0, 12).join(', ');
    $('verdict-recommendation').textContent = `Received: ${keys || 'only modifier keys'}. Open Engineering Mode and scan again to see the raw key events, then send that to IT.`;
    for (const id of ['contents-card', 'data-card', 'config-card']) $(id).hidden = true;
}

function render(res) {
    if (!res.decode || res.decode.char_count === 0) return renderNothingRead(res);
    const cfg = res.config;
    const v = res.verdict;
    const j = judge(res);

    const banner = $('verdict-banner');
    banner.hidden = false;
    banner.className = `result verdict-${v.level}`;
    setStatus('status-scanner', ...j.scanner);
    setStatus('status-barcode', ...j.barcode);
    $('verdict-headline').textContent = v.level === 'success'
        ? 'PASS: the scanner and this barcode are working correctly'
        : v.headline;
    $('verdict-recommendation').textContent = v.level === 'success'
        ? 'The scanner read the barcode completely and sent it correctly. If an application still rejects it, the problem is in that application or its settings.'
        : v.recommendation;

    const g = res.gs1_data;
    $('contents-card').hidden = false;
    $('contents-title').textContent = g && g.elements.length ? "What's in this barcode" : 'Barcode data';
    clear($('contents'), componentsView(res));

    $('data-card').hidden = false;
    clear($('scan-stream'), streamView(res.units));
    clear($('data-tools'), copyButton('Copy', () => unitsToVisualText(res.units)));

    $('config-card').hidden = false;
    clear($('cfg-configured-for'), el('strong', { text: cfg.configured_for }));
    clear($('cfg-prefix'), framingCell(res.units, 'prefix'));
    clear($('cfg-suffix'), framingCell(res.units, 'suffix', res.framing));
    clear($('cfg-aim'), cfg.aim.enabled ? `On: ${cfg.aim.id} (${cfg.aim.symbology})` : 'Off');
    clear($('cfg-gs1'), cfg.gs1_separators.words);

    const todos = res.findings.filter(f => f.severity !== 'info' && f.id !== v.finding_id).map(f => f.tech_hint);
    $('todo-box').hidden = !todos.length;
    clear($('todo-list'), todos.map(t => el('li', { text: t })));

    clear($('cfg-profiles'), cfg.profile_checks.map(p => el('li', { class: p.match ? 'ok' : 'no' },
        el('span', { class: 'mark', text: p.match ? '✓' : '✗' }),
        el('strong', { text: p.name }),
        p.match ? ' matches' : el('span', { class: 'muted', text: ` ${p.reasons.join(' ')}` }))));

    $('gs1-box').hidden = !(g && g.elements.length);
    if (g && g.elements.length) {
        clear($('gs1-segments'), segmentedView(res));
        clear($('gs1-order'), gs1OrderLine(res));
        clear($('gs1-table'), gs1Table(res));
    }

    const t = res.timing;
    $('detail-summary').textContent =
        `${res.decode.char_count} characters · control characters sent as: ${cfg.control_chars.words} · ` +
        `scan took ${t.total_burst_time_ms} ms (${t.description})`;
    clear($('detail-hex'), hexDump(res.units));
}

function playSound(level) {
    if (!soundToggle.checked || !window.scanAudio) return;
    level === 'success' ? window.scanAudio.playPass() : window.scanAudio.playAlert();
}

let latestScan = 0;  // a slow response must never replace a newer scan on screen
const capture = new KeyCapture({
    gapMs: 150,
    onEvent: () => {
        if (capture.events.length === 1) setZone('receiving', 'Receiving scan…', '');
    },
    onScan: async ({ events, meta }) => {
        setZone('analyzing', 'Reading…', '');
        const seq = ++latestScan;
        let res;
        try {
            res = await analyze(events, { profileId: profileSelect.value, client: meta });
        } catch (err) {
            setZone('fail', 'Could not reach the ScanWise server', `${err.message || err}. Check the connection and scan again.`);
            return;
        }
        if (seq !== latestScan) return;
        window.__scans.push(res);
        try {
            render(res);
        } catch (err) {
            console.error(err);
            setZone('fail', 'Could not display this scan', `${err.message || err}. Open Engineering Mode and scan again.`);
            return;
        }
        const n = res.decode ? res.decode.char_count : 0;
        const zoneState = n === 0 ? 'fail' : ({ success: 'pass', warning: 'warn', error: 'fail' }[res.verdict.level] || 'warn');
        setZone(zoneState, n ? 'Scan received. Scan again any time.' : 'Scan received, but nothing readable', `${n} characters received`);
        playSound(n ? res.verdict.level : 'error');
    },
});
capture.arm();

$('clear-btn').addEventListener('click', e => {
    e.currentTarget.blur();
    for (const id of ['verdict-banner', 'contents-card', 'data-card', 'config-card']) $(id).hidden = true;
    setZone('waiting', 'Ready: scan a barcode', 'No need to click anything. Just scan.');
});

window.__ready = true;
