"""
GS1 Application Identifier table (GS1 General Specifications, section 3).

Each AI has a format spec:
    N14c        14 digits, last is a mod-10 check digit
    N6d         YYMMDD date (DD=00 means "end of month" where GS1 allows it)
    X..20       up to 20 characters from the GS1 AI encodable set (CSET 82)
    N3+X..9     components, consumed left to right
    N6..12      6 to 12 digits

Whether a GS (FNC1) must follow an element is NOT determined by its format.
It's determined by the *predefined length* table (GS1 GenSpecs fig. 7.8.5-2):
only AIs starting with 00-04, 11-20, 31-36 and 41 may be followed directly by
the next AI. Every other AI, even a fixed-length one such as (422), must be
followed by GS unless it is the last element.
"""
import re

PREDEFINED_LENGTH_PREFIXES = {
    "00", "01", "02", "03", "04", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "31", "32", "33", "34", "35", "36", "41",
}

# AI | spec | short title (healthcare-friendly wording)
_TABLE = """
00|N18c|SSCC (shipping container)
01|N14c|GTIN
02|N14c|GTIN of contained items
10|X..20|Batch / Lot
11|N6d|Production date
12|N6d|Due date
13|N6d|Packaging date
15|N6d|Best before date
16|N6d|Sell by date
17|N6d|Expiration date
20|N2|Internal product variant
21|X..20|Serial number
22|X..20|Consumer product variant
235|X..28|Third-party serial (TPX)
240|X..30|Additional product ID
241|X..30|Customer part number
242|N..6|Made-to-order variant
243|X..20|Packaging component number
250|X..30|Secondary serial number
251|X..30|Reference to source entity
253|N13c+X..17|Global Document Type ID (GDTI)
254|X..20|GLN extension
255|N13c+N..12|Global Coupon Number
30|N..8|Variable count
37|N..8|Count of trade items
400|X..30|Customer order number
401|X..30|Consignment number (GINC)
402|N17c|Shipment ID (GSIN)
403|X..30|Routing code
410|N13c|Ship to GLN
411|N13c|Bill to GLN
412|N13c|Purchased from GLN
413|N13c|Ship for GLN
414|N13c|Physical location GLN
415|N13c|Invoicing party GLN
416|N13c|Production / service location GLN
417|N13c|Party GLN
420|X..20|Ship to postal code
421|N3+X..9|Ship to postal code (with ISO country)
422|N3|Country of origin
423|N3+N..12|Country of initial processing
424|N3|Country of processing
425|N3+N..12|Country of disassembly
426|N3|Country of full processing
427|X..3|Country subdivision of origin
4300|X..35|Ship-to company name
4301|X..35|Ship-to contact
4302|X..70|Ship-to address line 1
4303|X..70|Ship-to address line 2
4304|X..70|Ship-to suburb
4305|X..70|Ship-to locality
4306|X..70|Ship-to region
4307|X2|Ship-to country code
4308|X..30|Ship-to telephone
4309|N20|Ship-to geolocation
4310|X..35|Return-to company name
4311|X..35|Return-to contact
4312|X..70|Return-to address line 1
4313|X..70|Return-to address line 2
4314|X..70|Return-to suburb
4315|X..70|Return-to locality
4316|X..70|Return-to region
4317|X2|Return-to country code
4318|X..20|Return-to postal code
4319|X..30|Return-to telephone
4320|X..35|Service code description
4321|N1|Dangerous goods flag
4322|N1|Authority to leave flag
4323|N1|Signature required flag
4324|N10D|Not before delivery date/time
4325|N10D|Not after delivery date/time
4326|N6d|Release date
7001|N13|NATO stock number
7002|X..30|Meat cut classification
7003|N10D|Expiration date and time
7004|N..4|Active potency
7005|X..12|Catch area
7006|N6d|First freeze date
7007|N6..12|Harvest date
7008|X..3|Aquatic species
7009|X..10|Fishing gear type
7010|X..2|Production method
7011|N6+N..4|Test by date
7020|X..20|Refurbishment lot ID
7021|X..20|Functional status
7022|X..20|Revision status
7023|X..30|GIAI of assembly
7040|N1+X3|GS1 UIC with extension
710|X..20|NHRN: Germany PZN
711|X..20|NHRN: France CIP
712|X..20|NHRN: Spain CN
713|X..20|NHRN: Brazil DRN
714|X..20|NHRN: Portugal AIM
715|X..20|NHRN: USA FDA NDC
716|X..20|NHRN: Italy AIC
7240|X..20|Protocol ID
7241|N2|AIDC media type
7242|X..25|Version control number
7250|N8|Date of birth (YYYYMMDD)
7251|N12|Date and time of birth
7252|N1|Biological sex
7253|X..40|Family name
7254|X..40|Given name
7255|X..10|Name suffix
7256|X..90|Full name
7257|X..70|Address
7258|X3|Baby birth sequence
7259|X..40|Baby of family name
8001|N14|Roll dimensions
8002|X..20|Cellular mobile ID
8003|N14+X..16|Returnable asset ID (GRAI)
8004|X..30|Individual asset ID (GIAI)
8005|N6|Price per unit of measure
8006|N14c+N2+N2|Trade item component (ITIP)
8007|X..34|IBAN
8008|N8+N..4|Production date and time
8009|X..50|Optically readable sensor indicator
8010|X..30|Component / part ID (CPID)
8011|N..12|CPID serial number
8012|X..20|Software version
8013|X..25|Global Model Number (GMN)
8017|N18c|GSRN: care provider
8018|N18c|GSRN: patient / recipient
8019|N..10|Service relation instance number
8020|X..25|Payment slip reference
8026|N14c+N2+N2|Contained ITIP
8030|Z..90|Digital signature
8110|X..70|Coupon code (North America)
8111|N4|Loyalty points
8112|X..70|Paperless coupon code
8200|X..70|Extended packaging URL
90|X..30|Internal: mutually agreed
91|X..90|Company internal
92|X..90|Company internal
93|X..90|Company internal
94|X..90|Company internal
95|X..90|Company internal
96|X..90|Company internal
97|X..90|Company internal
98|X..90|Company internal
99|X..90|Company internal
"""

