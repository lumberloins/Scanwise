# ScanWise: Medical Barcode & Scanner Configuration Diagnostic Tool
## Architecture & Technical Build Specification

---

## 1. Executive Summary & Problem Statement

In healthcare environments (hospitals, outpatient clinics, surgical centers, and pharmacies), barcode scanners are critical for patient safety, bedside medication administration (BCMA), specimen tracking, and electronic health record (EHR/EMR) workflows.

When a barcode fails to scan in hospital applications like **Epic Hyperspace / Rover**, **Cerner Millennium / Oracle Health**, or **Meditech Expanse**, clinical staff frequently report that *"the scanner is broken"*. Site technicians and biomedical engineers are dispatched, only to find that the root cause is rarely hardware failure. Instead, failures typically stem from:
1. **Scanner Configuration Drifts:** Missing required prefixes/suffixes (preambles/postambles) such as Epic's `/DATA/` framing, standard `[CR]`/`[LF]`, or AIM symbology identifiers.
2. **Symbology Configuration:** The scanner firmware has specific symbologies disabled (e.g., GS1 DataMatrix or Aztec disabled, or FNC1 transmission disabled).
3. **Mangled Barcode Data:** Poor print contrast, damaged labels, missing GS1 Group Separator (`<GS>` / ASCII 29) delimiters, or invalid check digits.
4. **Hidden Command / Control Characters:** Scanners in USB HID Keyboard Wedge mode unintentionally transmitting raw ASCII control codes (`NUL`, `ETX`, `ESC`, `STX`, `SUB`) that corrupt EMR input fields.
5. **Virtual Desktop / Latency Drops:** Citrix, VMware Horizon, or RDP sessions dropping characters due to missing keystroke inter-character delays on the scanner.

**ScanWise** is a lightweight, zero-install, standalone web application engineered for site technicians to instantly test, decode, and diagnose barcode scanner configurations and barcode payloads in real time, conclusively proving whether an issue lies with the scanner hardware/configuration, the physical barcode label, or the host application.

---

## 2. Technical Stack & Runtime Environment

To ensure seamless deployment across clinical technician laptops, workstations on wheels (WOWs), and local IT bench machines without requiring complex external database engines or container runtimes:

- **Language:** Python 3.10+
- **Web Framework:** Flask (lightweight, modular, highly extensible)
- **WSGI Application Server:** Waitress (pure-Python, production-ready, multithreaded, zero native C-dependencies, native Windows and Linux support)
- **Frontend Architecture:** Modern Vanilla JavaScript (ES2022+), Semantic HTML5, and Custom Vanilla CSS.
  - Zero heavy frontend frameworks (no Node.js/npm build step required, instant loading, resilient).
  - Web Audio API for positive and negative diagnostic sound feedback (configurable).
  - High-precision Keystroke Event Timing API for hardware wedge capture and inter-character jitter analysis.
- **Data Persistence:** Stateless analysis engine with optional SQLite / client-side LocalStorage for technician scan session history and report export (PDF/JSON/CSV).
- **Packaging & Portability:** Single-directory execution, optional PyInstaller standalone executable bundling for Windows/Linux technician toolkits.

---

