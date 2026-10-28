/**
 * ScanWise Main Application Bootstrap
 */
document.addEventListener('DOMContentLoaded', () => {
    const profileSelect = document.getElementById('profile-select');

    // Initialize Wedge Interceptor
    const wedge = new ScanWedgeInterceptor(async (rawInput, timings) => {
        const profileId = profileSelect ? profileSelect.value : 'epic_emr';
        
        try {
            const response = await fetch('/api/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    raw_input: rawInput,
                    profile_id: profileId,
                    keystroke_timings: timings
                })
            });

            if (!response.ok) {
                throw new Error(`Server returned status ${response.status}`);
            }

            const data = await response.json();
            if (data.status === 'success' && window.scanUI) {
                window.scanUI.renderResults(data);
            }
        } catch (err) {
            console.error('Scan analysis request failed:', err);
        }
    });

    // Auto-focus input box on click anywhere
    document.addEventListener('click', (e) => {
        const inputBox = document.getElementById('scan-input-box');
        if (inputBox && !['SELECT', 'BUTTON', 'A', 'TEXTAREA'].includes(e.target.tagName)) {
            inputBox.focus();
        }
    });
});
