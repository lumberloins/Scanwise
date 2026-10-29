/**
 * Engineering Mode: keystroke-level forensics for HID wedge scanners.
 *
 * Any capture source calls ingest({events, meta, source}). Browser capture is
 * built in; the native agent plugs in through the same call (agent-client.js).
 */
import { KeyCapture, enableKeyboardLock, disableKeyboardLock } from './core/capture.js';
import { analyze } from './core/api.js';
import { AgentClient } from './agent-client.js';
import { el, clear, streamView, unitNode, hexDump, copyButton, unitsToVisualText, unitsToHex, fmtMs, segmentedView, gs1OrderLine, componentsView } from './core/render.js';

const $ = id => document.getElementById(id);
const HISTORY_KEY = 'scanwise.engineering.history.v1';
const HISTORY_MAX = 50;
const EXPORT_FORMAT = 'scanwise-capture';

const VIA_WORDS = {
    key: 'key', enter_key: 'Enter key', named_key: 'named key', ctrl: 'Ctrl emulation',
    alt_numpad: 'Alt+numpad', function_key: 'function key', combo: 'combo', unknown: 'unknown', raw: 'raw text',
};

const state = {
    current: null,      // {res, events, meta, source, id}
    selected: null,
    history: loadHistory(),
    cache: new Map(),   // history id -> analysis result
    liveCount: 0,
    mode: 'browser',    // browser | agent | both
    agent: { client: null, status: null, devices: [], connected: false, error: null },
    pending: { agent: null, browser: null, timer: null },
};
window.__scans = [];
window.scanwise = { ingest, state };   // used by agent-client.js and tests

// ---------------------------------------------------------------- capture

const profileSelect = $('profile-select');
const gapInput = $('gap-input');
for (const ctl of [profileSelect, gapInput]) ctl.addEventListener('change', () => ctl.blur());

const capture = new KeyCapture({
    gapMs: Number(gapInput.value),
    onEvent: ev => { if (state.mode === 'browser') liveEvent(ev); },
    onScan: ({ events, meta }) => routeScan('browser', events, meta),
});
capture.arm();
window.scanwise.capture = capture;

// Agent events go through their own segmenter (never armed: it only receives push()).
const agentCapture = new KeyCapture({
    gapMs: Number(gapInput.value),
    src: 'agent',
    onEvent: ev => { if (state.mode !== 'browser') liveEvent(ev); },
    onScan: ({ events, meta }) => routeScan('agent', events, meta),
});

gapInput.addEventListener('change', () => {
    const v = Math.max(20, Math.min(2000, Number(gapInput.value) || 150));
    gapInput.value = v;
    capture.gapMs = v;
    agentCapture.gapMs = v;
});

$('lock-btn').addEventListener('click', async e => {
    e.currentTarget.blur();
    if (document.fullscreenElement) { disableKeyboardLock(); return; }
    const r = await enableKeyboardLock();
    $('lock-state').textContent = r.locked ? 'On: Ctrl+W/T/N reach the page'
        : r.fullscreen ? 'Fullscreen only (Keyboard Lock API not supported)' : `Failed: ${r.error || 'unknown'}`;
    $('lock-state').className = r.locked ? 'ok-text' : 'warn-text';
});
document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement) { $('lock-state').textContent = 'Off'; $('lock-state').className = 'muted'; }
});

function modsLabel(ev) {
    const m = ev.mods || {};
    return ['ctrl', 'alt', 'shift', 'meta'].filter(k => m[k]).map(k => k[0].toUpperCase() + k.slice(1)).join('+');
}

function liveEvent(ev) {
    const box = $('live-keys');
    if (!state.liveActive) { clear(box); state.liveActive = true; state.liveCount = 0; }
    state.liveCount++;
    if (ev.type !== 'down') return;
    const mods = modsLabel(ev);
    const label = /^(Shift|Control|Alt|Meta)/.test(ev.code) ? ev.code.replace(/Left|Right/, '') : (mods ? `${mods}+${ev.code}` : ev.code);
    box.appendChild(el('span', { class: `live-chip${mods ? ' with-mods' : ''}`, text: label || ev.key || '?' }));
    if (box.childElementCount > 400) box.firstChild.remove();
    box.scrollTop = box.scrollHeight;
}

// ---------------------------------------------------------------- analysis

export async function ingest({ events, meta = {}, source = { kind: 'browser' }, save = true, id = null, pair = null }) {
    state.liveActive = false;
    let res;
    try {
        res = await analyze(events, { profileId: profileSelect.value, client: meta });
    } catch (err) {
        clear($('summary'), el('p', { class: 'warn-text', text: `Analysis failed: ${err.message || err}` }));
        $('summary').hidden = false;
        return null;
    }
    const entry = { id: id || `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`, events, meta, source, res };
    if (pair) {
        entry.pair = pair.events
            ? { ...pair, res: await analyze(pair.events, { profileId: profileSelect.value, client: pair.meta || {} }).catch(() => null) }
            : { missing: true };
    }
    if (entry.pair) applyPairFinding(entry);
    state.current = entry;
    state.cache.set(entry.id, res);
    state.selected = null;
    window.__scans.push(res);
    if (save) addHistory(entry);
    renderAll();
    return res;
}

// ---------------------------------------------------------------- rendering

function renderAll() {
    const { res } = state.current;
    for (const id of ['summary', 'contents-card', 'stream-card', 'tabs-card']) $(id).hidden = false;
    renderSummary();
    const g = res.gs1_data;
    $('contents-title').textContent = g && g.elements.length ? 'Barcode contents (GS1)' : 'Barcode contents';
    clear($('contents'), componentsView(res));
    renderStream();
    renderChars(res);
    renderEvents();
    renderHex(res);
    renderTiming(res);
    renderParsed(res);
    renderFindings(res);
    renderCompare();
    renderHistory();
}