## 3. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             Hardware Input Layer                                 │
│  Barcode Scanner (Zebra, Honeywell, Code Corp, Datalogic) in USB HID Wedge Mode  │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │ Raw Keystroke Stream (Burst rate: 1-15ms)
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         Browser Client (Frontend UI)                             │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │ 1. Raw Event Interceptor (`keydown` / `beforeinput` / `input`)             │  │
│  │    - Intercepts ASCII 0x00-0x1F control codes (e.g. ASCII 29 <GS> / FNC1) │  │
│  │    - Measures inter-character arrival times (scanner vs human typing)      │  │
│  │    - Captures raw scan buffer before browser sanitization                  │  │
│  └─────────────────────────────────────┬──────────────────────────────────────┘  │
│                                        │ Cleaned payload + Raw hex + Timings     │
│                                        ▼                                         │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │ 2. Real-Time Visual Diagnostic Display                                     │  │
│  │    - Visual control character badges ([STX], [GS], [CR], [LF], [TAB])      │  │
│  │    - Hex viewer and character-by-character inspection grid                 │  │
│  │    - Audio feedback chimes (Pass / Warning / Fail)                         │  │
│  └─────────────────────────────────────┬──────────────────────────────────────┘  │
└────────────────────────────────────────┼─────────────────────────────────────────┘
                                         │ POST /api/analyze
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                       Flask Diagnostic Engine (Backend)                          │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │ 1. Scanner Framing & Preamble/Postamble Analyzer                           │  │
│  │    - AIM Symbology Identifier Decoder (e.g., ]C1, ]d2, ]A0, ]Q1)           │  │
│  │    - Target EMR Profile Matcher (Epic /DATA/, Cerner, Meditech, Generic)   │  │
│  │    - Preamble / Postamble isolation ([STX], [ETX], [CR], [LF], [TAB])      │  │
│  ├────────────────────────────────────────────────────────────────────────────┤  │
│  │ 2. Hidden Command & Control Character Inspector                            │  │
│  │    - Flags rogue ASCII controls (NUL, ESC, BEL, SUB, DLE)                  │  │
│  │    - Validates mandatory FNC1/GS separators                                │  │
│  ├────────────────────────────────────────────────────────────────────────────┤  │
│  │ 3. Healthcare Symbology & GS1 Parsing Engine                               │  │
│  │    - GS1 Application Identifier (AI) Parser (Fixed & Variable Length)      │  │
│  │    - FDA UDI & DSCSA Pharmaceutical Serialization Validator                │  │
│  │    - ISBT 128 Blood Bag Transfusion Specimen Decoder                       │  │
│  │    - Check Digit Verification (GTIN Modulo 10, Luhn, etc.)                 │  │
│  │    - Date Format & Expiration Validator (YYMMDD with 00 day rule)          │  │
│  ├────────────────────────────────────────────────────────────────────────────┤  │
│  │ 4. Verdict & Fault Engine                                                  │  │
│  │    - Category: Scanner Config Fault vs Barcode Data Fault vs Network/VDI   │  │
│  │    - Plain-English Technician Recommendations & Configuration Guides       │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Hardware Wedge & Input Capture Subsystem

> **Implementation note (2026-10):** capture now records raw key events (physical `code` + modifiers +
> timing) and decodes them server-side, so Ctrl-ASCII (`Ctrl+]`), Alt+numpad (`Alt+0029`) and
> function-key mappings all resolve to the correct byte. An optional native agent reads the OS input
> layer directly. See `BUILD_PLAN.md` and `docs/ENGINEERING_GUIDE.md`; where 4.2 differs, those win.

### 4.1 The Web Browser Wedge Challenge
In hospital environments, handheld scanners operate as **USB HID Keyboards**. When scanning into standard HTML inputs:
- Browsers frequently strip, suppress, or misinterpret non-printable ASCII control characters (such as ASCII 29 `<GS>` / Group Separator, which represents FNC1 in GS1 barcodes).
- Characters like `\r` (Enter) or `\t` (Tab) trigger immediate form submission or field focus shifts, prematurely cutting off input.
- Scanners configured with fast baud/character burst rates can drop characters if the web page event loop is blocked.

### 4.2 Interception Strategy
The frontend uses a multi-layered input capture strategy:
1. **Low-Level `keydown` & `beforeinput` Listener:**
   - Captures keys before browser default handling.
   - Converts non-printable key events (e.g., `event.key === 'Enter'`, `event.key === 'Tab'`, `event.key === 'GroupSeparator'`) into explicit token representations.
   - Prevents accidental form submissions with `e.preventDefault()` on framing postambles.
