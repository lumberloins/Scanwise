/**
 * ScanWise Advanced Global Hardware Wedge & Keystroke Interceptor
 * Intercepts all raw keystrokes globally, preventing browser default actions (like Tab shifting focus)
 * during high-speed scanner bursts.
 */
class ScanWedgeInterceptor {
    constructor(onScanComplete) {
        this.onScanComplete = onScanComplete;
        this.timings = [];
        this.rawBuffer = "";
        this.keyEvents = [];
        this.scanTimeout = null;
        
        this.setupGlobalListeners();
    }

    setupGlobalListeners() {
        window.addEventListener('keydown', (e) => {
            const now = performance.now();
            
            // Determine if this is part of a high-speed scanner burst (< 40ms delta)
            let isBurst = false;
            if (this.timings.length > 0) {
                const delta = now - this.timings[this.timings.length - 1];
                if (delta < 50) {
                    isBurst = true;
                }
            } else {
                // First key of potential scan
                isBurst = true;
            }

            // If we are actively receiving a scanner burst, suppress default browser behavior
            // (e.g., prevent Tab from changing focus, prevent Enter from submitting forms, prevent Form Feed / PageUp scrolling)
            if (isBurst || e.key === 'Tab' || e.key === 'Enter' || e.key === 'PageDown') {
                // Only suppress if it's coming into our capture context or global
                const activeEl = document.activeElement;
                const isInputFocused = activeEl && (activeEl.tagName === 'TEXTAREA' || activeEl.tagName === 'INPUT');
                
                if (isInputFocused || this.timings.length > 0) {
                    e.preventDefault();
                }
            }

            this.timings.push(now);

            // Record key details
            let charToAdd = "";
            if (e.key === 'Enter') {
                charToAdd = '\r';
            } else if (e.key === 'Tab') {
                charToAdd = '\t';
            } else if (e.key === 'PageDown') {
                charToAdd = '\x0c'; // Form feed / page down representation
            } else if (e.key.length === 1) {
                charToAdd = e.key;
            } else {
                // Special key representation
                charToAdd = `[${e.key}]`;
            }

            this.rawBuffer += charToAdd;
            this.keyEvents.push({
                key: e.key,
                code: e.code,
                keyCode: e.keyCode || e.which,
                char: charToAdd,
                time: now
            });

            // Debounce scan completion (60ms silence)
            clearTimeout(this.scanTimeout);
            this.scanTimeout = setTimeout(() => {
                if (this.rawBuffer.length > 1) {
                    this.finalizeScan();
                }
            }, 70);
        }, true); // Use capture phase
    }

    finalizeScan() {
        clearTimeout(this.scanTimeout);
        const payload = this.rawBuffer;
        const timings = [...this.timings];
        const events = [...this.keyEvents];
        
        // Reset buffers
        this.rawBuffer = "";
        this.timings = [];
        this.keyEvents = [];

        const inputBox = document.getElementById('scan-input-box');
        if (inputBox) {
            inputBox.value = payload
                .replace(/\r/g, '<CR>')
                .replace(/\t/g, '<TAB>')
                .replace(/\n/g, '<LF>')
                .replace(/\x1d/g, '<GS>');
        }

        if (payload.trim().length > 0 && typeof this.onScanComplete === 'function') {
            this.onScanComplete(payload, timings, events);
        }
    }
}
