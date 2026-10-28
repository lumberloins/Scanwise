import pytest
from scanwise.diagnostics.framing import extract_framing
from scanwise.diagnostics.anomalies import detect_anomalies
from scanwise.diagnostics.timing import analyze_timings
from scanwise.diagnostics.verdict import generate_verdict

def test_framing_extraction():
    profile = {
        "id": "epic_emr",
        "name": "Epic EMR",
        "expected_prefix": "/DATA/",
        "expected_suffix": "\r"
    }

    raw = "/DATA/]d20100301234567896\r"
    res = extract_framing(raw, profile)

    assert res["profile_matched"] is True
    assert res["prefix_detected"] == "/DATA/"
    assert res["suffix_detected"] == "\r"
    assert res["clean_payload"] == "]d20100301234567896"

def test_anomaly_detection():
    # Clean payload vs harmful control character
    clean = "0100301234567896"
    raw_harmful = "0100301234567896\x00"
    res = detect_anomalies(clean, raw_harmful)
    assert res["has_harmful_controls"] is True

def test_timing_analysis():
    # Fast scanner burst timings (deltas < 15ms)
    timings = [0, 5, 10, 15, 20]
    res = analyze_timings(timings)
    assert res["is_scanner_speed"] is True
    assert res["jitter_detected"] is False

def test_verdict_generation():
    framing = {"profile_matched": True, "profile_name": "Epic EMR"}
    anomalies = {"has_harmful_controls": False, "missing_gs1_delimiter": False}
    gs1 = {"valid": True}
    timing = {"jitter_detected": False}

    verdict = generate_verdict(framing, anomalies, gs1, timing)
    assert verdict["category"] == "PASS"
    assert verdict["level"] == "success"