function stat(label, value, cls = '') {
    return el('div', { class: 'stat' }, el('div', { class: 'label', text: label }), el('div', { class: `value ${cls}`, text: value }));
}

function renderSummary() {
    const { res, source, meta } = state.current;
    const v = res.verdict;
    const d = res.decode || {};
    const lvl = { success: 'ok-text', warning: 'warn-text', error: 'err-text' }[v.level] || '';
    clear($('summary'),
        el('div', { class: `summary-verdict verdict-${v.level}` },
            el('strong', { text: v.level === 'success' ? 'PASS' : v.headline }),
            el('span', { class: 'muted', text: ` ${v.recommendation}` })),
        el('div', { class: 'stats' },
            stat('Characters', String(d.char_count ?? res.text.length)),
            stat('Non-char keys', String(d.token_count ?? 0), d.token_count ? 'warn-text' : ''),
            stat('Key events', String(d.event_count ?? 0)),
            stat('Scan duration', fmtMs(res.timing.total_burst_time_ms)),
            stat('Median gap', fmtMs(res.timing.median_inter_char_ms, 2)),
            stat('Control chars via', res.config.control_chars.words),
            stat('Configured for', res.config.configured_for),
            stat('Source', source.kind === 'agent' ? `Agent: ${source.device?.name || '?'}` : source.kind === 'import' ? 'Imported file' : 'Browser'),
            meta.interrupted ? stat('Interrupted', meta.interruption_reason || 'yes', 'err-text') : null,
            state.current.pair ? pairStat(state.current) : null,
            stat('Verdict', v.category, lvl)));
}

function renderStream() {
    const { res } = state.current;
    clear($('stream-box'), streamView(res.units, { onSelect: select }));
    const g = res.gs1_data;
    $('eng-gs1-box').hidden = !(g && g.elements.length);
    if (g && g.elements.length) {
        clear($('eng-gs1-segments'), segmentedView(res, { onSelect: select }));
        clear($('eng-gs1-order'), gs1OrderLine(res));
    }
    const json = JSON.stringify(res.text);
    clear($('stream-tools'),
        copyButton('Copy visual', () => unitsToVisualText(res.units)),
        copyButton('Copy hex', () => res.text_hex),
        copyButton('Copy JSON string', () => json),
        el('button', { class: 'btn btn-secondary btn-small', type: 'button', text: 'Export scan', onclick: e => { e.currentTarget.blur(); exportScans([state.current]); } }));
}

function relT(t) {
    const t0 = state.current.events.length ? state.current.events[0].t : 0;
    return t === null || t === undefined ? '–' : (t - t0).toFixed(2);
}

function renderChars(res) {
    const rows = res.units.map(u => el('tr', { dataset: { unit: u.index }, class: `sev-row-${u.severity}`, onclick: () => select(u.index) },
        el('td', { class: 'num', text: u.index }),
        el('td', null, unitNode(u)),
        el('td', { class: 'mono', text: u.hex ?? '–' }),
        el('td', { class: 'num', text: u.code_point ?? '–' }),
        el('td', { text: u.name }),
        el('td', { text: u.category }),
        el('td', { text: u.region }),
        el('td', { text: VIA_WORDS[u.via] || u.via }),
        el('td', { class: 'mono', text: u.keys ?? '–' }),
        el('td', { class: 'num', text: relT(u.t) }),
        el('td', { class: 'num', text: u.delta_ms ?? '–' }),
        el('td', { class: 'num', text: u.dwell_ms ?? '–' }),
        el('td', { class: 'mono', text: u.host_key ?? '–' }),
        el('td', null, [u.layout_mismatch ? flag('layout', 'err') : null, u.caps_lock_suspected ? flag('caps', 'warn') : null,
            u.repeat ? flag('repeat', 'warn') : null, u.incomplete ? flag('incomplete', 'err') : null,
            u.codepage && u.code_point >= 0x80 ? flag(u.codepage, 'info') : null])));
    clear($('pane-chars'), tableWrap(['#', 'Char', 'Hex', 'Dec', 'Name', 'Category', 'Region', 'Produced by', 'Keys', 't (ms)', 'Δ (ms)', 'Dwell (ms)', 'Host key', 'Flags'], rows));
}

function flag(text, kind) { return el('span', { class: `flag flag-${kind}`, text }); }

function tableWrap(headers, rows, cls = 'eng-table') {
    return el('div', { class: 'table-wrap' }, el('table', { class: cls },
        el('thead', null, el('tr', null, headers.map(h => el('th', { text: h })))), el('tbody', null, rows)));
}

function renderEvents() {
    const { res, events } = state.current;
    const evToUnit = new Map();
    res.units.forEach(u => (u.event_indices || []).forEach(i => evToUnit.set(i, u.index)));
    let prev = null;
    const rows = events.map((ev, i) => {
        const u = evToUnit.get(i);
        const delta = prev === null ? '–' : (ev.t - prev).toFixed(3);
        prev = ev.t;
        return el('tr', { class: `ev-${ev.type}`, dataset: u !== undefined ? { unit: u } : {}, onclick: u !== undefined ? () => select(u) : null },
            el('td', { class: 'num', text: i }),
            el('td', { class: 'num', text: relT(ev.t) }),
            el('td', { class: 'num', text: delta }),
            el('td', { text: ev.type }),
            el('td', { class: 'mono', text: ev.code || '–' }),
            el('td', { class: 'mono', text: ev.key ?? '–' }),
            el('td', { text: modsLabel(ev) || '–' }),
            el('td', { text: ev.repeat ? 'yes' : '' }),
            el('td', { text: ev.src || '' }),
            el('td', { class: 'num', text: u ?? '' }));
    });
    clear($('pane-events'),
        el('p', { class: 'muted small', text: 'Every keydown/keyup exactly as captured. Modifier keys are shown here but never become characters.' }),
        tableWrap(['#', 't (ms)', 'Δ (ms)', 'Type', 'Code (physical)', 'Key (host layout)', 'Modifiers', 'Repeat', 'Source', '→ Char #'], rows));
}

