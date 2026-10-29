/**
 * ScanWise DOM rendering helpers.
 *
 * All text goes through text nodes, never innerHTML, so scanned data (and
 * labels like <GS>) can never be parsed as markup.
 */

export function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
        if (v === null || v === undefined || v === false) continue;
        if (k === 'class') node.className = v;
        else if (k === 'dataset') Object.assign(node.dataset, v);
        else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
        else if (k === 'text') node.textContent = v;
        else node.setAttribute(k, v === true ? '' : v);
    }
    append(node, children);
    return node;
}

function append(node, children) {
    for (const c of children.flat(Infinity)) {
        if (c === null || c === undefined || c === false) continue;
        node.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
    }
}

export function clear(node, ...children) {
    node.replaceChildren();
    append(node, children);
    return node;
}

/** Tooltip text for a unit. */
export function unitTitle(u) {
    const parts = [u.name];
    if (u.hex) parts.push(`0x${u.hex}`);
    if (u.keys) parts.push(`keys: ${u.keys}`);
    if (u.via) parts.push(`via: ${u.via}`);
    if (u.region) parts.push(`region: ${u.region}`);
    return parts.join(' · ');
}

/** One unit as either plain text or a badge. Every non-visible character becomes a badge. */
export function unitNode(u, { onSelect } = {}) {
    let node;
    if (u.kind === 'char' && u.visible) {
        node = el('span', { class: `ch region-${u.region}${u.char === ' ' ? ' ch-space' : ''}`, text: u.char === ' ' ? '·' : u.char });
    } else {
        const label = u.kind === 'token' ? `[${u.abbr}]` : u.abbr;
        node = el('span', { class: `char-badge cat-${u.category} sev-${u.severity} region-${u.region}`, text: label });
    }
    node.title = unitTitle(u);
    node.dataset.unit = u.index;
    if (onSelect) {
        node.classList.add('selectable');
        node.addEventListener('click', ev => { ev.stopPropagation(); onSelect(u.index); });
    }
    return node;
}

export function streamView(units, opts = {}) {
    const box = el('div', { class: 'stream' });
    if (!units.length) box.appendChild(el('span', { class: 'empty-state', text: '(no characters)' }));
    units.forEach(u => box.appendChild(unitNode(u, opts)));
    return box;
}

/** Badge for a control character abbreviation (for legends / framing words). */
export function abbrBadge(abbr, category = 'terminator') {
    return el('span', { class: `char-badge cat-${category}`, text: abbr });
}

/** Plain text with every non-visible character written as <ABBR>, for copying. */
export function unitsToVisualText(units) {
    return units.map(u => (u.kind === 'char' && u.visible) ? u.char : `<${u.abbr}>`).join('');
}

export function unitsToHex(units) {
    return units.filter(u => u.kind === 'char').map(u => u.hex).join(' ');
}

/** xxd-style dump: offset | 16 hex cells | ASCII column with badges. */
export function hexDump(units, { onSelect, width = 16 } = {}) {
    const chars = units.filter(u => u.kind === 'char');
    const table = el('table', { class: 'hexdump' });
    for (let off = 0; off < chars.length; off += width) {
        const row = chars.slice(off, off + width);
        const hexCells = row.map(u => el('td', {
            class: `hx cat-${u.category}`, dataset: { unit: u.index }, title: unitTitle(u), text: u.hex,
            onclick: onSelect ? () => onSelect(u.index) : null,
        }));
        while (hexCells.length < width) hexCells.push(el('td', { class: 'hx pad' }));
        const ascii = el('td', { class: 'ascii' }, row.map(u => unitNode(u, { onSelect })));
        table.appendChild(el('tr', null,
            el('td', { class: 'off', text: off.toString(16).padStart(4, '0') }), hexCells, ascii));
    }
    if (!chars.length) table.appendChild(el('tr', null, el('td', { class: 'empty-state', text: '(empty)' })));
    return table;
}

export function copyButton(label, getText) {
    const btn = el('button', { class: 'btn btn-secondary btn-small', type: 'button', text: label });
    btn.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(getText());
            btn.textContent = 'Copied!';
        } catch {
            btn.textContent = 'Copy failed';
        }
        setTimeout(() => { btn.textContent = label; }, 1500);
        btn.blur();
    });
    return btn;
}

export function fmtMs(v, digits = 1) {
    return v === null || v === undefined ? '–' : `${Number(v).toFixed(digits)} ms`;
}

const TERMINATOR_WORDS = {
    predefined: 'fixed length, no GS needed',
    gs: 'ended by GS',
    end: 'last field',
    missing_gs: 'GS MISSING',
    hri: 'bracketed',
    url: 'from URL',
};

