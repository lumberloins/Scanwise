/**
 * Client for scanwise-agent (native HID capture), over HTTP + Server-Sent Events.
 * The agent only accepts requests from allowed page origins (see agent --allow-origin).
 */
export class AgentClient {
    constructor(base = 'http://127.0.0.1:47800') {
        this.base = base.replace(/\/+$/, '');
        this.es = null;
    }

    async _fetch(path, opts = {}) {
        const res = await fetch(`${this.base}${path}`, { ...opts, headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) } });
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
        return body;
    }

    status() { return this._fetch('/status'); }
    devices() { return this._fetch('/devices'); }
    select(id, grab) { return this._fetch('/select', { method: 'POST', body: JSON.stringify({ id, grab }) }); }
    release() { return this._fetch('/release', { method: 'POST', body: '{}' }); }

    /** Subscribe to the event stream. Returns an unsubscribe function. */
    connect({ onKey, onStatus, onError }) {
        this.disconnect();
        const es = new EventSource(`${this.base}/events`);
        es.addEventListener('key', e => onKey && onKey(JSON.parse(e.data)));
        es.addEventListener('status', e => onStatus && onStatus(JSON.parse(e.data)));
        es.onerror = () => onError && onError(es.readyState);
        this.es = es;
        return () => this.disconnect();
    }

    disconnect() {
        if (this.es) { this.es.close(); this.es = null; }
    }
}
