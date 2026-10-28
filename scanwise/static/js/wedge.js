/**
 * ScanWise Hardware Wedge & Keystroke Timing Interceptor
 */
class ScanWedgeInterceptor {
    constructor(onScanComplete) {
        this.onScanComplete = onScanComplete;
        this.timings = [];
        this.rawBuffer = "";
        this.scanTimeout = null;
        this.isScanning = false;
        
        this.setupListeners();
    }

    setupListeners() {
        const inputBox = document.getElementById('scan-input-box');
        if (!inputBox) return;

        inputBox.addEventListener('keydown', (e) => {
            const now = performance.now();
            
            // If new scan burst starting after pause
            if (this.timings.length === 0 || (now - this.timings[this.timings.length - 1] > 150)) {
                this.timings = [];
                this.rawBuffer = "";
            }

            this.timings.push(now);

            // Handle terminator keys or special tokens
            if (e.key === 'Enter') {
                e.preventDefault();
                this.rawBuffer += '\r';
                this.finalizeScan();
                return;
            } else if (e.key === 'Tab') {
                e.preventDefault();
                this.rawBuffer += '\t';
                this.finalizeScan();
                return;
            } else if (e.key.length === 1) {
                this.rawBuffer += e.key;
            }

            // Debounce scanner burst completion (if no more keys arrive within 60ms)
            clearTimeout(this.scanTimeout);
            this.scanTimeout = setTimeout(() => {
                if (this.rawBuffer.length > 3) {
                    this.finalizeScan();
                }
            }, 60);
        });

        // Also allow manual pasting or clicking analyze button
        inputBox.addEventListener('input', (e) => {
            // Handled via keydown for precise timing, but syncs value
        });
    }

    finalizeScan() {
        clearTimeout(this.scanTimeout);
        const payload = this.rawBuffer;
        const timings = [...this.timings];
        
        // Reset buffers
        this.rawBuffer = "";
        this.timings = [];

        const inputBox = document.getElementById('scan-input-box');
        if (inputBox) {
            inputBox.value = payload.replace('\r', '<CR>').replace('\t', '<TAB>');
        }

        if (payload.trim().length > 0 && typeof this.onScanComplete === 'function') {
            this.onScanComplete(payload, timings);
        }
    }
}