function renderHex(res) {
    clear($('pane-hex'),
        el('div', { class: 'card-tools', dataset: { scanIgnore: '' } },
            copyButton('Copy hex', () => unitsToHex(res.units)),
            copyButton('Copy UTF-8 hex', () => res.text_hex)),
        el('div', { class: 'hexdump-wrap' }, hexDump(res.units, { onSelect: select })),
        el('p', { class: 'muted small', text: 'Hex shows code points (two digits up to 0xFF, U+XXXX above). Non-character keys (tokens) are not part of the byte stream.' }));
}

// Timing chart: inter-key delay per character (single series; spikes use the warning status colour).
function renderTiming(res) {
    const t = res.timing;
    const pane = $('pane-timing');
    const chars = res.units.filter(u => u.kind === 'char');
    if (chars.length < 2) { clear(pane, el('p', { class: 'empty-state', text: 'Need at least two characters for timing.' })); return; }

    const deltas = chars.slice(1).map(u => ({ u, d: u.delta_ms ?? 0 }));
    const thr = t.spike_threshold_ms || 50;
    const maxV = Math.max(thr * 1.15, ...deltas.map(x => x.d)) || 1;
    const W = 960, H = 260, padL = 48, padR = 12, padT = 12, padB = 28;
    const plotW = W - padL - padR, plotH = H - padT - padB;
    const step = plotW / deltas.length;
    const barW = Math.max(1, Math.min(18, step - 2));
    const y = v => padT + plotH - (v / maxV) * plotH;
    const NS = 'http://www.w3.org/2000/svg';
    const svgEl = (tag, attrs) => { const n = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v); return n; };

    const svg = svgEl('svg', { viewBox: `0 0 ${W} ${H}`, class: 'timing-chart', role: 'img', 'aria-label': 'Inter-key delay per character' });
    const ticks = niceTicks(maxV, 4);
    for (const tv of ticks) {
        svg.appendChild(svgEl('line', { x1: padL, x2: W - padR, y1: y(tv), y2: y(tv), class: 'grid' }));
        const lbl = svgEl('text', { x: padL - 6, y: y(tv) + 4, class: 'axis-label', 'text-anchor': 'end' });
        lbl.textContent = `${tv}`;
        svg.appendChild(lbl);
    }
    const unitLbl = svgEl('text', { x: padL - 6, y: padT - 2, class: 'axis-label', 'text-anchor': 'end' });
    unitLbl.textContent = 'ms';
    svg.appendChild(unitLbl);

    const tip = $('tooltip');
    deltas.forEach(({ u, d }, i) => {
        const x = padL + i * step + (step - barW) / 2;
        const top = y(d);
        const h = Math.max(1, padT + plotH - top);
        const r = Math.min(4, barW / 2, h);
        // Rounded data-end, square baseline.
        const path = `M${x},${padT + plotH} V${top + r} Q${x},${top} ${x + r},${top} H${x + barW - r} Q${x + barW},${top} ${x + barW},${top + r} V${padT + plotH} Z`;
        const spike = d > thr;
        svg.appendChild(svgEl('path', { d: path, class: `bar${spike ? ' spike' : ''}`, 'data-unit': u.index }));
        const hit = svgEl('rect', { x: padL + i * step, y: padT, width: step, height: plotH, class: 'hit', 'data-unit': u.index });
        hit.addEventListener('mousemove', e => {
            tip.hidden = false;
            clear(tip, el('div', { class: 'tip-title' }, `#${u.index} `, unitNode(u)),
                el('div', { text: `${d.toFixed(3)} ms after previous character` }),
                spike ? el('div', { class: 'warn-text', text: `⚠ Spike: above ${thr.toFixed(0)} ms threshold` }) : null,
                el('div', { class: 'muted', text: `via ${VIA_WORDS[u.via] || u.via}${u.dwell_ms != null ? ` · dwell ${u.dwell_ms} ms` : ''}` }));
            tip.style.left = `${e.clientX + 14}px`;
            tip.style.top = `${e.clientY + 14}px`;
        });
        hit.addEventListener('mouseleave', () => { tip.hidden = true; });
        hit.addEventListener('click', () => select(u.index));
        svg.appendChild(hit);
        if (deltas.length <= 60) {
            const lbl = svgEl('text', { x: x + barW / 2, y: padT + plotH + 12, class: 'bar-label', 'text-anchor': 'middle' });
            lbl.textContent = u.kind === 'char' && u.visible ? u.char : u.abbr;
            svg.appendChild(lbl);
        }
    });
    svg.appendChild(svgEl('line', { x1: padL, x2: W - padR, y1: y(thr), y2: y(thr), class: 'threshold' }));
    const thrLbl = svgEl('text', { x: W - padR, y: y(thr) - 4, class: 'axis-label', 'text-anchor': 'end' });
    thrLbl.textContent = `spike threshold ${thr.toFixed(0)} ms`;
    svg.appendChild(thrLbl);
    svg.appendChild(svgEl('line', { x1: padL, x2: W - padR, y1: padT + plotH, y2: padT + plotH, class: 'baseline' }));
    const xl = svgEl('text', { x: padL + plotW / 2, y: H - 2, class: 'axis-label', 'text-anchor': 'middle' });
    xl.textContent = 'character (delay measured from the previous character) →';
    svg.appendChild(xl);

    const statsRows = [
        ['Total burst', fmtMs(t.total_burst_time_ms, 2)], ['Median Δ', fmtMs(t.median_inter_char_ms, 3)],
        ['Mean Δ', fmtMs(t.avg_inter_char_ms, 3)], ['Min / max Δ', `${fmtMs(t.min_inter_char_ms, 3)} / ${fmtMs(t.max_inter_char_ms, 3)}`],
        ['p95 Δ', fmtMs(t.p95_inter_char_ms, 3)], ['Std dev', fmtMs(t.stdev_ms, 3)],
        ['Chars / second', t.chars_per_second ?? '–'], ['Spikes', `${t.spikes.length}`],
        ['Dwell (min / median / max)', t.dwell ? `${t.dwell.min_ms} / ${t.dwell.median_ms} / ${t.dwell.max_ms} ms` : '–'],
        ['Assessment', t.description],
    ].map(([k, v]) => el('tr', null, el('th', { text: k }), el('td', { text: String(v) })));
    const histRows = t.histogram.map(h => el('tr', null, el('th', { text: h.label }), el('td', { class: 'num', text: h.count })));

    clear(pane,
        el('h3', { class: 'pane-h', text: 'Inter-key delay per character' }),
        el('div', { class: 'chart-wrap' }, svg),
        el('div', { class: 'two-col' },
            el('div', null, el('h3', { class: 'pane-h', text: 'Statistics' }), el('table', { class: 'kv-table' }, el('tbody', null, statsRows))),
            el('div', null, el('h3', { class: 'pane-h', text: 'Delay histogram' }), el('table', { class: 'kv-table' }, el('tbody', null, histRows)))),
        el('p', { class: 'muted small', text: 'Browser timestamps are event creation times (sub-millisecond, but subject to browser timer coarsening). The native agent provides kernel timestamps.' }));
}

