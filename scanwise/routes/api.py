"""
ScanWise REST API Blueprint.
Provides endpoints for scan analysis, profile listing, and health checks.
"""
import os
import json
import datetime
from flask import Blueprint, request, jsonify, current_app

from scanwise.parsers.aim_codes import parse_aim_identifier
from scanwise.parsers.gs1_parser import parse_gs1_barcode
from scanwise.parsers.ascii_chars import inspect_payload
from scanwise.diagnostics.framing import extract_framing
from scanwise.diagnostics.anomalies import detect_anomalies
from scanwise.diagnostics.timing import analyze_timings
from scanwise.diagnostics.verdict import generate_verdict

api_bp = Blueprint('api', __name__)

def load_profiles():
    profiles_path = os.path.join(current_app.root_path, 'profiles', 'emr_profiles.json')
    try:
        with open(profiles_path, 'r') as f:
            return json.load(f)
    except Exception:
        return {}

@api_bp.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "ScanWise Diagnostic API"}), 200

@api_bp.route('/profiles', methods=['GET'])
def get_profiles():
    profiles = load_profiles()
    return jsonify({"status": "success", "profiles": profiles}), 200

@api_bp.route('/analyze', methods=['POST'])
def analyze_scan():
    """
    Analyzes raw scan input, keystroke timings, and profile selection.
    """
    data = request.get_json() or {}
    raw_input = data.get("raw_input", "")
    profile_id = data.get("profile_id", "epic_emr")
    timings = data.get("keystroke_timings", [])

    profiles = load_profiles()
    profile = profiles.get(profile_id, profiles.get("epic_emr", {
        "id": "epic_emr",
        "name": "Epic EMR",
        "expected_prefix": "/DATA/",
        "expected_suffix": "\r"
    }))

    # 1. Framing analysis
    framing = extract_framing(raw_input, profile)
    clean_payload = framing["clean_payload"]

    # 2. Symbology & AIM ID parsing
    symbology = parse_aim_identifier(clean_payload)
    barcode_payload = symbology["clean_payload"]

    # 3. GS1 Parsing (if GS1 symbology or contains GS1 AIs)
    gs1_data = None
    if symbology["is_gs1"] or any(ai in barcode_payload for ai in ["01", "17", "10", "21"]):
        gs1_data = parse_gs1_barcode(barcode_payload)

    # 4. Anomaly detection
    anomalies = detect_anomalies(barcode_payload, raw_input)

    # 5. Timing analysis
    timing_res = analyze_timings(timings)

    # 6. Verdict synthesis
    verdict = generate_verdict(framing, anomalies, gs1_data, timing_res)

    # 7. Raw dump hex / ascii formatting
    ascii_dump = raw_input.replace('\x1d', '<GS>').replace('\r', '<CR>').replace('\n', '<LF>').replace('\t', '<TAB>')
    hex_dump = " ".join([f"{ord(c):02x}" for c in raw_input])

    return jsonify({
        "status": "success",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "verdict": verdict,
        "framing": framing,
        "symbology": symbology,
        "gs1_data": gs1_data,
        "anomalies": anomalies,
        "timing": timing_res,
        "raw_dump": {
            "ascii": ascii_dump,
            "hex": hex_dump
        }
    }), 200
