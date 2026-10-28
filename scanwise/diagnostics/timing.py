"""
Keystroke Timing & Jitter Analyzer.
Analyzes inter-character arrival times from hardware wedge event streams to detect
scanner burst speed vs manual typing vs Citrix/RDP virtual channel latency drops.
"""

def analyze_timings(timings):
    """
    Analyzes an array of high-resolution timestamp deltas (in milliseconds) between keystrokes.
    """
    if not timings or len(timings) < 2:
        return {
            "total_burst_time_ms": 0,
            "avg_inter_char_ms": 0,
            "is_scanner_speed": True,
            "jitter_detected": False,
            "description": "Insufficient timing data (single key or manual entry)."
        }

    # Calculate deltas if absolute timestamps were provided
    deltas = []
    for i in range(1, len(timings)):
        delta = timings[i] - timings[i-1]
        deltas.append(max(0.0, delta))

    if not deltas:
        return {
            "total_burst_time_ms": 0,
            "avg_inter_char_ms": 0,
            "is_scanner_speed": True,
            "jitter_detected": False,
            "description": "No timing deltas computed."
        }

    total_time = sum(deltas)
    avg_delta = total_time / len(deltas)

    # Scanner signature: average inter-character delay < 30ms
    is_scanner = avg_delta < 40.0

    # Jitter / Citrix lag detection: high variance or spikes > 80ms mid-scan
    max_delta = max(deltas)
    min_delta = min(deltas)
    jitter_detected = is_scanner and (max_delta > 100.0) and (max_delta / (min_delta + 1.0) > 10.0)

    desc = "Consistent high-speed scanner burst."
    if not is_scanner:
        desc = "Detected manual typing speed (inter-character delay > 40ms)."
    elif jitter_detected:
        desc = "Timing jitter detected! Spikes in inter-character arrival suggest Citrix/RDP virtual desktop latency or dropped characters."

    return {
        "total_burst_time_ms": round(total_time, 2),
        "avg_inter_char_ms": round(avg_delta, 2),
        "is_scanner_speed": is_scanner,
        "jitter_detected": jitter_detected,
        "description": desc
    }
