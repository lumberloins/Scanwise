# ScanWise Tech Guide (Onsite)

**Goal:** find out how a barcode scanner is configured in one scan.

## Steps

1. Open ScanWise (the **Tech Mode** tab).
2. Optional: under **Expected setup**, pick the system this workstation uses (e.g. Epic). Leave it on
   *Detect automatically* if you just want to know what the scanner is doing.
3. Scan any barcode. You don't need to click a text box: the whole page listens.

## Reading the result

| Row | What it tells you |
|---|---|
| **Configured for** | Which known setup the scanner matches (Epic, Cerner, Meditech), or what it does instead. |
| **Prefix** | What the scanner adds *before* the barcode (e.g. `/DATA/`), or None. |
| **Suffix** | What it adds *after* the barcode: **CR** = Enter, **TAB** = Tab, **CR LF** = Enter + Line Feed, or None. |
| **AIM symbology IDs** | On/Off. When on, the scan starts with a code like `]d2` that says what kind of barcode it was. |
| **GS1 separators** | For medication/device barcodes: *Present* is good. *Missing* means a separator is missing. |
| **Profile check** | ✓ / ✗ for every known setup, with the reason when it doesn't match. |

**What the scanner typed** shows the data with every hidden character as a coloured tag:

- 🟩 green `CR` `LF` `TAB`: Enter / Line Feed / Tab (normal suffixes)
- 🟦 blue `GS`: GS1 separator (normal in medication barcodes)
- 🟨 yellow `STX` `ETX`: framing characters (usually a mis-programmed scanner)
- 🟥 red `FF` `NUL` `ESC` `BEL` …: problem characters
- 🟪 purple `[F5]` `[PageDown]`: the scanner pressed an extra key

## The banner

- **Green PASS**: the scanner and barcode are fine. The problem is elsewhere (the application or the workstation).
- **Red / amber**: read the sentence under the headline. It says what to do, e.g. *"Program the scanner for
  Epic: prefix "/DATA/", suffix CR (Enter)."*

## If something odd happens

- **The browser tab closed or a new tab opened during the scan**: the scanner is sending control
  characters as Ctrl-key shortcuts. Note the scanner model and hand it to engineering.
- **"Host keyboard layout doesn't match"**: the PC's keyboard language differs from the scanner's
  keyboard-country setting.
- **"Letter case inverted"**: Caps Lock is on.

For anything deeper, use **Engineering Mode** or send the scanner to the engineering team.
