from scanwise.capture.decoder import decode_events
from scanwise.parsers.ascii_chars import describe_char, visualize
from tests.keyseq import KeySeq


def text_of(seq):
    return decode_events(seq.events)["text"]


def test_shift_capitals_never_leak_modifier_names():
    res = decode_events(KeySeq().type("ABC123xyz").events)
    assert res["text"] == "ABC123xyz"
    assert "[" not in res["text"]
    assert res["summary"]["unit_count"] == 9


def test_enter_and_tab_keys():
    res = decode_events(KeySeq().type("A").tab().type("B").enter().events)
    assert res["text"] == "A\tB\r"
    vias = [u["via"] for u in res["units"]]
    assert vias == ["key", "named_key", "key", "enter_key"]
    assert res["summary"]["control_char_mode"] == "keys_only"


def test_ctrl_letters_produce_c0_controls():
    s = KeySeq()
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        s.ctrl(f"Key{letter}")
    res = decode_events(s.events)
    assert [ord(c) for c in res["text"]] == list(range(1, 27))
    assert all(u["via"] == "ctrl" for u in res["units"])
    assert res["summary"]["control_char_mode"] == "ctrl_ascii"


def test_ctrl_symbols():
    s = KeySeq().ctrl("BracketLeft").ctrl("Backslash").ctrl("BracketRight") \
        .ctrl("Digit6", shift=True).ctrl("Minus", shift=True).ctrl("Digit2", shift=True)
    assert text_of(s) == "\x1b\x1c\x1d\x1e\x1f\x00"


def test_gs_three_ways_all_decode_to_0x1d():
    ctrl = decode_events(KeySeq().type("10AB").ctrl("BracketRight").type("21X").events)
    alt = decode_events(KeySeq().type("10AB").alt("0029").type("21X").events)
    for res, via in ((ctrl, "ctrl"), (alt, "alt_numpad")):
        assert res["text"] == "10AB\x1d21X"
        gs = [u for u in res["units"] if u["char"] == "\x1d"][0]
        assert gs["via"] == via
    assert alt["summary"]["control_char_mode"] == "alt_numpad"


def test_alt_numpad_codepages():
    # Alt+0128 -> Windows-1252 euro sign; Alt+128 -> CP437 'Ç'
    res = decode_events(KeySeq().alt("0128").alt("128").alt("65").events)
    assert res["text"] == "€ÇA"
    assert res["units"][0]["codepage"] == "cp1252"
    assert res["units"][1]["codepage"] == "cp437"


def test_alt_sequence_without_release_is_flushed_incomplete():
    s = KeySeq()
    s.mod_down("AltLeft").press("Numpad1").press("Numpad3")
    res = decode_events(s.events)
    assert res["text"] == "\r"
    assert res["units"][0]["incomplete"] is True
    assert res["summary"]["notes"]


def test_function_keys_are_tokens_not_bytes():
    res = decode_events(KeySeq().type("A").press("F5").press("PageDown").events)
    assert res["text"] == "A"
    assert res["summary"]["tokens"] == ["F5", "PageDown"]
    assert res["units"][1]["kind"] == "token"


def test_full_mixed_scan():
    # Epic-style framing with GS1 DataMatrix, AIM ID, GS separator, FF and CR+LF.
    s = KeySeq().type("/DATA/]d20100301234567896").type("10LOT1").ctrl("BracketRight") \
        .type("21SER").ctrl("KeyL").enter().ctrl("KeyJ")
    res = decode_events(s.events)
    assert res["text"] == "/DATA/]d20100301234567896" "10LOT1\x1d21SER\x0c\r\n"
    assert visualize(res["text"]).endswith("<GS>21SER<FF><CR><LF>")


def test_layout_mismatch_detected_from_browser_key():
    s = KeySeq(browser=True).type("A")
    s.events[1]["key"] = "q"           # host is AZERTY: KeyA produces 'q'
    res = decode_events(s.events)
    assert res["units"][0]["layout_mismatch"] is True
    assert res["summary"]["layout_mismatch_count"] == 1


