"""
ScanWise REST API Blueprint.
Provides endpoints for scan analysis, profile listing, and health checks.
"""
import json
import os

from flask import Blueprint, current_app, jsonify, request

from scanwise.analysis import analyze

api_bp = Blueprint('api', __name__)

MAX_EVENTS = 20000


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
    return jsonify({"status": "success", "profiles": load_profiles()}), 200


@api_bp.route('/redact', methods=['POST'])
def redact_scan():
    """Body: {"key_events": [...], "profile_id"?}. Returns the events with PHI-capable data replaced. Nothing is stored."""
    from scanwise.redact import redact_events
    data = request.get_json(silent=True) or {}
    key_events = data.get("key_events")
    if not isinstance(key_events, list) or len(key_events) > MAX_EVENTS or not all(isinstance(e, dict) for e in key_events):
        return jsonify({"status": "error", "error": f"key_events must be a list of at most {MAX_EVENTS} objects"}), 400
    events, count = redact_events(key_events, profiles=load_profiles(), profile_id=data.get("profile_id"))
    return jsonify({"status": "success", "key_events": events, "redacted_chars": count}), 200


@api_bp.route('/analyze', methods=['POST'])
def analyze_scan():
    """
    Body: {"key_events": [...]} (preferred) or {"raw_input": "..."};
    optional "profile_id" ("auto" = detect only), "keystroke_timings", "client".
    """
    data = request.get_json(silent=True) or {}
    key_events = data.get("key_events")
    if key_events is not None and (not isinstance(key_events, list) or len(key_events) > MAX_EVENTS):
        return jsonify({"status": "error", "error": f"key_events must be a list of at most {MAX_EVENTS} events"}), 400
    if key_events is not None and not all(isinstance(e, dict) for e in key_events):
        return jsonify({"status": "error", "error": "each key event must be an object"}), 400

    result = analyze(
        key_events=key_events,
        raw_input=data.get("raw_input", ""),
        profiles=load_profiles(),
        profile_id=data.get("profile_id"),
        keystroke_timings=data.get("keystroke_timings") or [],
        client=data.get("client") if isinstance(data.get("client"), dict) else None,
    )
    return jsonify(result), 200