function segmentKey(u) {
    if (u.kind === 'token') return `token:${u.index}`;
    if (u.region === 'prefix' || u.region === 'aim' || u.region === 'suffix') return u.region;
    if (u.gs1_part === 'fnc1') return `fnc1:${u.index}`;
    if (u.gs1_part === 'separator') return `sep:${u.index}`;
    if (u.gs1_element !== undefined) return `el:${u.gs1_element}`;
    return 'data';
}

/**
 * The scan split into labelled boxes in the order received: prefix, AIM ID,
 * each GS1 field, every GS between them, suffix. Every character is shown.
 */
export function segmentedView(res, { onSelect } = {}) {
    const units = res.units;
    const gs1 = res.gs1_data;
    const box = el('div', { class: 'segments' });
    const groups = [];
    for (const u of units) {
        const key = segmentKey(u);
        const last = groups[groups.length - 1];
        if (last && last.key === key && !key.startsWith('token') && !key.startsWith('sep') && !key.startsWith('fnc1')) last.units.push(u);
        else groups.push({ key, units: [u] });
    }
    for (const g of groups) {
        const [kind, id] = g.key.split(':');
        const chars = g.units.map(u => unitNode(u, { onSelect }));
        if (kind === 'sep' || kind === 'fnc1' || kind === 'token') {
            box.appendChild(el('div', { class: `seg seg-${kind}` },
                el('div', { class: 'seg-label', text: kind === 'sep' ? 'separator' : kind === 'fnc1' ? 'FNC1' : 'key' }),
                el('div', { class: 'seg-chars' }, chars)));
            continue;
        }
        if (kind === 'el' && gs1) {
            const e = gs1.elements[Number(id)];
            const bad = e.unknown || e.boundary_guessed || e.terminator === 'missing_gs' || (e.issues && e.issues.length);
            const aiChars = g.units.filter(u => u.gs1_part === 'ai').map(u => unitNode(u, { onSelect }));
            const valChars = g.units.filter(u => u.gs1_part !== 'ai').map(u => unitNode(u, { onSelect }));
            aiChars.forEach(n => n.classList.add('seg-ai-char'));
            box.appendChild(el('div', { class: `seg seg-el${bad ? ' seg-bad' : ''}`, title: (e.issues || []).join('; ') || e.spec },
                el('div', { class: 'seg-label' }, el('span', { class: 'seg-num', text: `${e.index + 1}` }), ` (${e.ai}) ${e.title}`),
                el('div', { class: 'seg-chars' }, aiChars, valChars),
                el('div', { class: 'seg-foot' },
                    e.formatted_value !== e.value ? el('span', { class: 'seg-formatted', text: e.formatted_value }) : null,
                    el('span', { class: `seg-term term-${e.terminator}`, text: e.boundary_guessed ? 'GS MISSING (boundary guessed)' : TERMINATOR_WORDS[e.terminator] || '' }))));
            continue;
        }
        const label = { prefix: 'Prefix', aim: `AIM ${res.symbology?.aim_id || ''}`, suffix: 'Suffix', data: 'Data' }[kind] || kind;
        box.appendChild(el('div', { class: `seg seg-${kind}` }, el('div', { class: 'seg-label', text: label }), el('div', { class: 'seg-chars' }, chars)));
    }
    return box;
}

/** "Received order: (21) → (01) → (17)" with a note that any order is valid. */
export function gs1OrderLine(res) {
    const g = res.gs1_data;
    if (!g || g.elements.length < 2) return null;
    return el('p', { class: 'gs1-order' },
        el('strong', { text: 'Order received: ' }),
        g.elements.map((e, i) => [i ? ' → ' : '', el('span', { class: 'mono', text: `(${e.ai})` })]),
        el('span', { class: 'muted', text: '  ·  Any order is valid GS1. Only variable-length fields need a GS after them (unless last).' }),
        g.typical_order ? null : el('span', { class: 'warn-text', text: `  The GTIN/primary key isn't first: systems that expect a fixed order may reject this label (their parser's problem, not the scanner's).` }));
}

/** Compact GS1 field table: #, AI, field, value, how it ended, status. */
export function gs1Table(res, { onSelect } = {}) {
    const g = res.gs1_data;
    const rows = g.elements.map(e => {
        const problems = [...(e.issues || [])];
        if (e.boundary_guessed || e.terminator === 'missing_gs') problems.unshift('GS separator missing after this field');
        const ok = !problems.length && !e.unknown;
        return el('tr', { class: ok ? '' : 'row-bad', onclick: onSelect ? () => {
            const u = res.units.find(x => x.gs1_element === e.index);
            if (u) onSelect(u.index);
        } : null },
            el('td', { class: 'num', text: e.index + 1 }),
            el('td', { class: 'mono', text: `(${e.ai})` }),
            el('td', { text: e.title }),
            el('td', { class: 'mono', text: e.value }),
            el('td', { text: e.formatted_value !== e.value ? e.formatted_value : '' }),
            el('td', { text: e.boundary_guessed ? 'GS missing' : TERMINATOR_WORDS[e.terminator] || '' }),
            el('td', { class: ok ? 'ok-text' : 'warn-text', text: ok ? '✓' : problems.join('; ') }));
    });
    return el('div', { class: 'table-wrap' }, el('table', { class: 'gs1-table' },
        el('thead', null, el('tr', null, ['#', 'AI', 'Field', 'Value', 'Means', 'Ended by', 'Check'].map(h => el('th', { text: h })))),
        el('tbody', null, rows)));
}

