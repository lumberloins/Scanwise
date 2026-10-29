package main

import "strings"

// Vendor IDs of common healthcare barcode scanner manufacturers.
var scannerVendors = map[string]string{
	"05e0": "Zebra / Symbol",
	"0c2e": "Honeywell / Metrologic",
	"0536": "Hand Held Products (Honeywell)",
	"05f9": "Datalogic / PSC",
}

var scannerWords = []string{"scanner", "barcode", "bar code", "symbol", "zebra", "honeywell", "metrologic",
	"datalogic", "hand held", "handheld products", "newland", "opticon", "code reader", "socket mobile", "imager"}

func detectScanner(name, vendorID string) (bool, string) {
	if v, ok := scannerVendors[strings.ToLower(vendorID)]; ok {
		return true, "vendor " + vendorID + " (" + v + ")"
	}
	lower := strings.ToLower(name)
	for _, w := range scannerWords {
		if strings.Contains(lower, w) {
			return true, "name contains \"" + w + "\""
		}
	}
	return false, ""
}