2. **Inter-Character Timing (Burst Detection):**
   - Records high-resolution timestamps (`performance.now()`) for every incoming keystroke.
   - **Scanner Signature:** Keystrokes arriving with inter-character deltas $< 25\text{ ms}$ are tagged as Scanner Input. Keystrokes $> 80\text{ ms}$ indicate manual technician typing.
   - **VDI / Latency Jitter Detection:** If keystrokes alternate between $<5\text{ ms}$ and $>60\text{ ms}$ within a single scan burst, ScanWise flags a potential **Citrix / RDP / Virtual Desktop keystroke drop issue**.
3. **Dedicated Target Scanning Surface:**
   - Prominent, auto-focused scan target box that automatically recaptures focus if clicked outside, ensuring technicians can scan repeatedly without manual mouse clicks.

---

## 5. Supported Healthcare Symbologies & Specifications

| Symbology | Healthcare Context & Use Case | Diagnostic Identification Rules |
| :--- | :--- | :--- |
| **GS1 DataMatrix (2D)** | FDA UDI (medical devices), DSCSA pharmaceutical serialization, unit-dose oral meds. | AIM ID: `]d2` (GS1 mode) or `]d1` (standard). Contains FNC1/ASCII 29. |
| **GS1-128 (Code 128 w/ FNC1)** | Bulk pharmaceuticals, medical supply chain cases, blood products (ISBT 128). | AIM ID: `]C1`. Leading FNC1 character. |
| **Raw Code 128** | Patient wristbands, specimen collection tubes, internal hospital order numbers. | AIM ID: `]C0`. Standard alphanumeric data without FNC1 preamble. |
| **ISBT 128** | Blood bag transfusion medicine (DIN - Donation Identification Number, Blood Group). | Starts with `=` or `&`, strict ISBT data structure compliance. |
| **Aztec Code (2D)** | Patient ID wristbands, lab specimen slides (common in Cerner and Epic lab workflows). | AIM ID: `]z0` to `]z3` or `]A0`. High data density, square center finder. |
| **GS1 DataBar (Expanded / Stacked)** | Small unit-dose hospital pharmacy syringes, vials, blister packs. | AIM ID: `]e0`. Variable-length stacked symbology. |
| **QR Code / Micro QR** | Vaccine administration cards, equipment asset tags, patient portal links. | AIM ID: `]Q1` (GS1 QR) or `]Q0` (Standard QR). |
| **Code 39 / Codabar** | Legacy lab automation racks, older blood bank tags. | AIM ID: `]A0` / `]F0`. Start/stop asterisk or standard framed characters. |
| **PDF417** | State patient identification cards, military medical IDs. | AIM ID: `]L0` to `]L2`. Stacked linear multi-row format. |

---

## 6. GS1 Application Identifier (AI) Parser & Validator

ScanWise includes a comprehensive GS1 decoding engine tailored specifically to pharmaceutical and medical device standards (DSCSA & FDA UDI regulations).

### 6.1 Critical Healthcare Application Identifiers Dictionary

| AI | Meaning | Format | Type | Healthcare Significance |
| :---: | :--- | :--- | :---: | :--- |
| **01** | Global Trade Item Number (GTIN) | 14 Numeric (`N14`) | Fixed | NDC/Package packaging identifier |
| **10** | Batch or Lot Number | Up to 20 Alphanumeric (`X..20`) | Variable | Recall tracking & drug compounding |
| **11** | Production Date | 6 Numeric (`N6` YYMMDD) | Fixed | Manufacturing date verification |
| **17** | Expiration Date | 6 Numeric (`N6` YYMMDD) | Fixed | Drug shelf-life safety (DD=00 rule) |
| **21** | Serial Number | Up to 20 Alphanumeric (`X..20`) | Variable | DSCSA serialization verification |
| **30** | Variable Count | Up to 8 Numeric (`N..8`) | Variable | Unit dose counting |
| **240**| Additional Product Identification | Up to 30 Alphanumeric (`X..30`)| Variable | Hospital internal catalog numbers |
| **8005**| Normalized Packaging Unit | 6 Numeric (`N6`) | Fixed | Medical unit-dose packaging |