// ---- Barcode contents (human-readable components) -----------------------------------

const FRIENDLY = {
    '01': 'Product (GTIN)', '00': 'Shipping container (SSCC)', '02': 'Contained product (GTIN)',
    '17': 'Expiration date', '7003': 'Expiration date & time', '15': 'Best before', '16': 'Sell by',
    '11': 'Manufactured', '13': 'Packed', '12': 'Due date', '10': 'Lot / Batch', '21': 'Serial number',
    '30': 'Quantity', '37': 'Quantity', '8018': 'Patient ID (GSRN)', '8017': 'Caregiver ID (GSRN)',
    '715': 'NDC (FDA)', '710': 'PZN (Germany)', '714': 'AIM code (Portugal)', '7250': 'Date of birth',
    '7253': 'Family name', '7254': 'Given name', '7240': 'Protocol ID', '240': 'Additional product ID',
    '250': 'Secondary serial number', '22': 'Product variant',
};
const PRIORITY = ['01', '00', '02', '8018', '8017', '17', '7003', '15', '16', '11', '13', '12', '10', '21', '30', '37', '715', '710', '714'];

function humanDate(iso) {
    if (!iso) return null;
    const d = new Date(`${iso}T00:00:00`);
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
}

function componentCard(e) {
    const problems = [...(e.issues || [])];
    if (e.boundary_guessed || e.terminator === 'missing_gs') problems.unshift('separator (GS) missing after this field');
    const di = e.date_info;
    let main = e.formatted_value ?? e.value;
    const subs = [];
    if (di && di.valid) {
        main = humanDate(di.formatted);
        subs.push(el('span', { class: 'muted', text: di.formatted + (di.rule && di.rule.startsWith('Last') ? ' (end of month)' : '') }));
        if (['17', '7003'].includes(e.ai)) subs.push(di.expired ? el('span', { class: 'pill pill-bad', text: 'EXPIRED' }) : el('span', { class: 'pill pill-ok', text: 'Not expired' }));
    }
    if ('check_digit_valid' in e) {
        subs.push(e.check_digit_valid ? el('span', { class: 'pill pill-ok', text: 'Check digit OK' }) : el('span', { class: 'pill pill-bad', text: 'Check digit WRONG' }));
    }
    if (e.ai === '01' && /^\d03\d{11}$/.test(e.value)) {
        subs.push(el('span', { class: 'muted', text: `NDC ${e.value.slice(3, 13)} (10 digits; dash format not encoded)` }));
    }
    return el('div', { class: `comp${problems.length || e.unknown ? ' comp-bad' : ''}`, dataset: { ai: e.ai } },
        el('div', { class: 'comp-label', text: FRIENDLY[e.ai] || e.title }),
        el('div', { class: 'comp-value', text: main }),
        subs.length ? el('div', { class: 'comp-subs' }, subs) : null,
        problems.length ? el('div', { class: 'comp-problem', text: problems.join('; ') }) : null,
        el('div', { class: 'comp-ai', text: `GS1 AI (${e.ai})` }));
}

/** Cards for each barcode component, most important first. Non-GS1: the data itself. */
export function componentsView(res) {
    const g = res.gs1_data;
    if (g && g.elements.length) {
        const rank = e => { const i = PRIORITY.indexOf(e.ai); return i === -1 ? 100 + e.index : i; };
        const sorted = [...g.elements].sort((a, b) => rank(a) - rank(b));
        return el('div', { class: 'comps' }, sorted.map(componentCard));
    }
    const data = res.units.filter(u => u.region === 'data' || u.region === 'token');
    return el('div', { class: 'comps' },
        el('div', { class: 'comp comp-wide' },
            el('div', { class: 'comp-label', text: 'Barcode data' }),
            el('div', { class: 'comp-value comp-data' }, data.length ? data.map(u => unitNode(u)) : el('span', { class: 'muted', text: '(empty)' })),
            res.symbology?.has_aim_id ? el('div', { class: 'comp-ai', text: `${res.symbology.symbology_name} (${res.symbology.aim_id})` }) : null));
}
