/** ScanWise API client. */

export async function analyze(events, { profileId = 'auto', client = {} } = {}) {
    const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key_events: events, profile_id: profileId, client }),
    });
    if (!res.ok) throw new Error(`Analyze failed: HTTP ${res.status}`);
    return res.json();
}

export async function getProfiles() {
    const res = await fetch('/api/profiles');
    if (!res.ok) throw new Error(`Profiles failed: HTTP ${res.status}`);
    return (await res.json()).profiles;
}

/** Replace PHI-capable data characters in key events (server-side; nothing is stored). */
export async function redact(events, { profileId = 'auto' } = {}) {
    const res = await fetch('/api/redact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key_events: events, profile_id: profileId }),
    });
    if (!res.ok) throw new Error(`Redact failed: HTTP ${res.status}`);
    return res.json();
}