def test_caps_lock_suspected():
    s = KeySeq(browser=True).type("abc")
    for ev in s.events:
        if ev["type"] == "down":
            ev["key"] = ev["key"].upper()
    res = decode_events(s.events)
    assert res["summary"]["caps_lock_suspected"] is True


def test_browser_mods_are_authoritative():
    # Browser events carry mods; no separate Control key-down was delivered.
    events = [{"t": 0, "type": "down", "code": "BracketRight", "key": "]",
               "mods": {"ctrl": True, "shift": False, "alt": False, "meta": False}}]
    assert decode_events(events)["text"] == "\x1d"


def test_dwell_and_timing_recorded():
    res = decode_events(KeySeq(step=4).type("AB").events)
    a = res["units"][0]
    assert a["dwell_ms"] is not None and a["dwell_ms"] > 0
    assert res["units"][1]["t"] > a["t"]


def test_unknown_key_reported():
    res = decode_events([{"t": 0, "type": "down", "code": "Lang1"}])
    assert res["summary"]["unknown_keys"] == ["Lang1"]


def test_every_c0_control_has_a_badge():
    for cp in list(range(0x20)) + [0x7F] + list(range(0x80, 0xA0)):
        info = describe_char(cp)
        assert info["abbr"], hex(cp)
        assert not info["visible"]
    assert describe_char(0x1D)["abbr"] == "GS"
    assert describe_char(0x0C)["abbr"] == "FF"
    assert describe_char(0xA0)["abbr"] == "NBSP"
    assert describe_char(0xFEFF)["abbr"] == "BOM"
    assert describe_char("A")["visible"]


def _codeless(text, ctrl_letters=""):
    ev, t = [], 0.0
    for ch in text:
        t += 2
        ev += [{"t": t, "type": "down", "code": "", "key": ch, "mods": {}}, {"t": t + 1, "type": "up", "code": "", "key": ch, "mods": {}}]
    return ev


def test_codeless_events_use_host_characters():
    # RDP/Citrix/VK_PACKET style: no physical code, only the produced character.
    ev = _codeless("0100301234567896" + "10LOT" + "\x1d" + "21SER")
    ev.append({"t": 99, "type": "down", "code": "", "key": "Enter", "mods": {}})
    res = decode_events(ev)
    assert res["text"] == "0100301234567896" "10LOT\x1d21SER\r"
    assert res["summary"]["codeless_count"] == 27
    assert res["summary"]["unknown_keys"] == []


def test_codeless_ctrl_letter_and_unidentified_code():
    ev = [{"t": 0, "type": "down", "code": "Unidentified", "key": "j", "mods": {"ctrl": True}},
          {"t": 1, "type": "down", "code": "", "key": "Tab", "mods": {}}]
    assert decode_events(ev)["text"] == "\n\t"


def test_shift_pressed_alone_is_a_lost_key():
    # From a real export: the I of "IS2205993" was dropped; only Shift down/up arrived.
    s = KeySeq().mod_down("ShiftLeft").mod_up("ShiftLeft").type("S2")
    res = decode_events(s.events)
    assert res["text"] == "S2"
    assert res["summary"]["lost_key_count"] == 1
    assert res["units"][0]["token"] == "LOST KEY" and res["units"][0]["via"] == "lost_key"


def test_normal_shift_and_ctrl_and_alt_are_not_lost_keys():
    s = KeySeq().type("AbC").ctrl("BracketRight").alt("0029").enter()
    assert decode_events(s.events)["summary"]["lost_key_count"] == 0


def test_lost_key_finding_is_the_headline():
    from scanwise.analysis import analyze
    s = KeySeq().type("0").mod_down("ShiftLeft").mod_up("ShiftLeft").type("S").enter()
    res = analyze(s.events)
    assert res["findings"][0]["id"] == "keys_lost"
    assert res["verdict"]["category"] != "PASS"
