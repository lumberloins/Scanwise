/**
 * ScanWise UI Controller & Diagnostic Renderer
 */
class ScanUI {
    constructor() {
        this.setupTabs();
    }

    setupTabs() {
        const tabBtns = document.querySelectorAll('.tab-btn');
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const targetId = btn.getAttribute('data-target');
                
                // Update active buttons
                tabBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');

                // Update active panes
                document.querySelectorAll('.tab-pane').forEach(pane => {
                    pane.classList.remove('active');
                });
                const targetPane = document.getElementById(targetId);
                if (targetPane) {
                    targetPane.classList.add('active');
                }
            });
        });

        const clearBtn = document.getElementById('clear-btn');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => {
                const box = document.getElementById('scan-input-box');
                if (box) {
                    box.value = '';
                    box.focus();
                }
                this.resetDisplay();
            });
        }
    }

    resetDisplay() {
        const banner = document.getElementById('verdict-banner');
        if (banner) {
            banner.className = 'verdict-banner verdict-idle';
            document.getElementById('verdict-headline').textContent = 'Ready for Scan Analysis';
            document.getElementById('verdict-recommendation').textContent = 'Scan a barcode to evaluate scanner configuration, EMR framing, and GS1 data integrity.';
        }

        document.getElementById('structured-data-table-container').innerHTML = '<p class="empty-state">No barcode parsed yet.</p>';
        document.getElementById('framing-results-container').innerHTML = '<p class="empty-state">No framing data available.</p>';
        document.getElementById('raw-inspector-container').innerHTML = '<p class="empty-state">No raw stream inspected yet.</p>';
    }

    renderResults(data) {
        this.renderVerdict(data.verdict);
        this.renderStructuredData(data.gs1_data, data.symbology);
        this.renderFraming(data.framing, data.symbology, data.timing);
        this.renderRawInspector(data.anomalies, data.raw_dump);

        // Play audio feedback
        if (window.scanAudio) {
            if (data.verdict.level === 'success') {
                window.scanAudio.playPass();
            } else {
                window.scanAudio.playAlert();
            }
        }
    }

    renderVerdict(verdict) {
        const banner = document.getElementById('verdict-banner');
        const headline = document.getElementById('verdict-headline');
        const recommendation = document.getElementById('verdict-recommendation');

        banner.className = `verdict-banner verdict-${verdict.level || 'warning'}`;
        headline.textContent = verdict.headline;
        recommendation.textContent = verdict.recommendation;
    }

    renderStructuredData(gs1Data, symbology) {
        const container = document.getElementById('structured-data-table-container');
        
        let html = `<p><strong>Symbology:</strong> ${symbology.symbology_name} (${symbology.standard})</p>`;
        if (symbology.has_aim_id) {
            html += `<p><strong>AIM Identifier:</strong> <code>${symbology.aim_id}</code> &bull; <em>${symbology.healthcare_use}</em></p><br>`;
        }

        if (gs1Data && gs1Data.elements && gs1Data.elements.length > 0) {
            html += `
                <table class="diagnostic-table">
                    <thead>
                        <tr>
                            <th>AI</th>
                            <th>Field Name</th>
                            <th>Raw Value</th>
                            <th>Formatted / Validation</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            gs1Data.elements.forEach(el => {
                let statusBadge = '';
                if (el.ai === '01') {
                    statusBadge = el.check_digit_valid ? '<span class="badge badge-subtle" style="color:#10b981">Valid Checksum</span>' : '<span class="badge badge-subtle" style="color:#ef4444">Invalid Checksum</span>';
                } else if (el.date_info) {
                    statusBadge = el.date_info.expired ? '<span class="badge badge-subtle" style="color:#ef4444">Expired</span>' : '<span class="badge badge-subtle" style="color:#10b981">Active Shelf-Life</span>';
                }

                html += `
                    <tr>
                        <td><code>(${el.ai})</code></td>
                        <td>${el.name}</td>
                        <td><code>${el.raw_value}</code></td>
                        <td>${el.formatted_value} ${statusBadge}</td>
                    </tr>
                `;
            });

            html += `</tbody></table>`;
        } else {
            html += `<p class="empty-state">No composite GS1 Application Identifiers found in payload.</p>`;
        }

        container.innerHTML = html;
    }

    renderFraming(framing, symbology, timing) {
        const container = document.getElementById('framing-results-container');

        const matchStatus = framing.profile_matched ? 
            '<span class="badge badge-subtle" style="color:#10b981">Profile Matched</span>' : 
            '<span class="badge badge-subtle" style="color:#ef4444">Framing Mismatch</span>';

        container.innerHTML = `
            <table class="diagnostic-table">
                <tr>
                    <th>Selected EMR Profile</th>
                    <td>${framing.profile_name}</td>
                </tr>
                <tr>
                    <th>Profile Match Status</th>
                    <td>${matchStatus}</td>
                </tr>
                <tr>
                    <th>Detected Prefix</th>
                    <td><code>${framing.prefix_detected || '(None)'}</code> (Hex: <code>${framing.raw_prefix_hex || 'N/A'}</code>)</td>
                </tr>
                <tr>
                    <th>Detected Suffix</th>
                    <td><code>${framing.suffix_detected || '(None)'}</code> (Hex: <code>${framing.raw_suffix_hex || 'N/A'}</code>)</td>
                </tr>
                <tr>
                    <th>Keystroke Timing</th>
                    <td>${timing.description} (Avg delta: ${timing.avg_inter_char_ms}ms)</td>
                </tr>
            </table>
        `;
    }

    renderRawInspector(anomalies, rawDump) {
        const container = document.getElementById('raw-inspector-container');

        let badgesHtml = '';
        if (anomalies.control_characters && anomalies.control_characters.length > 0) {
            anomalies.control_characters.forEach(c => {
                let badgeClass = c.is_safe ? 'badge-delimiter' : 'badge-harmful';
                if (c.category === 'line_terminator') badgeClass = 'badge-terminator';
                badgesHtml += `<span class="char-badge ${badgeClass}" title="${c.name}: ${c.description}">${c.symbol} (0x${c.hex})</span>`;
            });
        } else {
            badgesHtml = '<span class="empty-state">No control characters or hidden codes detected.</span>';
        }

        container.innerHTML = `
            <div style="margin-bottom: 1rem;">
                <strong>ASCII Visualization:</strong><br>
                <div style="background: var(--bg-primary); padding: 1rem; border-radius: var(--radius-sm); font-family: var(--font-mono); margin-top: 0.5rem; word-break: break-all;">
                    ${rawDump.ascii}
                </div>
            </div>
            <div style="margin-bottom: 1rem;">
                <strong>Hexadecimal Dump:</strong><br>
                <div style="background: var(--bg-primary); padding: 1rem; border-radius: var(--radius-sm); font-family: var(--font-mono); margin-top: 0.5rem; word-break: break-all; color: #60a5fa;">
                    ${rawDump.hex}
                </div>
            </div>
            <div>
                <strong>Control Characters / Delimiters:</strong><br>
                <div style="margin-top: 0.5rem;">
                    ${badgesHtml}
                </div>
            </div>
        `;
    }
}

window.scanUI = new ScanUI();
