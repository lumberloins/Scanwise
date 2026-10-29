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
    # Epic wraps the barcode in backslashes: \<data>\ (here with an optional CR after).
    return KeySeq().type("\\]d2010030123456789610LOT1").ctrl("BracketRight").type("21SER9\\").enter()


def test_epic_scan_auto_detects_profile_and_passes():
    res = scan(epic_gs1())
    assert res["config"]["prefix"]["words"] == '"\\"'
    assert res["config"]["suffix"]["words"] == '"\\" + CR (Enter)'
    assert "epic_emr" in res["config"]["matched_profiles"]
    assert res["config"]["aim"]["enabled"] is True
    assert res["config"]["gs1_separators"]["status"] == "present"
    assert res["config"]["control_chars"]["mode"] == "ctrl_ascii"
    assert res["verdict"]["category"] == "PASS", res["findings"]


def test_units_carry_region_and_badges():
    res = scan(epic_gs1())
    chars = [u for u in res["units"] if u["kind"] == "char"]
    assert chars[0]["region"] == "prefix"
    assert chars[1]["region"] == "aim"
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


def test_wrong_prefix_fails_epic():
    res = scan(KeySeq().type("/DATA/MRN42").tab(), profile_id="epic_emr")
    assert res["framing"]["profile_matched"] is False
    assert res["verdict"]["category"] == "SCANNER_CONFIG_FAULT"
    epic = [p for p in res["config"]["profile_checks"] if p["id"] == "epic_emr"][0]
    assert "prefix" in epic["reasons"][0].lower()


GS1_BODY = ("0100301234567896", "10LOT1", "21SER9")
TERMINATORS = {None: lambda s: s, "cr": lambda s: s.enter(), "tab": lambda s: s.tab(),
               "crlf": lambda s: s.enter().ctrl("KeyJ"), "lf": lambda s: s.ctrl("KeyJ"),
               "tab+cr": lambda s: s.tab().enter()}


def epic_scan(aim="]d2", terminator=None, aim_first=False):
    """Epic framing: \\ + data + \\, optionally followed by CR/LF/Tab."""
    lead = (aim + "\\") if aim_first else ("\\" + aim)
    s = KeySeq().type(lead + GS1_BODY[0] + GS1_BODY[1]).ctrl("BracketRight").type(GS1_BODY[2] + "\\")
    return TERMINATORS[terminator](s)


def test_real_denso_epic_scan_is_gs1_and_passes():
    # Captured from the team's DENSO with the enterprise Epic configuration.
    fx = json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "denso_epic_gs1.json")))
    for profile in ("auto", "epic_emr"):
        res = analyze(key_events=fx["events"], profiles=PROFILES, profile_id=profile)
        assert res["text"] == "\\01095011015300031715011910AB-123\\"
        assert res["verdict"]["category"] == "PASS", res["findings"]
        assert res["gs1_detection"]["is_gs1"]
        assert [(e["ai"], e["value"]) for e in res["gs1_data"]["elements"]] == [
            ("01", "09501101530003"), ("17", "150119"), ("10", "AB-123")]
        assert res["config"]["configured_for"] == \
            'Epic EMR (Hyperspace / Rover): "\\" before the data, "\\" after it, no Enter or Tab'
        assert not any(f["severity"] in ("warning", "error") for f in res["findings"])


@pytest.mark.parametrize("terminator", list(TERMINATORS))
@pytest.mark.parametrize("aim,aim_first", [("]d2", False), ("]d2", True), ("", False)])
def test_epic_wrapping_with_any_optional_terminator(terminator, aim, aim_first):
    for profile in ("auto", "epic_emr"):
        res = scan(epic_scan(aim=aim, terminator=terminator, aim_first=aim_first), profile_id=profile)
        assert res["framing"]["profile_matched"] in (True, None), res["framing"]["profile_reasons"]
        assert "epic_emr" in res["framing"]["matched_profiles"], res["config"]["profile_checks"]
        assert res["gs1_detection"]["is_gs1"]
        assert [e["ai"] for e in res["gs1_data"]["elements"]] == ["01", "10", "21"]
        assert res["gs1_data"]["elements"][-1]["value"] == "SER9"      # closing \\ is not part of the serial
        assert res["verdict"]["category"] == "PASS", res["findings"]
        cf = res["config"]["configured_for"]
        assert ("no Enter or Tab" in cf) if terminator is None else ("then " in cf), cf


def test_epic_regions_with_aim_first():
    res = scan(epic_scan(aim_first=True, terminator="cr"), profile_id="epic_emr")
    regions = "".join(u["region"][0] for u in res["units"] if u["kind"] == "char")
    assert regions.startswith("aaap" + "d")
    assert regions.endswith("dss")


def test_epic_missing_closing_backslash_fails():
    s = KeySeq().type("\\" + GS1_BODY[0])
    res = scan(s, profile_id="epic_emr")
    assert res["framing"]["profile_matched"] is False


def test_epic_rejects_a_non_terminator_after_the_wrapping():
    res = scan(epic_scan().ctrl("KeyL"), profile_id="epic_emr")
    assert res["framing"]["profile_matched"] is False


def test_unknown_text_prefix_before_aim_does_not_hide_gs1():
    s = KeySeq().type("HOSP1]d2" + GS1_BODY[0] + GS1_BODY[1]).ctrl("BracketRight").type(GS1_BODY[2]).enter()
    res = scan(s)
    assert res["framing"]["prefix_detected"] == "HOSP1"
    assert res["framing"]["prefix_unrecognized"] is True
    assert res["gs1_detection"]["is_gs1"]


def test_trailing_backslash_without_epic_prefix_stays_data():
    res = scan(KeySeq().type("MRN42\\").enter())
    assert res["framing"]["suffix_detected"] == "\r"


def test_no_suffix_is_only_info_when_nothing_requires_one():
    res = scan(KeySeq().type("MRN42"))
    f = [f for f in res["findings"] if f["id"] == "no_suffix"]
    assert f and f[0]["severity"] == "info"
    assert res["verdict"]["category"] == "PASS"


def test_no_suffix_still_warns_when_profile_needs_one():
    res = scan(KeySeq().type("MRN42"), profile_id="meditech_expanse")
    assert any(f["id"] == "no_suffix" for f in res["findings"])


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
    # A 12-char lot is legal, but it hides (17) + a valid date: flagged as *possible*.
    res = scan(KeySeq().type("]d2010030123456789610LOT117251231").enter())
    assert any(f["id"] == "possible_missing_gs1_separator" for f in res["findings"])
    assert res["config"]["gs1_separators"]["status"] == "possible_missing"
    # A 25-char "lot" exceeds X..20, so the missing GS is definite and the boundary is re-split.
    res = scan(KeySeq().type("]d20100301234567896" "10ABCDEFGHIJKLMNO" "17251231" "21XY").enter())
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
    assert data["text"].endswith("\x1d21SER9\\\r")
    assert "<" not in json.dumps(data["units"])  # no HTML in structured units


def test_api_rejects_bad_events(client):
    assert client.post("/api/analyze", json={"key_events": "nope"}).status_code == 400
    assert client.post("/api/analyze", json={"key_events": [1, 2]}).status_code == 400
