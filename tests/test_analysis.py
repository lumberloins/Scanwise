import json
import os

import pytest

from scanwise import create_app
from scanwise.analysis import analyze
from tests.keyseq import KeySeq

PROFILES = json.load(open(os.path.join(os.path.dirname(__file__), "..", "scanwise", "profiles", "emr_profiles.json")))


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def scan(seq, profile_id=None, **kw):
    return analyze(key_events=seq.events, profiles=PROFILES, profile_id=profile_id, **kw)


def epic_gs1():
    return KeySeq().type("/DATA/]d2010030123456789610LOT1").ctrl("BracketRight").type("21SER9").enter()


def test_epic_scan_auto_detects_profile_and_passes():
    res = scan(epic_gs1())
    assert res["config"]["prefix"]["words"] == '"/DATA/"'
    assert res["config"]["suffix"]["words"] == "CR (Enter)"
    assert "epic_emr" in res["config"]["matched_profiles"]
    assert res["config"]["aim"]["enabled"] is True
    assert res["config"]["gs1_separators"]["status"] == "present"
    assert res["config"]["control_chars"]["mode"] == "ctrl_ascii"
    assert res["verdict"]["category"] == "PASS", res["findings"]


def test_units_carry_region_and_badges():
    res = scan(epic_gs1())
    chars = [u for u in res["units"] if u["kind"] == "char"]
    assert chars[0]["region"] == "prefix"
    assert chars[6]["region"] == "aim"
    gs = [u for u in chars if u["abbr"] == "GS"][0]
    assert gs["region"] == "data" and gs["via"] == "ctrl" and gs["hex"] == "1D"
    assert chars[-1]["abbr"] == "CR" and chars[-1]["region"] == "suffix"


@pytest.mark.parametrize("build,words", [
    (lambda s: s.tab(), "Tab"),
    (lambda s: s.enter().ctrl("KeyJ"), "CR (Enter) + LF"),
    (lambda s: s, "None"),
    (lambda s: s.ctrl("KeyL"), "FF"),
])
def test_suffix_words(build, words):
    res = scan(build(KeySeq().type("PATIENT123")))
    assert res["config"]["suffix"]["words"] == words


def test_tab_suffix_fails_epic_but_detects_ok():
    res = scan(KeySeq().type("/DATA/MRN42").tab(), profile_id="epic_emr")
    assert res["framing"]["profile_matched"] is False
    assert res["verdict"]["category"] == "SCANNER_CONFIG_FAULT"
    epic = [p for p in res["config"]["profile_checks"] if p["id"] == "epic_emr"][0]
    assert "Suffix is Tab" in epic["reasons"][0]


def test_form_feed_suffix_is_flagged():
    res = scan(KeySeq().type("MRN42").ctrl("KeyL"))
    assert any(f["id"] == "harmful_framing_char" for f in res["findings"])


def test_rogue_control_inside_data():
    res = scan(KeySeq().type("MRN").ctrl("KeyG").type("42").enter())
    f = [f for f in res["findings"] if f["id"] == "rogue_control_in_data"][0]
    assert "BEL" in f["title"]


def test_plain_wristband_with_10_is_not_gs1():
    res = scan(KeySeq().type("E10293").enter())
    assert res["gs1_data"] is None
    assert res["verdict"]["category"] == "PASS"


def test_missing_gs_separator_detected():
    res = scan(KeySeq().type("]d2010030123456789610LOT117251231").enter())
    assert any(f["id"] == "missing_gs1_separator" for f in res["findings"])
    assert res["config"]["gs1_separators"]["status"] == "missing"


def test_generic_profile_keeps_aim_id():
    res = scan(KeySeq().type("]C0ABC").enter(), profile_id="generic_gs1")
    assert res["symbology"]["aim_id"] == "]C0"


def test_interrupted_scan_finding():
    res = scan(KeySeq().type("AB"), client={"interrupted": True, "interruption_reason": "blur"})
    assert res["verdict"]["finding_id"] == "scan_interrupted"


def test_function_key_token_finding():
    res = scan(KeySeq().type("AB").press("PageDown"))
    assert any(f["id"] == "function_keys" for f in res["findings"])


def test_iso15434_envelope():
    s = KeySeq().type("[)>").ctrl("Digit6", shift=True).type("06").ctrl("BracketRight") \
        .type("1PABC").ctrl("Digit6", shift=True).ctrl("KeyD").enter()
    res = scan(s)
    assert res["anomalies"]["iso15434"]["format"] == "06"
    assert not res["anomalies"]["rogue_in_data"]


def test_api_accepts_key_events(client):
    r = client.post("/api/analyze", json={"key_events": epic_gs1().events, "profile_id": "auto"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["input_mode"] == "key_events"
    assert data["text"].endswith("\x1d21SER9\r")
    assert "<" not in json.dumps(data["units"])  # no HTML in structured units


def test_api_rejects_bad_events(client):
    assert client.post("/api/analyze", json={"key_events": "nope"}).status_code == 400
    assert client.post("/api/analyze", json={"key_events": [1, 2]}).status_code == 400