### 6.2 Variable-Length Parsing & FNC1 / ASCII 29 (`<GS>`) Handling
- Fixed-length fields (e.g. AI `01` which is exactly 14 digits, AI `17` which is exactly 6 digits) are extracted immediately.
- Variable-length fields (e.g. AI `10` Lot, AI `21` Serial) **must** be terminated by an FNC1 character (transmitted by the scanner as ASCII 29 `<GS>`, `\x1d`), unless they occur as the final field in the barcode.
- **Fault Detection:** If a variable-length AI is followed immediately by another AI without an intervening `<GS>` delimiter, ScanWise flags a **Fatal Barcode Encoding Fault (Missing FNC1/GS Delimiter)**.

### 6.3 Check Digit & Date Validation
- **GTIN-14 Modulo 10 Check:** Validates the standard alternating $\times 3, \times 1$ modulo 10 algorithm on AI (01). Flags invalid check digits.
- **Expiration Date Validation:**
  - Parses `YYMMDD`.
  - Implements GS1 Rule: If `DD == "00"`, the expiration date is the **last calendar day** of the specified month.
  - Flags impossible dates (e.g., Month `13`, Day `32`, or invalid leap years).
  - Highlights expired medications with a visual warning badge.

---

## 7. Scanner Framing & EMR Profile Engine

Different EMRs require specific scanner framing so the clinical software knows how to route input to the active window or field. ScanWise allows technicians to select an **EMR Target Profile** to test against.

### 7.1 Pre-configured EMR Profiles

#### A. Epic Systems (Hyperspace & Rover)
- **Framing Option 1 (Epic Standard Preamble/Postamble):**
  - Expected Prefix: `/DATA/` or `]` or configured leading character.
  - Expected Suffix: `\r` (Enter) or `\t` (Tab) or `/DATA/` closing tag.
- **Framing Option 2 (Rover Mobile):**
  - Requires AIM Symbology Identifiers to prevent misinterpreting Code 128 as GS1 DataMatrix.
- **Configuration Check:** Verifies that scanner wedge delivers the expected prefix/suffix wrapper cleanly without extra spaces or truncated slashes.

#### B. Cerner Millennium
- Expected Prefix: Often configured with `~` or custom ASCII header.
- Expected Suffix: `<CR><LF>` or `<Enter>`.

#### C. Meditech Expanse
- Expected Suffix: `<CR>` or `<TAB>` with strict keystroke delay ($> 10\text{ ms}$) to prevent field overruns.

#### D. Raw / Diagnostic Mode (Default)
- Does not enforce a specific EMR framing. Isolates any detected prefix, payload, and suffix automatically.

### 7.2 AIM Symbology Identifier Processing
When a barcode scanner is configured with "Transmit AIM Code ID":
- It prepends a 3-character sequence: `]` + `[Code Character]` + `[Modifier Character]`.
- Examples:
  - `]C1` = Code 128 with FNC1 in 1st position (GS1-128).
  - `]d2` = DataMatrix with GS1 format (FNC1 in 1st position).
  - `]A0` = Aztec Code (standard).
  - `]Q1` = QR Code (GS1 mode).
- ScanWise parses the AIM ID to immediately tell the technician whether the scanner has the appropriate symbology mode enabled in its firmware.

---

## 8. Fault Detection & Anomaly Classification Engine