function niceTicks(max, n) {
    const raw = max / n;
    const mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 5, 10].map(m => m * mag).find(s => s >= raw) || raw;
    const out = [];
    for (let v = 0; v <= max + 1e-9; v += step) out.push(Math.round(v * 1000) / 1000);
    return out;
}

function kv(rows) {
    return el('table', { class: 'kv-table' }, el('tbody', null, rows.map(([k, v]) => el('tr', null, el('th', { text: k }), el('td', null, v)))));
}

function framingBadges(res, region) {
    const parts = res.units.filter(u => u.region === region);
    return parts.length ? el('span', null, parts.map(u => unitNode(u, { onSelect: select }))) : el('span', { class: 'muted', text: 'None' });
}

function renderParsed(res) {
    const f = res.framing, s = res.symbology, a = res.anomalies, d = res.decode || {};
    const sections = [
        el('h3', { class: 'pane-h', text: 'Framing' }),
        kv([
            ['Prefix', f.prefix_detected ? [framingBadges(res, 'prefix'), `  ${f.prefix_words} · hex ${f.raw_prefix_hex}`] : 'None'],
            ['Suffix', f.suffix_detected ? [framingBadges(res, 'suffix'), `  ${f.suffix_words} · hex ${f.raw_suffix_hex}`] : 'None'],
            ['Expected profile', f.profile_name ? `${f.profile_name}: ${f.profile_matched ? 'match' : 'MISMATCH. ' + f.profile_reasons.join(' ')}` : 'none (auto-detect)'],
            ['Profiles matched', res.config.matched_profiles.join(', ') || 'none'],
        ]),
        el('h3', { class: 'pane-h', text: 'Symbology' }),
        kv([
            ['AIM ID', s.has_aim_id ? `${s.aim_id}: ${s.symbology_name} (${s.standard})` : 'not transmitted'],
            ['GS1', s.is_gs1 || res.gs1_data ? 'yes' : 'no'],
            ['ISO/IEC 15434', a.iso15434 ? `format ${a.iso15434.format}: ${a.iso15434.format_name}${a.iso15434.terminated ? '' : ' (NOT terminated)'}` : 'no'],
            ['Leading FNC1 (GS)', a.leading_fnc1 ? 'yes' : 'no'],
        ]),
        el('h3', { class: 'pane-h', text: 'Keyboard decode' }),
        kv([
            ['Control-char method', `${res.config.control_chars.words}  ${JSON.stringify(d.control_methods || {})}`],
            ['Produced by (all chars)', Object.entries(d.via_counts || {}).map(([k, v]) => `${VIA_WORDS[k] || k}: ${v}`).join(' · ') || '–'],
            ['Layout mismatches', String(d.layout_mismatch_count ?? 0) + ((d.layout_mismatch_examples || []).length
                ? ` (e.g. ${d.layout_mismatch_examples.map(x => `${x.keys}: expected ${JSON.stringify(x.expected)}, host gave ${JSON.stringify(x.host_produced)}`).join('; ')})` : '')],
            ['Caps Lock suspected', d.caps_lock_suspected ? 'yes' : 'no'],
            ['Non-character keys', (d.tokens || []).join(', ') || 'none'],
            ['Unknown key codes', (d.unknown_keys || []).join(', ') || 'none'],
            ['Notes', (d.notes || []).join(' ') || '–'],
        ]),
    ];
    if (res.gs1_data) {
        const g = res.gs1_data, det = res.gs1_detection || {};
        const TERM = { predefined: 'predefined length', gs: 'GS', end: 'end of data', missing_gs: 'GS MISSING', hri: 'bracket', url: 'URL' };
        const rows = g.elements.map(e => el('tr', { onclick: () => { const u = res.units.find(x => x.gs1_element === e.index); if (u) select(u.index); } },
            el('td', { class: 'num', text: e.index + 1 }),
            el('td', { class: 'mono', text: `(${e.ai})` }), el('td', { text: e.title }), el('td', { class: 'mono', text: e.spec }),
            el('td', { class: 'mono', text: e.value }), el('td', { text: e.formatted_value !== e.value ? e.formatted_value : '' }),
            el('td', { class: 'num', text: e.start ?? '–' }),
            el('td', null, flag(e.boundary_guessed ? 'GS missing (guessed)' : TERM[e.terminator] || e.terminator,
                e.boundary_guessed || e.terminator === 'missing_gs' ? 'err' : 'info'),
                e.gs_unnecessary ? flag('extra GS', 'info') : null),
            el('td', null, [
                e.unknown ? flag('unknown AI', 'err') : null,
                'check_digit_valid' in e ? flag(e.check_digit_valid ? 'check ok' : 'BAD check digit', e.check_digit_valid ? 'info' : 'err') : null,
                e.date_info ? flag(e.date_info.valid ? (e.date_info.expired ? 'expired' : e.date_info.rule) : 'invalid date', e.date_info.valid ? 'info' : 'err') : null,
                ...(e.issues || []).filter(i => !/check digit|date|Invalid month/i.test(i)).map(i => flag(i, 'err'))])));
        sections.push(el('h3', { class: 'pane-h', text: 'GS1 element string' }),
            kv([
                ['Detected as GS1', `${det.is_gs1 ? 'yes' : 'no'} (${det.confidence}): ${det.reason || ''}`],
                ['Input form', { raw: 'raw element string', hri: 'bracketed human-readable', digital_link: 'GS1 Digital Link URI' }[g.form] || g.form],
                ['Leading FNC1', g.leading_fnc1 ? 'yes' : 'no'],
                ['Separators (GS) at', g.separators.length ? g.separators.join(', ') : 'none'],
                ['Order', `${g.order.map(a => `(${a})`).join(' → ')}${g.typical_order ? '' : '  (primary key not first, still valid GS1)'}`],
                ['Missing separators', g.missing_separators.length ? g.missing_separators.map(m => `${m.definite ? 'DEFINITE' : 'possible'}: after (${m.after_ai}) ${JSON.stringify(m.value)} → (${m.next_ai})`).join('; ') : 'none'],
            ]),
            tableWrap(['#', 'AI', 'Field', 'Format', 'Value', 'Means', 'Pos', 'Ended by', 'Checks'], rows),
            el('p', { class: 'muted small', text: 'GS1 allows fields in any order. Fields whose AI starts with 00-04, 11-20, 31-36 or 41 have predefined lengths and never need a GS; every other field must be followed by GS unless it is last.' }));
    }
    clear($('pane-parsed'), sections);
}

