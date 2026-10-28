import pytest
from scanwise.parsers.ascii_chars import get_char_info, inspect_payload
from scanwise.parsers.aim_codes import parse_aim_identifier

def test_ascii_character_classification():
    # Test GS1 delimiter (ASCII 29)
    gs_info = get_char_info(29)
    assert gs_info["category"] == "gs1_delimiter"
    assert gs_info["safe"] is True

    # Test harmful control (ASCII 0 NUL)
    nul_info = get_char_info(0)
    assert nul_info["category"] == "harmful_control"
    assert nul_info["safe"] is False

    # Test printable character
    a_info = get_char_info('A')
    assert a_info["category"] == "printable"
    assert a_info["safe"] is True

def test_payload_inspection():
    payload = "TEST\x1dDATA\x00"
    result = inspect_payload(payload)
    assert result["has_hidden_controls"] is True
    assert result["has_harmful_controls"] is True
    assert len(result["characters"]) == 10

def test_aim_identifier_parsing():
    # Test GS1 DataMatrix AIM ID
    res = parse_aim_identifier("]d20100301234567897")
    assert res["has_aim_id"] is True
    assert res["aim_id"] == "]d2"
    assert res["is_gs1"] is True
    assert res["clean_payload"] == "0100301234567897"

    # Test non-AIM payload
    res_raw = parse_aim_identifier("1234567890")
    assert res_raw["has_aim_id"] is False
    assert res_raw["clean_payload"] == "1234567890"
