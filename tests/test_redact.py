import json
import os

from scanwise.capture.decoder import decode_events
from scanwise.redact import redact_events
from tests.keyseq import KeySeq

PROFILES = json.load(open(os.path.join(os.path.dirname(__file__), "..", "scanwise", "profiles", "emr_profiles.json")))


def redacted_text(seq, **kw):
    events, n = redact_events(seq.events, profiles=PROFILES, **kw)
    return decode_events(events)["text"], n


def test_wristband_mrn_and_name_are_replaced_controls_kept():
    text, n = redacted_text(KeySeq().type("MRN12345").tab().type("Doe, Jane").enter())
    assert text == "XXX00000\tXxx, Xxxx\r"
    assert n == 15


def test_gs1_ais_separators_aim_and_profile_prefix_survive():
    s = KeySeq().type("\\]d2" "0100301234567896" "10LOT9").ctrl("BracketRight").type("21Ab7\\").enter()
    text, _ = redacted_text(s)
    assert text == "\\]d2" "0100000000000000" "10XXX0\x1d" "21Xx0\\\r"


def test_unconfirmed_prefix_is_redacted():
    # No profile expects "ZZ", so it may be data: redact it.
    text, _ = redacted_text(KeySeq().type("ZZ").type("SMITH").enter())
    assert "SMITH" not in text and "ZZ" not in text


def test_alt_numpad_and_codeless_characters_are_replaced():
    s = KeySeq().alt("0083").alt("74")
    ev = s.events + [{"t": 999, "type": "down", "code": "", "key": "q", "mods": {}}]
    events, n = redact_events(ev, profiles=PROFILES)
    assert decode_events(events)["text"] == "XXx"
    assert n == 3


def test_original_events_are_not_modified():
    s = KeySeq().type("PHI1")
    before = json.dumps(s.events)
    redact_events(s.events, profiles=PROFILES)
    assert json.dumps(s.events) == before


def test_redact_endpoint_stores_nothing_and_never_caches():
    from scanwise import create_app
    app = create_app()
    c = app.test_client()
    r = c.post("/api/redact", json={"key_events": KeySeq().type("JANE").enter().events})
    assert r.status_code == 200
    assert decode_events(r.get_json()["key_events"])["text"] == "XXXX\r"
    assert "no-store" in r.headers.get("Cache-Control", "")
    a = c.post("/api/analyze", json={"key_events": KeySeq().type("JANE").events})
    assert "no-store" in a.headers.get("Cache-Control", "")


def test_server_errors_do_not_log_scan_data(monkeypatch, caplog):
    import scanwise.routes.api as api
    from scanwise import create_app

    secret = "".join(["SMI", "TH"])   # built at runtime so no source line contains it

    def boom(**kw):
        raise ValueError(f"value was {secret}")
    monkeypatch.setattr(api, "analyze", boom)
    app = create_app()
    app.config["PROPAGATE_EXCEPTIONS"] = False
    r = app.test_client().post("/api/analyze", json={"key_events": []})
    assert r.status_code == 500
    assert secret not in r.get_data(as_text=True)
    assert secret not in caplog.text and "ValueError" in caplog.text