function renderFindings(res) {
    $('findings-count').textContent = res.findings.length ? String(res.findings.length) : '';
    if (!res.findings.length) { clear($('pane-findings'), el('p', { class: 'ok-text', text: 'No findings. Everything checks out.' })); return; }
    clear($('pane-findings'), res.findings.map(f => el('div', { class: `finding finding-${f.severity}` },
        el('div', { class: 'finding-head' }, flag(f.severity, { error: 'err', warning: 'warn', info: 'info' }[f.severity]),
            el('strong', { text: ` ${f.title}` }), el('span', { class: 'muted', text: `  ${f.category} · ${f.id}` })),
        el('p', { text: f.detail }),
        f.tech_hint !== f.detail ? el('p', { class: 'muted', text: `Tech wording: ${f.tech_hint}` }) : null,
        Object.keys(f.evidence || {}).length ? el('pre', { class: 'evidence', text: JSON.stringify(f.evidence, null, 1) }) : null,
        (f.evidence?.indices || []).length ? el('button', { class: 'btn btn-secondary btn-small', type: 'button', text: 'Show in stream',
            onclick: e => { e.currentTarget.blur(); select(res.units.find(u => u.char_index === f.evidence.indices[0])?.index ?? null); } }) : null)));
}

// ---------------------------------------------------------------- selection

function select(index) {
    state.selected = index;
    document.querySelectorAll('.selected').forEach(n => n.classList.remove('selected'));
    if (index === null || index === undefined) return;
    document.querySelectorAll(`[data-unit="${index}"]`).forEach(n => n.classList.add('selected'));
    const row = document.querySelector(`#pane-chars tr[data-unit="${index}"]`);
    if (row && $('pane-chars').classList.contains('active')) row.scrollIntoView({ block: 'nearest' });
}

document.querySelectorAll('.eng-tab').forEach(btn => btn.addEventListener('click', () => {
    btn.blur();
    document.querySelectorAll('.eng-tab').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.eng-pane').forEach(p => p.classList.toggle('active', p.id === `pane-${btn.dataset.tab}`));
}));

// ---------------------------------------------------------------- history, export, import

function loadHistory() {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); } catch { return []; }
}
function saveHistory() {
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(state.history)); } catch { /* storage full or blocked */ }
}

function addHistory(entry) {
    const v = entry.res.verdict;
    state.history.unshift({
        id: entry.id, savedAt: new Date().toISOString(), events: entry.events, meta: entry.meta, source: entry.source,
        summary: { level: v.level, headline: v.level === 'success' ? 'PASS' : v.headline, visual: unitsToVisualText(entry.res.units).slice(0, 160),
            chars: entry.res.decode?.char_count ?? entry.res.text.length },
    });
    state.history = state.history.slice(0, HISTORY_MAX);
    saveHistory();
}

async function resultFor(h) {
    if (!state.cache.has(h.id)) state.cache.set(h.id, await analyze(h.events, { profileId: profileSelect.value, client: h.meta }));
    return state.cache.get(h.id);
}