When a scan is evaluated, ScanWise classifies the findings into one of three clear categories:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ScanWise Verdict Engine                         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         ▼                          ▼                          ▼
┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐
│  Scanner Config  │      │   Barcode Data   │      │ Environment/Host │
│      Fault       │      │      Fault       │      │      Fault       │
└──────────────────┘      └──────────────────┘      └──────────────────┘
```

### 1. Scanner Configuration Faults
- **Missing EMR Framing:** Selected Epic profile requires `/DATA/`, but scanner transmitted raw data without preambles.
- **AIM ID Disabled:** Scanner is not transmitting AIM identifiers required by clinical software to distinguish medication barcodes from patient wristbands.
- **FNC1 Translation Disabled:** Scanner transmitted raw unprintable `\x1d` without proper wedge mapping, or stripped FNC1 entirely, causing GS1 parsing to collapse.
- **Unwanted Extra Suffixes:** Scanner is sending double Enter (`\r\r`) or `<CR><LF>` when the EMR expects only `<CR>`, causing form jumping or premature dialog closure.

### 2. Barcode Data & Print Faults
- **Missing FNC1 Delimiter:** Barcode contains variable AI (10) Lot followed by AI (17) Exp, but omitted the required `<GS>` separator.
- **Invalid Check Digit:** GTIN-14 check digit mismatch (indicates bad reprint or corrupted barcode encoding).
- **Invalid Date Encoding:** Expiration date contains non-numeric characters, impossible month (e.g. `240231` or `241301`).
- **Mangled Characters / Parity Errors:** Decoding yielded replacement characters (`` / `\ufffd`) or truncated bitstreams.

### 3. Environment & Host Faults
- **Rogue Control Characters:** Detected `NUL` (0x00), `BEL` (0x07), `ESC` (0x1B), or `ETX` (0x03) in the stream, which typically crash terminal emulators or break web EMR textboxes.
- **Keystroke Jitter (Citrix/RDP Lag):** Scanner burst timing exhibits erratic spikes ($>100\text{ ms}$ gaps mid-scan), pointing to virtual channel network latency rather than hardware failure.

---

## 9. User Interface & Technician Experience Design

The user interface must be clean, responsive, and purpose-built for technicians on clinical floors carrying laptops or working on bedside WOWs.

### 9.1 Visual Layout & Key Components
1. **Header Bar:**
   - App title, status indicator (Scanner Ready / Active), Target EMR Profile selector dropdown (Epic EMR `/DATA/`, Cerner, Meditech, Generic GS1, Raw Pass-Through), and Sound Toggle.
2. **Primary Scan Capture Zone:**
   - Large, prominent, high-contrast input area with persistent autofocus.
   - Pulsing visual state when waiting for scan; instant flash (Green for Valid, Amber for Warning, Red for Fault) on scan reception.
3. **Verdict Banner:**
   - Giant, unmistakable status badge:
     - `[ PASS ] Scanner and Barcode Valid`
     - `[ SCANNER FAULT ] Missing Epic /DATA/ Framing`
     - `[ BARCODE FAULT ] Invalid GS1 Lot Separator`
     - `[ WARNING ] Rogue Control Characters Detected`
   - Technician Next-Step Action recommendation box (e.g., *"Scan the 'Enable AIM ID' barcode from the Zebra programming sheet"*).
4. **Three-Tab Diagnostic Breakdown:**
   - **Tab 1: Structured Medical Data (GS1 / UDI / EMR):**
     - Table of extracted fields: GTIN, Trade Name/Catalog, Lot/Batch, Expiration (with human-readable date & countdown), Serial Number.
     - Check digit status and validity indicators.
   - **Tab 2: Scanner Configuration & Framing:**
     - Prefix analysis: Detected prefix vs Expected profile prefix.
     - Suffix analysis: Detected suffix vs Expected profile suffix.
     - Detected Symbology & AIM Identifier breakdown.
     - Keystroke timing statistics (total scan burst time, average inter-character latency, jitter rating).
   - **Tab 3: Raw Byte & Hidden Character Inspector:**
     - Interactive visual display where invisible control characters are rendered as colored pill badges:
       - Green badge for standard `[CR]` / `[LF]`
       - Blue badge for valid GS1 `[GS]` (ASCII 29)
       - Red badge for rogue command characters (`[NUL]`, `[ESC]`, `[ETX]`)
     - Side-by-side Hexadecimal / ASCII dump.
5. **Action Toolbar:**
   - **Copy Clean Data:** Copies payload with or without framing.
   - **Export Diagnostic Report:** Generates a printable single-page PDF / HTML report or JSON log that the technician can attach to a ServiceNow/Epic ticket to prove the scanner is innocent.
   - **Clear / Reset:** Clears history for next test.

---

## 10. Application Directory & Module Structure

```
scanwise/
│
├── run.py                     # Entry point: initializes Waitress server and launches browser
├── requirements.txt           # Python dependencies (Flask, waitress, etc.)
├── vision.md                  # System architecture and design specification (this file)
│
├── scanwise/                  # Core application package
│   ├── __init__.py            # Flask app factory
│   ├── config.py              # Application settings, default ports, log config
│   │
│   ├── parsers/               # Domain parsing engines
│   │   ├── __init__.py
│   │   ├── aim_codes.py       # AIM symbology code identifier dictionary and matcher
│   │   ├── ascii_chars.py     # ASCII control character definitions & safety ratings
│   │   ├── gs1_parser.py      # GS1 AI parser, variable length handler, check digit rules
│   │   ├── isbt_parser.py     # ISBT 128 blood bag specification decoder
│   │   └── udi_parser.py      # FDA UDI & DSCSA serialization parser
│   │
│   ├── diagnostics/           # Scanner and framing diagnostic engines
│   │   ├── __init__.py
│   │   ├── framing.py         # Prefix/suffix extractor and EMR profile verifier (Epic /DATA/, etc.)
│   │   ├── anomalies.py       # Hidden command character and mangled data detector
│   │   ├── timing.py          # Keystroke inter-arrival timing and latency analyzer
│   │   └── verdict.py         # Rule-based fault categorization and recommendation engine
│   │
│   ├── profiles/              # Target EMR configuration profiles
│   │   ├── __init__.py
│   │   └── emr_profiles.json  # Profiles: Epic Hyperspace, Epic Rover, Cerner, Meditech, Generic
│   │
│   ├── routes/                # Flask blueprints
│   │   ├── __init__.py
│   │   ├── api.py             # REST API: /api/analyze, /api/profiles, /api/report
│   │   └── views.py           # Web views: GET / (Main diagnostic dashboard)
│   │
│   ├── static/                # Static assets (Vanilla, zero build step)
│   │   ├── css/
│   │   │   ├── main.css       # Core design system, variables, responsive layout
│   │   │   └── diagnostics.css# Badges, hex viewer, timing charts, verdict banners
│   │   ├── js/
│   │   │   ├── wedge.js       # Low-level HID keyboard event listener & timing recorder
│   │   │   ├── audio.js       # Web Audio API sound generator (chimes/buzzers)
│   │   │   ├── ui.js          # DOM rendering, tab switching, hex renderer, report export
│   │   │   └── app.js         # Application bootstrap and controller
│   │   └── sounds/            # Fallback audio assets (or synthesized via Web Audio)
│   │
│   └── templates/             # Jinja2 HTML templates
│       ├── base.html          # Base layout, meta tags, fonts
│       └── dashboard.html     # Main diagnostic workstation interface
│
└── tests/                     # Comprehensive automated test suite
    ├── __init__.py
    ├── test_gs1_parser.py     # Unit tests for GS1 AI extraction and check digits
    ├── test_framing.py        # Unit tests for Epic /DATA/ and EMR framing
    ├── test_anomalies.py      # Unit tests for hidden command characters and mangled payloads
    ├── test_api.py            # Integration tests for Flask REST endpoints
    └── sample_payloads.json   # Synthetic test scan barcodes from real-world hospital scenarios
