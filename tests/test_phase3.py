import pytest
from scanwise.parsers.gs1_parser import validate_gtin_checksum, parse_gs1_date, parse_gs1_barcode

def test_gtin_checksum_validation():
    # Valid GTIN-14: 00301234567896 (6 is check digit)
    assert validate_gtin_checksum("00301234567896") is True
    # Invalid GTIN-14
    assert validate_gtin_checksum("00301234567899") is False
    # Non-digit
    assert validate_gtin_checksum("0030123456789A") is False

def test_gs1_date_parsing_and_zero_day_rule():
    # Exact date: YYMMDD -> 251231 (Dec 31, 2025)
    res = parse_gs1_date("251231")
    assert res["valid"] is True
    assert res["formatted"] == "2025-12-31"
    assert res["rule"] == "Exact date"

    # DD == 00 rule: 251200 -> Last day of Dec 2025 (Dec 31, 2025)
    res_zero = parse_gs1_date("251200")
    assert res_zero["valid"] is True
    assert res_zero["formatted"] == "2025-12-31"
    assert res_zero["rule"] == "Last day of month (DD=00)"

    # Invalid month
    res_bad = parse_gs1_date("251331")
    assert res_bad["valid"] is False

def test_gs1_barcode_parsing():
    # Payload: AI 01 (GTIN) + AI 17 (Exp) + AI 10 (Lot) + <GS> + AI 21 (Serial)
    # GTIN: 00301234567896
    # Exp: 251231
    # Lot: BATCH999
    # GS: \x1d
    # Serial: SER12345
    payload = "01003012345678961725123110BATCH999\x1d21SER12345"
    parsed = parse_gs1_barcode(payload)

    assert parsed["valid"] is True
    elements = parsed["elements"]
    assert len(elements) == 4

    assert elements[0]["ai"] == "01"
    assert elements[0]["raw_value"] == "00301234567896"
    assert elements[0]["check_digit_valid"] is True

    assert elements[1]["ai"] == "17"
    assert elements[1]["formatted_value"] == "2025-12-31"

    assert elements[2]["ai"] == "10"
    assert elements[2]["raw_value"] == "BATCH999"

    assert elements[3]["ai"] == "21"
    assert elements[3]["raw_value"] == "SER12345"