function renderHistory() {
    const box = $('history-box');
    if (!state.history.length) { clear(box, el('p', { class: 'empty-state', text: 'No scans yet.' })); return; }
    const rows = state.history.map(h => el('tr', { class: state.current && state.current.id === h.id ? 'current' : '' },
        el('td', { class: 'num', text: new Date(h.savedAt).toLocaleTimeString() }),
        el('td', null, flag(h.summary.level === 'success' ? 'pass' : h.summary.level, { success: 'info', warning: 'warn', error: 'err' }[h.summary.level])),
        el('td', { text: h.summary.headline }),
        el('td', { class: 'num', text: h.summary.chars }),
        el('td', { text: h.source?.kind || '' }),
        el('td', { class: 'mono trunc', text: h.summary.visual }),
        el('td', { class: 'row-actions' },
            el('button', { class: 'btn btn-secondary btn-small', type: 'button', text: 'View', onclick: e => { e.currentTarget.blur(); ingest({ ...h, save: false }); } }),
            el('button', { class: 'btn btn-secondary btn-small', type: 'button', text: 'A', title: 'Compare: set as A', onclick: e => { e.currentTarget.blur(); state.compareA = h.id; renderCompare(); showTab('compare'); } }),
            el('button', { class: 'btn btn-secondary btn-small', type: 'button', text: 'B', title: 'Compare: set as B', onclick: e => { e.currentTarget.blur(); state.compareB = h.id; renderCompare(); showTab('compare'); } }),
            el('button', { class: 'btn btn-secondary btn-small', type: 'button', text: '✕', title: 'Delete', onclick: e => { e.currentTarget.blur(); state.history = state.history.filter(x => x.id !== h.id); saveHistory(); renderHistory(); } }))));
    clear(box, tableWrap(['Time', 'Result', 'Headline', 'Chars', 'Source', 'Data', ''], rows));
}

function showTab(name) { document.querySelector(`.eng-tab[data-tab="${name}"]`)?.click(); }

