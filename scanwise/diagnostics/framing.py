"""
Scanner Framing & EMR Profile Verifier.
Extracts preambles/prefixes and postambles/suffixes from raw scanner wedge input
and verifies them against selected EMR requirements (e.g. Epic /DATA/ framing).
"""

def extract_framing(raw_input, profile):
    """
    Extracts prefix and suffix from raw input based on EMR profile specification.
    Profile expected keys: 'expected_prefix', 'expected_suffix'.
    """
    if not raw_input:
        return {
            "profile_id": profile.get("id"),
            "profile_name": profile.get("name"),
            "profile_matched": False,
            "prefix_detected": "",
            "suffix_detected": "",
            "clean_payload": "",
            "raw_prefix_hex": "",
            "raw_suffix_hex": ""
        }

    expected_prefix = profile.get("expected_prefix", "")
    expected_suffix = profile.get("expected_suffix", "")

    prefix_detected = ""
    suffix_detected = ""
    clean = raw_input

    # Check prefix
    if expected_prefix and clean.startswith(expected_prefix):
        prefix_detected = expected_prefix
        clean = clean[len(expected_prefix):]
    elif clean.startswith("]"):
        # Common AIM ID prefix even if profile doesn't enforce /DATA/
        prefix_detected = clean[:3]
        clean = clean[3:]

    # Check suffix (e.g. \r, \n, \t)
    if expected_suffix and clean.endswith(expected_suffix):
        suffix_detected = expected_suffix
        clean = clean[:-len(expected_suffix)]
    elif clean.endswith("\r\n"):
        suffix_detected = "\r\n"
        clean = clean[:-2]
    elif clean.endswith("\r"):
        suffix_detected = "\r"
        clean = clean[:-1]
    elif clean.endswith("\n"):
        suffix_detected = "\n"
        clean = clean[:-1]
    elif clean.endswith("\t"):
        suffix_detected = "\t"
        clean = clean[:-1]

    # Compute hex representations
    prefix_hex = "".join([f"{ord(c):02x}" for c in prefix_detected])
    suffix_hex = "".join([f"{ord(c):02x}" for c in suffix_detected])

    # Determine if profile matched
    profile_matched = True
    if expected_prefix and prefix_detected != expected_prefix:
        profile_matched = False
    if expected_suffix and suffix_detected != expected_suffix:
        profile_matched = False

    return {
        "profile_id": profile.get("id"),
        "profile_name": profile.get("name"),
        "profile_matched": profile_matched,
        "prefix_detected": prefix_detected,
        "suffix_detected": suffix_detected,
        "clean_payload": clean,
        "raw_prefix_hex": prefix_hex,
        "raw_suffix_hex": suffix_hex
    }
