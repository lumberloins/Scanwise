# ScanWise Tech Guide (Onsite)

**Goal:** find out how a barcode scanner is configured in one scan.

## Steps

1. Open ScanWise (the **Tech Mode** tab).
2. Optional: under **Expected setup**, pick the system this workstation uses (e.g. Epic). Leave it on
   *Detect automatically* if you just want to know what the scanner is doing.
3. Scan any barcode. You don't need to click a text box: the whole page listens.

## Reading the result (top to bottom)

1. **Scanner** and **Barcode** pills, plus one sentence. Show this to the nurse:
   - ✓ Scanner **Working** · ✓ Barcode **Read OK** → both are fine. If the EMR still rejects the
     barcode, the problem is in the EMR or its settings.
   - ! Scanner **Needs setup** → the scanner works but is programmed wrong (the sentence says what).
   - ✗ Barcode **Problem with label** → the scanner is fine; the printed barcode is bad.
2. **What's in this barcode**: the barcode's contents in plain words. For medication and device
   barcodes (GS1): **Product (GTIN)**, plus the NDC when the GTIN carries one; **Expiration date**,
   marked EXPIRED in red if past; **Lot / Batch**; **Serial number**; and anything else on the label.
   For wristbands and other barcodes: the data itself.
3. **Exactly what the scanner sent**: every character in order, with hidden characters as coloured tags:
   🟩 `CR` Enter · `TAB` Tab · `LF` Line feed · 🟦 `GS` GS1 separator · 🟥 `FF` `NUL` `ESC` … problem
   characters · 🟪 `[F5]` an extra key press.
4. **Scanner setup**: prefix, suffix (Enter / Tab / Enter + Line feed), barcode type codes (AIM), GS1
   separators.

Everything technical (profile checks, GS1 fields in received order, bytes) is under **More details (for IT)**.

## If something odd happens

- **The browser tab closed or a new tab opened during the scan**: the scanner is sending control
  characters as Ctrl-key shortcuts. Note the scanner model and hand it to engineering.
- **"Host keyboard layout doesn't match"**: the PC's keyboard language differs from the scanner's
  keyboard-country setting.
- **"Letter case inverted"**: Caps Lock is on.
- **"The scanner sent key presses, but no characters could be read"**: open Engineering Mode, scan again,
  use **Export scan**, and send the file to IT.
- **A red "ScanWise hit an error" / "did not finish loading" box**: reload with Ctrl+Shift+R.

For anything deeper, use **Engineering Mode** or send the scanner to the engineering team.