function exportScans(entries) {
    const doc = {
        format: EXPORT_FORMAT, version: 1, exported_at: new Date().toISOString(),
        scans: entries.map(e => ({ id: e.id, saved_at: e.savedAt || new Date().toISOString(), source: e.source, meta: e.meta, events: e.events })),
    };
    const blob = new Blob([JSON.stringify(doc, null, 1)], { type: 'application/json' });
    const a = el('a', { href: URL.createObjectURL(blob), download: `scanwise-${new Date().toISOString().replace(/[:.]/g, '-')}.json` });
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

$('export-all-btn').addEventListener('click', e => { e.currentTarget.blur(); exportScans(state.history); });
$('clear-history-btn').addEventListener('click', e => { e.currentTarget.blur(); state.history = []; saveHistory(); renderHistory(); });
$('import-input').addEventListener('change', async e => {
    const file = e.target.files[0];
    e.target.value = '';
    if (!file) return;
    try {
        await importDocument(JSON.parse(await file.text()));
    } catch (err) {
        clear($('history-box'), el('p', { class: 'err-text', text: `Import failed: ${err.message || err}` }));
    }
});

export async function importDocument(doc) {
    if (!doc || doc.format !== EXPORT_FORMAT || !Array.isArray(doc.scans)) throw new Error(`not a ${EXPORT_FORMAT} file`);
    const scans = doc.scans.filter(s => Array.isArray(s.events));
    for (const s of scans.slice().reverse()) {
        await ingest({ events: s.events, meta: s.meta || {}, source: { ...(s.source || {}), kind: s.source?.kind || 'import', imported: true } });
    }
    return scans.length;
}
window.scanwise.importDocument = importDocument;

// ---------------------------------------------------------------- compare

function sig(u) { return u.kind === 'char' ? `c${u.code_point}` : `t${u.token}`; }

/** LCS alignment of two unit lists -> ops [{op: same|del|add, a, b}]. */
export function diffUnits(A, B) {
    const n = A.length, m = B.length;
    if (n * m > 4e6) return null;
    const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
        dp[i][j] = sig(A[i]) === sig(B[j]) ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    const ops = [];
    let i = 0, j = 0;
    while (i < n && j < m) {
        if (sig(A[i]) === sig(B[j])) ops.push({ op: 'same', a: A[i++], b: B[j++] });
        else if (dp[i + 1][j] >= dp[i][j + 1]) ops.push({ op: 'del', a: A[i++] });
        else ops.push({ op: 'add', b: B[j++] });
    }
    while (i < n) ops.push({ op: 'del', a: A[i++] });
    while (j < m) ops.push({ op: 'add', b: B[j++] });
    return ops;
}

function pairCounts(entry) {
    if (!entry.pair || entry.pair.missing || !entry.pair.res) return null;
    const ops = diffUnits(entry.res.units, entry.pair.res.units);
    if (!ops) return null;
    const c = { same: 0, del: 0, add: 0 };
    ops.forEach(o => c[o.op]++);
    return c;
}

/** Agent-vs-browser loss is an environment fault the server can't see: make it the headline. */
function applyPairFinding(entry) {
    const c = entry.pair.missing ? null : pairCounts(entry);
    let finding = null;
    if (entry.pair.missing) {
        finding = { id: 'browser_received_nothing', title: 'Browser received none of the keystrokes the scanner sent',
            detail: 'The agent captured this scan at the OS input layer, but the page saw no key events. The page was not focused, the agent grab is on, or something between the OS and the browser (remote session, keyboard hook, security software) swallowed the input.' };
    } else if (c && (c.del || c.add)) {
        finding = { id: 'browser_lost_chars', title: `Browser lost ${c.del} and gained ${c.add} character(s) vs the device`,
            detail: 'The device sent the agent\'s stream; the page received something different. The scanner is not at fault: look at the OS/VDI/browser path (inter-character delay, keyboard hooks, remote-session channels).' };
    }
    if (!finding) return;
    const f = { ...finding, severity: 'error', category: 'ENVIRONMENT_FAULT', tech_hint: finding.detail, evidence: c || {} };
    entry.res.findings = [f, ...entry.res.findings];
    entry.res.verdict = { category: f.category, level: 'error', headline: f.title, recommendation: f.detail, finding_id: f.id };
}

function pairStat(entry) {
    if (entry.pair.missing) return stat('Agent vs browser', 'Browser received nothing', 'err-text');
    const c = pairCounts(entry);
    if (!c) return stat('Agent vs browser', 'n/a');
    if (!c.del && !c.add) return stat('Agent vs browser', 'Identical', 'ok-text');
    return stat('Agent vs browser', `${c.del} lost, ${c.add} extra in browser`, 'err-text');
}

/** Render an aligned diff of two analysis results into `out`. */
function renderDiff(out, rA, rB, labelA, labelB, srcA, srcB) {
    const ops = diffUnits(rA.units, rB.units);
    if (!ops) { out.appendChild(el('p', { class: 'warn-text', text: 'Scans too long to align.' })); return; }
    const counts = { same: 0, del: 0, add: 0 };
    ops.forEach(o => counts[o.op]++);
    out.appendChild(el('p', null, el('strong', { text: counts.del + counts.add === 0 ? 'Identical character streams.'
        : `${counts.del} only in ${labelA}, ${counts.add} only in ${labelB}, ${counts.same} identical.` })));
    out.appendChild(el('div', { class: 'diff-stream' }, ops.map(o => el('span', { class: `diff-${o.op}`,
        title: o.op === 'same' ? 'in both' : o.op === 'del' ? `only in ${labelA}` : `only in ${labelB}` }, unitNode(o.a || o.b)))));
    const field = (label, fa, fb) => el('tr', { class: fa === fb ? '' : 'diff-row' }, el('th', { text: label }), el('td', { text: fa }), el('td', { text: fb }));
    out.appendChild(el('table', { class: 'kv-table compare-table' },
        el('thead', null, el('tr', null, el('th'), el('th', { text: labelA }), el('th', { text: labelB }))), el('tbody', null,
            field('Verdict', rA.verdict.headline, rB.verdict.headline),
            field('Prefix', rA.framing.prefix_words, rB.framing.prefix_words),
            field('Suffix', rA.framing.suffix_words, rB.framing.suffix_words),
            field('AIM', rA.config.aim.words, rB.config.aim.words),
            field('Control chars via', rA.config.control_chars.words, rB.config.control_chars.words),
            field('Median Δ', fmtMs(rA.timing.median_inter_char_ms, 2), fmtMs(rB.timing.median_inter_char_ms, 2)),
            field('Duration', fmtMs(rA.timing.total_burst_time_ms), fmtMs(rB.timing.total_burst_time_ms)),
            field('Source', srcA, srcB))));
}

function sourceLabel(src) {
    if (!src) return '';
    return src.kind === 'agent' ? `agent: ${src.device?.name || src.device?.id || '?'}` : src.kind;
}

async function renderCompare() {
    const pane = $('pane-compare');
    const sections = [];
    const cur = state.current;
    if (cur && cur.pair) {
        const out = el('div', { class: 'compare-out pair-out' });
        sections.push(el('h3', { class: 'pane-h', text: 'This scan: agent (ground truth) vs browser' }),
            el('p', { class: 'muted small', text: 'The agent reads the device directly; the browser sees what survived the OS, remote-session and browser layers. Characters only in the agent were lost on the way to the page.' }), out);
        if (cur.pair.missing) {
            out.appendChild(el('p', { class: 'err-text', text: 'The agent captured this scan but the browser received no key events. Either the page was not focused, the device is grabbed by the agent, or something between the OS and the browser swallowed the input.' }));
        } else if (cur.pair.res) {
            renderDiff(out, cur.res, cur.pair.res, 'agent', 'browser', sourceLabel(cur.source), 'browser');
        }
    }

    const opts = (sel) => state.history.map(h => el('option', { value: h.id, selected: h.id === sel ? true : null,
        text: `${new Date(h.savedAt).toLocaleTimeString()} · ${h.summary.visual.slice(0, 40)}` }));
    const selA = el('select', { class: 'profile-dropdown' }, el('option', { value: '', text: 'Pick scan A' }), opts(state.compareA));
    const selB = el('select', { class: 'profile-dropdown' }, el('option', { value: '', text: 'Pick scan B' }), opts(state.compareB));
    selA.addEventListener('change', () => { state.compareA = selA.value; selA.blur(); renderCompare(); });
    selB.addEventListener('change', () => { state.compareB = selB.value; selB.blur(); renderCompare(); });
    const out = el('div', { class: 'compare-out history-out' });
    sections.push(el('h3', { class: 'pane-h', text: 'Compare two scans from history' }),
        el('div', { class: 'compare-pick', dataset: { scanIgnore: '' } }, 'A ', selA, '  B ', selB),
        el('p', { class: 'muted small', text: 'Character-level alignment. Use it to compare two scanners on the same label, or the same scanner before and after reprogramming.' }), out);
    clear(pane, sections);

    const hA = state.history.find(h => h.id === state.compareA), hB = state.history.find(h => h.id === state.compareB);
    if (!hA || !hB) { out.appendChild(el('p', { class: 'empty-state', text: 'Pick two scans (or use the A / B buttons in Session history).' })); return; }
    const [rA, rB] = await Promise.all([resultFor(hA), resultFor(hB)]);
    renderDiff(out, rA, rB, 'A', 'B', sourceLabel(hA.source), sourceLabel(hB.source));
}

// ---------------------------------------------------------------- capture source routing & agent

const PAIR_WINDOW_MS = 1000;

function routeScan(kind, events, meta) {
    if (state.mode === 'browser') {
        if (kind === 'browser') ingest({ events, meta, source: { kind: 'browser', userAgent: navigator.userAgent } });
        return;
    }
    if (state.mode === 'agent') {
        if (kind === 'agent') ingest({ events, meta, source: agentSource() });
        return;  // browser keys are still swallowed (preventDefault) but not analysed
    }
    // both: pair an agent scan with the browser scan that arrives within PAIR_WINDOW_MS
    const p = state.pending;
    p[kind] = { events, meta };
    if (p.agent && p.browser) return flushPair();
    clearTimeout(p.timer);
    p.timer = setTimeout(flushPair, PAIR_WINDOW_MS);
}

function flushPair() {
    const p = state.pending;
    clearTimeout(p.timer);
    const a = p.agent, b = p.browser;
    p.agent = p.browser = null;
    if (a) ingest({ events: a.events, meta: a.meta, source: agentSource(), pair: b ? { events: b.events, meta: b.meta } : { missing: true } });
    else if (b) ingest({ events: b.events, meta: { ...b.meta, note: 'agent saw nothing (wrong device selected?)' }, source: { kind: 'browser', userAgent: navigator.userAgent } });
}

function agentSource() {
    const sel = state.agent.status && state.agent.status.selected;
    return { kind: 'agent', device: sel || null, grab: !!(state.agent.status && state.agent.status.grab), platform: state.agent.status?.platform };
}

function agentUrl() {
    try { return localStorage.getItem('scanwise.agent.url') || 'http://127.0.0.1:47800'; } catch { return 'http://127.0.0.1:47800'; }
}

function renderSourcePanel() {
    const a = state.agent;
    const modeSel = el('select', { class: 'profile-dropdown', id: 'source-mode' },
        [['browser', 'Browser capture'], ['agent', 'Native agent'], ['both', 'Both (agent vs browser)']]
            .map(([v, t]) => el('option', { value: v, text: t, selected: state.mode === v ? true : null })));
    modeSel.addEventListener('change', () => { modeSel.blur(); setMode(modeSel.value); });
    const parts = [modeSel];

    if (state.mode !== 'browser') {
        const urlIn = el('input', { class: 'url-input', id: 'agent-url', value: agentUrl(), title: 'Agent address' });
        urlIn.addEventListener('change', () => {
            try { localStorage.setItem('scanwise.agent.url', urlIn.value); } catch {}
            urlIn.blur();
            connectAgent();
        });
        parts.push(urlIn);
        if (a.error) {
            parts.push(el('div', { class: 'agent-msg err-text', text: a.error }));
        } else if (a.connected) {
            const devSel = el('select', { class: 'profile-dropdown', id: 'agent-device' },
                el('option', { value: '', text: a.devices.length ? 'Select a device…' : 'No devices' }),
                a.devices.map(d => el('option', { value: d.id, selected: a.status?.selected?.id === d.id ? true : null,
                    text: `${d.likely_scanner ? '★ ' : ''}${d.name || d.id}${d.vendor_id ? ` (${d.vendor_id}:${d.product_id})` : ''}` })));
            const grab = el('input', { type: 'checkbox', id: 'agent-grab', checked: a.status?.grab ? true : null });
            const sel = a.devices.find(d => d.id === (a.status?.selected?.id || devSel.value));
            grab.disabled = sel ? !sel.can_grab : false;
            const apply = async () => {
                devSel.blur(); grab.blur();
                if (!devSel.value) { await a.client.release().catch(() => {}); return refreshAgent(); }
                try { a.status = await a.client.select(devSel.value, grab.checked); a.error = null; }
                catch (err) { a.error = `Select failed: ${err.message}`; }
                renderSourcePanel();
            };
            devSel.addEventListener('change', apply);
            grab.addEventListener('change', apply);
            parts.push(devSel, el('label', { class: 'toggle', title: 'Exclusive grab (Linux): scans stop typing into other apps. Turn off for agent-vs-browser comparison.' }, grab, ' Grab'));
            if (a.deviceErrors?.length) parts.push(el('div', { class: 'agent-msg warn-text', text: a.deviceErrors.join(' ') }));
            parts.push(el('div', { class: 'agent-msg muted', text: a.status?.selected
                ? `Streaming ${a.status.selected.name || a.status.selected.id}${a.status.grab ? ' (grabbed)' : ''} · agent ${a.status.version} on ${a.status.platform}`
                : `Connected to agent ${a.status?.version || ''}. Pick the scanner (★ = looks like a scanner).` }));
        } else {
            parts.push(el('div', { class: 'agent-msg muted', text: 'Connecting…' }));
        }
    }
    clear($('source-panel'), el('div', { class: 'source-controls' }, parts));
    const live = state.mode === 'browser' || (state.agent.connected && state.agent.status?.selected);
    clear($('capture-state'), el('span', { class: `dot ${live ? 'dot-live' : 'dot-warn'}` }),
        state.mode === 'browser' ? 'Armed: scan anywhere on this page'
            : live ? (state.mode === 'both' ? 'Armed: agent + browser (keep this page focused, grab off)' : 'Armed: scanning via agent')
                : 'Waiting for agent device');
}

async function refreshAgent() {
    const a = state.agent;
    try {
        a.status = await a.client.status();
        const d = await a.client.devices();
        a.devices = d.devices || [];
        a.deviceErrors = d.errors || [];
        a.connected = true;
        a.error = null;
    } catch (err) {
        a.connected = false;
        a.error = `Agent not reachable at ${a.client.base} (${err.message}). Start it with: scanwise-agent -allow-origin ${location.origin}`;
    }
    renderSourcePanel();
}

async function connectAgent() {
    const a = state.agent;
    if (a.client) a.client.disconnect();
    a.client = new AgentClient(agentUrl());
    a.connected = false;
    renderSourcePanel();
    await refreshAgent();
    if (!a.connected) return;
    a.client.connect({
        onKey: ev => agentCapture.push(ev),
        onStatus: st => { a.status = st; renderSourcePanel(); },
        onError: () => { if (state.mode !== 'browser') { a.error = 'Lost connection to agent; retrying…'; renderSourcePanel(); } },
    });
}

function setMode(mode) {
    state.mode = mode;
    if (mode === 'browser') {
        if (state.agent.client) state.agent.client.disconnect();
        state.agent.connected = false;
        renderSourcePanel();
    } else {
        connectAgent();
    }
}
window.scanwise.setMode = setMode;
renderSourcePanel();

window.scanwise.renderCompare = renderCompare;
renderHistory();
window.__ready = true;
