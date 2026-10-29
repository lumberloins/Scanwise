import datetime

import pytest

from scanwise.analysis import analyze
from scanwise.parsers.aim_codes import parse_aim_identifier
from scanwise.parsers.gs1_ai import AIS
from scanwise.parsers.gs1_parser import detect_gs1, gs1_year, parse_gs1
from tests.test_analysis import PROFILES

GS = "\x1d"
GTIN = "0100301234567896"


def els(payload):
    return [(e["ai"], e["value"], e["terminator"]) for e in parse_gs1(payload)["elements"]]


@pytest.mark.parametrize("payload,order", [
    (GTIN + "17270630" + "10LOT1" + GS + "21SER", ["01", "17", "10", "21"]),
    ("17270630" + "10LOT1" + GS + "21SER" + GS + GTIN, ["17", "10", "21", "01"]),
    ("21SER99" + GS + GTIN + "17270630" + "10L1", ["21", "01", "17", "10"]),
    ("10LOT1" + GS + "17270630" + GTIN, ["10", "17", "01"]),
])
def test_any_order_detected_without_aim(payload, order):
    p, det = detect_gs1(payload)
    assert det["is_gs1"], det
    assert p["order"] == order
    assert p["valid"] and not p["missing_separators"]


def test_terminators_follow_predefined_length_table():
    assert els(GTIN + "17270630" + "10LOT" + GS + "21S") == [
        ("01", "00301234567896", "predefined"), ("17", "270630", "predefined"),
        ("10", "LOT", "gs"), ("21", "S", "end")]


def test_fixed_but_not_predefined_ai_requires_gs():
    p = parse_gs1(GTIN + "422840" + "10X")
    assert p["elements"][1]["terminator"] == "missing_gs"
    assert p["missing_separators"][0]["definite"] and p["missing_separators"][0]["after_ai"] == "422"
    assert parse_gs1(GTIN + "422840" + GS + "10X")["missing_separators"] == []


def test_unnecessary_gs_after_predefined_is_info():
    p = parse_gs1(GTIN + GS + "10X")
    assert p["unnecessary_separators"] == [0] and p["valid"]


def test_definite_missing_gs_resplits_value():
    p = parse_gs1(GTIN + "10ABCDEFGHIJKLMNO" + "17270630" + "21XY")
    lot = p["elements"][1]
    assert lot["boundary_guessed"] and lot["value"] == "ABCDEFGHIJKLMNO"
    assert [e["ai"] for e in p["elements"]] == ["01", "10", "17", "21"]
    assert p["heuristic_applied"]


def test_possible_missing_gs_only_with_strong_evidence():
    assert parse_gs1(GTIN + "10LOT117270630")["possible_missing_separator"]
    assert not parse_gs1(GTIN + "10A21B")["possible_missing_separator"]   # weak: (21) proves nothing


def test_healthcare_ais():
    p = parse_gs1(GTIN + "7141234567" + GS + "21SER" + GS + "91ABC")
    assert [e["ai"] for e in p["elements"]] == ["01", "714", "21", "91"] and p["valid"]
    assert AIS["8018"]["title"].startswith("GSRN")
    p = parse_gs1("8018" + "123456789012345675")
    assert p["elements"][0]["check_digit_valid"] is True


def test_measure_decimals_and_dates():
    p = parse_gs1(GTIN + "3103000189")
    assert p["elements"][1]["formatted_value"] == "0.189"
    p = parse_gs1(GTIN + "17271200")
    assert p["elements"][1]["formatted_value"] == "2027-12-31"
    p = parse_gs1(GTIN + "7003" + "2706301530")
    assert p["elements"][1]["formatted_value"] == "2027-06-30 15:30"


def test_century_rule():
    today = datetime.date(2026, 10, 28)
    assert gs1_year(26, today) == 2026
    assert gs1_year(76, today) == 2076   # +50 stays in this century
    assert gs1_year(77, today) == 1977   # +51 goes back
    assert gs1_year(0, today) == 2000


def test_invalid_values():
    p = parse_gs1("0100301234567899")
    assert p["elements"][0]["check_digit_valid"] is False
    p = parse_gs1(GTIN + "17271332")
    assert not p["elements"][1]["date_info"]["valid"]
    p = parse_gs1(GTIN + "10LOT 1")
    assert any("not allowed" in i for i in p["elements"][1]["issues"])


def test_hri_and_digital_link():
    p, det = detect_gs1("(01)00301234567896(17)270630(10)LOT(21)X")
    assert det["is_gs1"] and p["form"] == "hri" and p["order"] == ["01", "17", "10", "21"]
    p, det = detect_gs1("https://id.example.org/pkg/01/00301234567896/10/AB%2FC?17=270630")
    assert det["is_gs1"] and p["form"] == "digital_link"
    assert [(e["ai"], e["value"]) for e in p["elements"]] == [("01", "00301234567896"), ("10", "AB/C"), ("17", "270630")]


@pytest.mark.parametrize("payload", ["E10293", "1012345678", "MRN0042", "21ABC", "https://example.org/patient/42"])
def test_non_gs1_not_detected(payload):
    assert not detect_gs1(payload)[1]["is_gs1"]


def test_aim_registry_gs1_modifiers():
    assert parse_aim_identifier("]Q3x")["is_gs1"] and not parse_aim_identifier("]Q1x")["is_gs1"]
    assert parse_aim_identifier("]d2x")["is_gs1"] and parse_aim_identifier("]C1x")["is_gs1"]
    assert parse_aim_identifier("]z1x")["is_gs1"] and parse_aim_identifier("]e0x")["is_gs1"]
    assert not parse_aim_identifier("]C0x")["is_gs1"]


def test_units_tagged_with_gs1_fields():
    res = analyze(raw_input="]d2" + "21SER" + GS + GTIN + "\r", profiles=PROFILES)
    data = [u for u in res["units"] if u["region"] == "data"]
    assert [u.get("gs1_part") for u in data[:3]] == ["ai", "ai", "value"]
    gs = [u for u in data if u["char"] == GS][0]
    assert gs["gs1_part"] == "separator" and gs["gs1_after"] == 0
    assert data[-1]["gs1_element"] == 1


def test_order_and_symbology_findings():
    res = analyze(raw_input="]d2" + "21SER" + GS + GTIN + "\r", profiles=PROFILES)
    assert any(f["id"] == "gs1_order" for f in res["findings"])
    assert res["verdict"]["category"] == "PASS"      # order alone is not a fault
    res = analyze(raw_input="]C0" + GTIN + "17270630" + "\r", profiles=PROFILES)
    assert any(f["id"] == "gs1_symbology_mismatch" for f in res["findings"])
