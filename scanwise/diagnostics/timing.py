"""
Keystroke Timing & Jitter Analyzer.

Works on per-character timestamps (key-down times, ms). Distinguishes scanner
bursts from manual typing and flags mid-scan gaps typical of Citrix/RDP
virtual channel lag or a scanner inter-character delay setting.
"""
import statistics

SCANNER_MAX_AVG_MS = 40.0
HISTOGRAM_EDGES = [2, 5, 10, 20, 50, 100]


def _bucket_label(lo, hi):
    return f"{lo}-{hi} ms" if hi is not None else f"{lo}+ ms"


def analyze_timings(timings, dwells=None):
    """`timings`: absolute timestamps (ms) for each character, in order."""
    if not timings or len(timings) < 2:
        return {
            "total_burst_time_ms": 0, "avg_inter_char_ms": 0, "is_scanner_speed": True,
            "jitter_detected": False, "deltas": [], "spikes": [], "histogram": [],
            "description": "Insufficient timing data (single key or no timestamps).",
        }

    deltas = [max(0.0, timings[i] - timings[i - 1]) for i in range(1, len(timings))]
    total = timings[-1] - timings[0]
    avg = sum(deltas) / len(deltas)
    median = statistics.median(deltas)
    ordered = sorted(deltas)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    is_scanner = median < SCANNER_MAX_AVG_MS

    # A spike is a gap far above the scan's own rhythm.
    spike_floor = max(50.0, 5 * median)
    spikes = [{"after_index": i, "delta_ms": round(d, 3)} for i, d in enumerate(deltas) if d > spike_floor]
    jitter = is_scanner and bool(spikes) and (max(deltas) > 100.0 or len(spikes) >= 2)

    edges = [0] + HISTOGRAM_EDGES
    hist = []
    for k, lo in enumerate(edges):
        hi = edges[k + 1] if k + 1 < len(edges) else None
        n = sum(1 for d in deltas if d >= lo and (hi is None or d < hi))
        hist.append({"label": _bucket_label(lo, hi), "count": n})

    if not is_scanner:
        desc = f"Manual typing speed (median {median:.1f} ms between keys)."
    elif jitter:
        desc = f"Scanner burst with {len(spikes)} mid-scan gap(s) up to {max(deltas):.0f} ms: typical of VDI/RDP lag."
    else:
        desc = "Consistent high-speed scanner burst."

    res = {
        "total_burst_time_ms": round(total, 2),
        "avg_inter_char_ms": round(avg, 2),
        "median_inter_char_ms": round(median, 3),
        "min_inter_char_ms": round(ordered[0], 3),
        "max_inter_char_ms": round(ordered[-1], 3),
        "p95_inter_char_ms": round(p95, 3),
        "stdev_ms": round(statistics.pstdev(deltas), 3),
        "chars_per_second": round((len(timings) - 1) / (total / 1000.0), 1) if total > 0 else None,
        "is_scanner_speed": is_scanner,
        "jitter_detected": bool(jitter),
        "spike_threshold_ms": round(spike_floor, 2),
        "spikes": spikes,
        "deltas": [round(d, 3) for d in deltas],
        "histogram": hist,
        "description": desc,
    }
    dw = [d for d in (dwells or []) if d is not None]
    if dw:
        res["dwell"] = {"min_ms": round(min(dw), 3), "max_ms": round(max(dw), 3),
                        "median_ms": round(statistics.median(dw), 3)}
    return res