```

---

## 11. REST API Specification

### 11.1 `POST /api/analyze`
Receives raw scan data, timestamps, and active profile; performs end-to-end diagnostic analysis.

#### Request Body
```json
{
  "raw_input": "]d201003012345678971725123110BATCH999\u001d21SER12345\r",
  "profile_id": "epic_emr",
  "keystroke_timings": [0, 4.2, 7.8, 12.1, 16.5, 20.2]
}
```

#### Response Body
```json
{
  "status": "success",
  "timestamp": "2026-10-21T14:30:00Z",
  "verdict": {
    "category": "BARCODE_FAULT",
    "level": "warning",
    "headline": "Barcode Format Warning: Missing Lot Delimiter",
    "recommendation": "The scanner is functioning correctly, but the physical barcode label is missing the FNC1/GS delimiter after the Batch/Lot field."
  },
  "framing": {
    "profile_id": "epic_emr",
    "profile_name": "Epic EMR (Standard /DATA/)",
    "profile_matched": true,
    "prefix_detected": "/DATA/",
    "suffix_detected": "[CR]",
    "raw_prefix_hex": "2f444154412f",
    "raw_suffix_hex": "0d"
  },
  "symbology": {
    "aim_id": "]d2",
    "symbology_name": "GS1 DataMatrix",
    "symbology_standard": "ISO/IEC 16022",
    "is_gs1": true
  },
  "anomalies": {
    "has_hidden_controls": false,
    "control_characters": [
      { "char": "[GS]", "ascii_code": 29, "hex": "1D", "category": "gs1_delimiter", "is_safe": true },
      { "char": "[CR]", "ascii_code": 13, "hex": "0D", "category": "line_terminator", "is_safe": true }
    ],
    "mangled_data": false,
    "timing_jitter_detected": false
  },
  "gs1_data": {
    "valid": true,
    "elements": [
      { "ai": "01", "name": "GTIN", "raw_value": "00301234567897", "formatted_value": "00301234567897", "check_digit_valid": true },
      { "ai": "17", "name": "Expiration Date", "raw_value": "251231", "formatted_value": "2025-12-31", "is_expired": false },
      { "ai": "10", "name": "Batch/Lot", "raw_value": "BATCH999", "formatted_value": "BATCH999" },
      { "ai": "21", "name": "Serial Number", "raw_value": "SER12345", "formatted_value": "SER12345" }
    ]
  },
  "raw_dump": {
    "ascii": "]d201003012345678971725123110BATCH999<GS>21SER12345<CR>",
    "hex": "5d 64 32 30 31 30 30 33 30 31 32 33 34 35 36 37 38 39 37 31 37 32 35 31 32 33 31 31 30 42 41 54 43 48 39 39 39 1d 32 31 53 45 52 31 32 33 34 35 0d"
  }
}
```

### 11.2 `GET /api/profiles`
Returns all active EMR scanner profiles (Epic, Cerner, Meditech, Raw) with expected prefixes, suffixes, and required AIM identifiers.

---

## 12. Token-Budgeted Implementation Roadmap

To prevent token exhaustion and ensure immaculate quality, the build is divided into **8 granular, self-contained sub-phases**. Each phase has specific file targets, implementation scope, and a mandatory verification step before proceeding to the next.

### Phase 1: Project Scaffolding & Configuration
- **Scope:** Initialize project directory structure, `requirements.txt`, application factory (`scanwise/__init__.py`), configuration (`scanwise/config.py`), and Waitress entry point (`run.py`).
- **Files Created:**
  - `requirements.txt` (`flask`, `waitress`, `pytest`)
  - `run.py`
  - `scanwise/__init__.py`
  - `scanwise/config.py`
- **Verification:** Run `python run.py` (or pytest) to verify clean startup and module imports.

### Phase 2: ASCII Control Characters & AIM Symbology Dictionaries
- **Scope:** Implement core lookup tables and classifiers for ASCII control codes (0x00–0x7F) and AIM symbology identifiers (`]C0`, `]C1`, `]d2`, `]A0`, `]Q1`, etc.).
- **Files Created:**
  - `scanwise/parsers/ascii_chars.py`
  - `scanwise/parsers/aim_codes.py`
- **Verification:** Unit test character classification (safe whitespace vs GS1 delimiter vs harmful control code).

### Phase 3: GS1 Application Identifier (AI) Parser & Modulo 10 Engine
- **Scope:** Implement robust GS1 barcode parsing supporting fixed and variable-length AIs (`01`, `10`, `11`, `17`, `21`, `240`), Modulo 10 check digit verification, and date parsing (including the `DD == 00` rule).
- **Files Created:**
  - `scanwise/parsers/gs1_parser.py`
- **Verification:** Run unit tests with synthetic GS1 barcodes (GTIN-14, Lot, Expiration).

### Phase 4: Diagnostic Engines (Framing, Anomalies, Verdict)
- **Scope:** Implement EMR framing extraction, hidden command character detection, keystroke timing/jitter analysis, and the rule-based verdict fault engine (`PASS`, `SCANNER_FAULT`, `BARCODE_FAULT`, `ENVIRONMENT_FAULT`).
- **Files Created:**
  - `scanwise/diagnostics/framing.py`
  - `scanwise/diagnostics/anomalies.py`
  - `scanwise/diagnostics/timing.py`
  - `scanwise/diagnostics/verdict.py`
- **Verification:** Unit test framing extraction against Epic `/DATA/` and anomaly detection against injected control codes.

### Phase 5: EMR Profiles & Flask REST API
- **Scope:** Create EMR profiles JSON repository (`scanwise/profiles/emr_profiles.json`) and Flask REST endpoints (`/api/analyze`, `/api/profiles`, `/api/health`, and view route `/`).
- **Files Created:**
  - `scanwise/profiles/emr_profiles.json`
  - `scanwise/routes/api.py`
  - `scanwise/routes/views.py`
- **Verification:** Test API endpoints using pytest/requests or curl.

### Phase 6: HTML Templates & CSS Design System
- **Scope:** Build responsive, high-contrast technician dashboard templates and CSS stylesheets (main layout, diagnostic cards, control character pill badges, hex viewer).
- **Files Created:**
  - `scanwise/templates/base.html`
  - `scanwise/templates/dashboard.html`
  - `scanwise/static/css/main.css`
  - `scanwise/static/css/diagnostics.css`
- **Verification:** Inspect rendered HTML structure and responsive layout.

### Phase 7: Frontend JavaScript (Wedge Interceptor, Audio & UI Controller)
- **Scope:** Implement low-level `keydown`/`beforeinput` hardware wedge capture, Web Audio API chime generator, real-time tab switching, hex dump renderer, and report exporter.
- **Files Created:**
  - `scanwise/static/js/wedge.js`
  - `scanwise/static/js/audio.js`
  - `scanwise/static/js/ui.js`
  - `scanwise/static/js/app.js`
- **Verification:** Browser simulation / end-to-end scan wedge testing.

### Phase 8: Comprehensive Automated Test Suite & Sample Payloads
- **Scope:** Populate automated test suite (`tests/test_gs1_parser.py`, `tests/test_framing.py`, `tests/test_anomalies.py`, `tests/test_api.py`) and real-world medical test barcode library (`tests/sample_payloads.json`).
- **Files Created:**
  - `tests/test_gs1_parser.py`
  - `tests/test_framing.py`
  - `tests/test_anomalies.py`
  - `tests/test_api.py`
  - `tests/sample_payloads.json`
- **Verification:** Run full test suite via `pytest -v` confirming 100% test pass rate.

---

## 13. Operational Verification & Acceptance Criteria

When Gemini completes the build, the application will be validated against the following criteria:
1. **Server Execution:** Runs cleanly via `python run.py` powered by Waitress on port 5000 with zero startup errors.
2. **Scanner Wedge Handling:** Captures rapid burst scans without dropped characters or page reloads.
3. **Epic /DATA/ Framing Diagnosis:** Correctly identifies whether `/DATA/` framing is present, malformed, or missing.
4. **GS1 Pharmaceutical Decoding:** Successfully splits composite medication barcodes into GTIN, Lot, Expiration Date, and Serial Number, flagging missing `<GS>` separators or expired dates.
5. **Hidden Command Character Trapping:** Detects and flags rogue non-printable characters (`0x00`-`0x1F`) in raw hex view and visual badges.
6. **Technician Verdict Clarity:** Outputs clear, unambiguous diagnostic guidance indicating whether the scanner, barcode, or network is at fault.