_MEASURES = {
    "310": "Net weight (kg)", "311": "Length (m)", "312": "Width (m)", "313": "Height (m)",
    "314": "Area (m²)", "315": "Net volume (L)", "316": "Net volume (m³)",
    "320": "Net weight (lb)", "321": "Length (in)", "322": "Length (ft)", "323": "Length (yd)",
    "324": "Width (in)", "325": "Width (ft)", "326": "Width (yd)", "327": "Height (in)",
    "328": "Height (ft)", "329": "Height (yd)", "330": "Gross weight (kg)", "331": "Length, logistic (m)",
    "332": "Width, logistic (m)", "333": "Height, logistic (m)", "334": "Area, logistic (m²)",
    "335": "Gross volume (L)", "336": "Gross volume (m³)", "337": "Kilograms per m²",
    "340": "Gross weight (lb)", "341": "Length, logistic (in)", "342": "Length, logistic (ft)",
    "343": "Length, logistic (yd)", "344": "Width, logistic (in)", "345": "Width, logistic (ft)",
    "346": "Width, logistic (yd)", "347": "Height, logistic (in)", "348": "Height, logistic (ft)",
    "349": "Height, logistic (yd)", "350": "Area (in²)", "351": "Area (ft²)", "352": "Area (yd²)",
    "353": "Area, logistic (in²)", "354": "Area, logistic (ft²)", "355": "Area, logistic (yd²)",
    "356": "Net weight (troy oz)", "357": "Net volume (oz)", "360": "Net volume (qt)",
    "361": "Net volume (gal)", "362": "Gross volume (qt)", "363": "Gross volume (gal)",
    "364": "Net volume (in³)", "365": "Net volume (ft³)", "366": "Net volume (yd³)",
    "367": "Gross volume (in³)", "368": "Gross volume (ft³)", "369": "Gross volume (yd³)",
}
_AMOUNTS = {
    "390": ("N..15", "Amount payable (local currency)"), "391": ("N3+N..15", "Amount payable (ISO currency)"),
    "392": ("N..15", "Amount payable, single item"), "393": ("N3+N..15", "Amount payable, single item (ISO currency)"),
    "394": ("N4", "Percentage discount"), "395": ("N6", "Amount payable per unit of measure"),
}
# 7030-7039 processor approval numbers, 7230-7239 certification references.
_RANGES = [(f"703{d}", "N3+X..27", f"Processor approval number {d}") for d in range(10)] + \
          [(f"723{d}", "X2+X..28", f"Certification reference {d}") for d in range(10)]

_COMP = re.compile(r"^([NXZ])(?:(\d+)\.\.(\d+)|\.\.(\d+)|(\d+))([cdD]?)$")


def _parse_spec(spec):
    comps = []
    for part in spec.split("+"):
        m = _COMP.match(part)
        if not m:
            raise ValueError(f"bad spec {spec}")
        kind, lo, hi, vmax, fixed, flag = m.groups()
        if fixed:
            mn = mx = int(fixed)
        elif vmax:
            mn, mx = 1, int(vmax)
        else:
            mn, mx = int(lo), int(hi)
        comps.append({"kind": kind, "min": mn, "max": mx, "fixed": mn == mx,
                      "check": flag == "c", "date": flag == "d", "datetime": flag == "D"})
    return comps


def _entry(ai, spec, title, decimals=None):
    comps = _parse_spec(spec)
    fixed = all(c["fixed"] for c in comps)
    return {
        "ai": ai, "spec": spec, "title": title, "components": comps,
        "fixed_length": sum(c["max"] for c in comps) if fixed else None,
        "min_length": sum(c["min"] for c in comps),
        "max_length": sum(c["max"] for c in comps),
        "predefined": ai[:2] in PREDEFINED_LENGTH_PREFIXES,
        "decimals": decimals,
    }


AIS = {}
for _line in _TABLE.strip().splitlines():
    _ai, _spec, _title = _line.split("|")
    AIS[_ai] = _entry(_ai, _spec, _title)
for _p, _t in _MEASURES.items():
    for _n in range(10):
        AIS[f"{_p}{_n}"] = _entry(f"{_p}{_n}", "N6", _t, decimals=_n)
for _p, (_s, _t) in _AMOUNTS.items():
    for _n in range(10):
        AIS[f"{_p}{_n}"] = _entry(f"{_p}{_n}", _s, _t, decimals=_n if _p in ("390", "391", "392", "393") else None)
for _ai, _s, _t in _RANGES:
    AIS[_ai] = _entry(_ai, _s, _t)

# GS1 AIs are prefix-free by design; verify so the parser can match greedily.
for _a in AIS:
    for _b in AIS:
        if _a != _b and _b.startswith(_a):
            raise AssertionError(f"AI table not prefix-free: {_a} / {_b}")

# Character sets.
CSET82 = set("!\"%&'()*+,-./0123456789:;<=>?ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz")
CSET64 = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=")


def lookup(text, pos):
    """Return the AI entry starting at text[pos], trying 2-, 3- then 4-digit AIs."""
    for n in (2, 3, 4):
        cand = text[pos:pos + n]
        if len(cand) == n and cand in AIS:
            return AIS[cand]
    return None
