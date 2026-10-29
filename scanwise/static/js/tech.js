/**
 * Tech Mode: scan once, learn how the scanner is configured.
 */
import { KeyCapture } from './core/capture.js';
import { analyze } from './core/api.js';
import { el, clear, streamView, unitNode, hexDump, segmentedView, gs1OrderLine, gs1Table, copyButton, unitsToVisualText } from './core/render.js';

const $ = id => document.getElementById(id);
window.__scans = [];  // read by the e2e tests

const profileSelect = $('profile-select');
const soundToggle = $('sound-toggle');

// Form controls keep focus after use, and capture ignores keys while a form
// control is focused. Hand focus back so the next scan is captured.
for (const ctl of [profileSelect, soundToggle]) ctl.addEventListener('change', () => ctl.blur());

function setZone(state, title, sub) {
    const zone = $('scan-zone');
    zone.className = `scan-zone ${state}`;
    $('scan-zone-title').textContent = title;
    $('scan-zone-sub').textContent = sub;
}

/** Badges for the prefix/suffix units, followed by the words. */
function framingCell(units, region, words) {
    const parts = units.filter(u => u.region === region);
    if (!parts.length) return [el('span', { class: 'muted', text: 'None' })];
    const out = [el('span', { class: 'framing-badges' }, parts.map(u => unitNode(u)))];
    // Spell out control characters ("CR (Enter) + LF"); printable text speaks for itself.
    if (parts.some(u => !u.visible)) out.push(el('span', { class: 'muted', text: `  = ${words}` }));
    return out;
}

function render(res) {
    const cfg = res.config;
    const v = res.verdict;

    const banner = $('verdict-banner');
    banner.hidden = false;
    banner.className = `verdict-banner verdict-${v.level}`;
    $('verdict-headline').textContent = v.level === 'success' ? 'PASS: scanner and barcode look correct' : v.headline;
    $('verdict-recommendation').textContent = v.recommendation;

    $('config-card').hidden = false;
    clear($('cfg-configured-for'), el('strong', { text: cfg.configured_for }));
    clear($('cfg-prefix'), framingCell(res.units, 'prefix', cfg.prefix.words));
    clear($('cfg-suffix'), framingCell(res.units, 'suffix', cfg.suffix.words));
    clear($('cfg-aim'), cfg.aim.enabled ? `On: ${cfg.aim.id} (${cfg.aim.symbology})` : 'Off');
    clear($('cfg-gs1'), cfg.gs1_separators.words);

    clear($('cfg-profiles'), cfg.profile_checks.map(p => el('li', { class: p.match ? 'ok' : 'no' },
        el('span', { class: 'mark', text: p.match ? '✓' : '✗' }),
        el('strong', { text: p.name }),
        p.match ? ' matches' : el('span', { class: 'muted', text: ` ${p.reasons.join(' ')}` }))));

    $('data-card').hidden = false;
    clear($('scan-stream'), streamView(res.units));
    clear($('data-tools'), copyButton('Copy with tags', () => unitsToVisualText(res.units)));
    const g = res.gs1_data;
    $('gs1-box').hidden = !(g && g.elements.length);
    if (g && g.elements.length) {
        clear($('gs1-segments'), segmentedView(res));
        clear($('gs1-order'), gs1OrderLine(res));
        clear($('gs1-table'), gs1Table(res));
    }

    // The banner already shows the top finding; list the rest.
    const todos = res.findings.filter(f => f.severity !== 'info' && f.id !== v.finding_id).map(f => f.tech_hint);
    $('todo-box').hidden = !todos.length;
    clear($('todo-list'), todos.map(t => el('li', { text: t })));

    const t = res.timing;
    $('detail-summary').textContent =
        `${res.decode ? res.decode.char_count : res.text.length} characters · ` +
        `control characters sent as: ${cfg.control_chars.words} · ` +
        `scan took ${t.total_burst_time_ms} ms (${t.description})`;
    clear($('detail-hex'), hexDump(res.units));
}

function playSound(level) {
    if (!soundToggle.checked || !window.scanAudio) return;
    level === 'success' ? window.scanAudio.playPass() : window.scanAudio.playAlert();
}

const capture = new KeyCapture({
    gapMs: 150,
    onEvent: () => {
        if (capture.events.length === 1) setZone('receiving', 'Receiving scan…', '');
    },
    onScan: async ({ events, meta }) => {
        setZone('analyzing', 'Analyzing…', '');
        try {
            const res = await analyze(events, { profileId: profileSelect.value, client: meta });
            window.__scans.push(res);
            render(res);
            const zoneState = { success: 'pass', warning: 'warn', error: 'fail' }[res.verdict.level] || 'warn';
            setZone(zoneState, 'Scan received. Scan again any time.', `${res.decode.char_count} characters received`);
            playSound(res.verdict.level);
        } catch (err) {
            setZone('fail', 'Could not analyze scan', String(err.message || err));
        }
    },
});
capture.arm();

$('clear-btn').addEventListener('click', e => {
    e.currentTarget.blur();
    $('verdict-banner').hidden = true;
    $('data-card').hidden = true;
    $('config-card').hidden = true;
    setZone('waiting', 'Ready: scan a barcode', 'No need to click anything. Just scan.');
});

window.__ready = true;
