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
