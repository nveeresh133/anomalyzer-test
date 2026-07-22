document.addEventListener('DOMContentLoaded', () => {
    const clusterSelect = document.getElementById('cluster-select');
    const namespaceSelect = document.getElementById('namespace-select');
    const userPromptInput = document.getElementById('user-prompt');
    const investigateBtn = document.getElementById('investigate-btn');
    
    const idleState = document.getElementById('idle-state');
    const loadingState = document.getElementById('loading-state');
    const reportView = document.getElementById('report-view');
    const thoughtStepsContainer = document.getElementById('thought-steps-container');

    // Init Clusters and Namespaces
    loadClusters();

    async function loadClusters() {
        try {
            const res = await fetch('/api/v1/clusters');
            if (res.ok) {
                const clusters = await res.json();
                clusterSelect.innerHTML = '';
                clusters.forEach(c => {
                    const opt = document.createElement('option');
                    opt.value = c.name;
                    opt.textContent = `${c.name}${c.is_current ? ' (Active Context)' : ''}`;
                    if (c.is_current) opt.selected = true;
                    clusterSelect.appendChild(opt);
                });
                // Load namespaces for active cluster
                loadNamespaces(clusterSelect.value);
            }
        } catch (err) {
            console.error('Failed to load clusters:', err);
            loadNamespaces();
        }
    }

    if (clusterSelect) {
        clusterSelect.addEventListener('change', () => {
            loadNamespaces(clusterSelect.value);
        });
    }

    async function loadNamespaces(clusterName = null) {
        try {
            const url = clusterName ? `/api/v1/namespaces?cluster=${encodeURIComponent(clusterName)}` : '/api/v1/namespaces';
            const res = await fetch(url);
            if (res.ok) {
                const namespaces = await res.json();
                namespaceSelect.innerHTML = '';
                namespaces.forEach(ns => {
                    const opt = document.createElement('option');
                    opt.value = ns.name;
                    opt.textContent = `${ns.name} (${ns.pod_count} pods${ns.unhealthy_pod_count > 0 ? ' - ' + ns.unhealthy_pod_count + ' faulty' : ''})`;
                    if (ns.unhealthy_pod_count > 0) {
                        opt.style.color = '#ef4444';
                        opt.selected = true;
                    }
                    namespaceSelect.appendChild(opt);
                });
            }
        } catch (err) {
            console.error('Failed to load namespaces:', err);
        }
    }

    // Handle Investigate Button Click
    investigateBtn.addEventListener('click', async () => {
        const targetCluster = clusterSelect ? clusterSelect.value : null;
        const targetNamespace = namespaceSelect.value || 'default';
        const userPrompt = userPromptInput.value.trim();

        // UI State -> Loading
        idleState.classList.add('hidden');
        reportView.classList.add('hidden');
        loadingState.classList.remove('hidden');
        investigateBtn.disabled = true;

        thoughtStepsContainer.innerHTML = '';
        renderThoughtStep(1, 'Initializing Cluster Inspection', `Connecting to K8s API server for cluster '${targetCluster || 'default'}' / namespace '${targetNamespace}'...`);

        try {
            const response = await fetch('/api/v1/investigate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cluster: targetCluster,
                    namespace: targetNamespace,
                    prompt: userPrompt || null
                })
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || 'Investigation failed');
            }

            const data = await response.json();
            
            // Render thought steps
            if (data.thought_steps && data.thought_steps.length > 0) {
                thoughtStepsContainer.innerHTML = '';
                data.thought_steps.forEach(step => {
                    renderThoughtStep(step.step, step.action, step.details);
                });
            }

            // Brief delay to allow user to see reasoning pipeline before showing report
            setTimeout(() => {
                loadingState.classList.add('hidden');
                renderReport(data.report);
                reportView.classList.remove('hidden');
                investigateBtn.disabled = false;
            }, 800);

        } catch (error) {
            console.error(error);
            alert(`Investigation Error: ${error.message}`);
            loadingState.classList.add('hidden');
            idleState.classList.remove('hidden');
            investigateBtn.disabled = false;
        }
    });

    function renderThoughtStep(stepNum, action, details) {
        const div = document.createElement('div');
        div.className = 'thought-card';
        div.innerHTML = `
            <div class="thought-title"><i class="fa-solid fa-gear fa-spin"></i> Step ${stepNum}: ${escapeHtml(action)}</div>
            <div class="thought-desc">${escapeHtml(details)}</div>
        `;
        thoughtStepsContainer.appendChild(div);
    }

    const diffModal = document.getElementById('diff-modal');
    const diffContent = document.getElementById('diff-content');
    const closeDiffBtn = document.getElementById('close-diff-btn');

    if (closeDiffBtn) {
        closeDiffBtn.addEventListener('click', () => {
            diffModal.classList.add('hidden');
        });
    }

    // Close modal on background click
    if (diffModal) {
        diffModal.addEventListener('click', (e) => {
            if (e.target === diffModal) {
                diffModal.classList.add('hidden');
            }
        });
    }

    function renderReport(report) {
        // Severity Badge
        const sevBadge = document.getElementById('report-severity');
        const sevText = document.getElementById('severity-text');
        sevBadge.className = `severity-badge ${report.severity}`;
        sevText.textContent = report.severity;

        // Timestamp
        document.getElementById('report-time').textContent = new Date().toLocaleTimeString();

        // Summary
        document.getElementById('summary-body').textContent = report.summary;

        // Root Cause
        document.getElementById('root-cause-body').textContent = report.root_cause;

        // Affected Resources
        const tagsContainer = document.getElementById('affected-resources-tags');
        tagsContainer.innerHTML = '';
        if (report.affected_resources && report.affected_resources.length > 0) {
            report.affected_resources.forEach(res => {
                const span = document.createElement('span');
                span.className = 'tag';
                span.innerHTML = `<i class="fa-solid fa-cube"></i> ${escapeHtml(res)}`;
                tagsContainer.appendChild(span);
            });
        } else {
            tagsContainer.innerHTML = '<span class="text-muted" style="font-size:13px">No single resource isolated.</span>';
        }

        // Security & Configuration Audits
        const auditsCard = document.getElementById('security-audits-card');
        const auditsList = document.getElementById('security-audits-list');
        auditsList.innerHTML = '';

        if (report.security_audits && report.security_audits.length > 0) {
            auditsCard.classList.remove('hidden');
            report.security_audits.forEach(audit => {
                const item = document.createElement('div');
                item.className = `audit-violation-card severity-${audit.severity}`;
                item.innerHTML = `
                    <div class="audit-card-header">
                        <span class="audit-severity-pill sev-${audit.severity}">${audit.severity}</span>
                        <span class="audit-rule-badge">${escapeHtml(audit.rule)}</span>
                        <span class="audit-resource-label"><i class="fa-solid fa-cubes"></i> ${escapeHtml(audit.resource)}</span>
                    </div>
                    <p class="audit-card-description">${escapeHtml(audit.description)}</p>
                    <div class="audit-card-remediation"><strong>Recommendation:</strong> ${escapeHtml(audit.remediation)}</div>
                `;
                auditsList.appendChild(item);
            });
        } else {
            auditsCard.classList.add('hidden');
        }

        // Remediation Steps
        const remList = document.getElementById('remediation-steps-list');
        remList.innerHTML = '';
        if (report.remediation_steps && report.remediation_steps.length > 0) {
            report.remediation_steps.forEach(step => {
                const item = document.createElement('div');
                item.className = 'remediation-item';
                
                let cmdHtml = '';
                if (step.command) {
                    let diffBtnHtml = '';
                    if (step.patch_kind && step.patch_name && step.patch_body) {
                        diffBtnHtml = `
                            <button class="diff-preview-btn" onclick="previewYamlDiff('${escapeHtml(step.patch_kind)}', '${escapeHtml(step.patch_name)}', '${escapeHtml(step.patch_body.replace(/'/g, "\\'"))}')">
                                <i class="fa-solid fa-code-compare"></i> Preview YAML Diff
                            </button>
                        `;
                    }

                    cmdHtml = `
                        <div class="cmd-box">
                            <code>${escapeHtml(step.command)}</code>
                            <div style="display:flex; gap:8px;">
                                <button class="copy-btn" onclick="copyToClipboard('${escapeHtml(step.command.replace(/'/g, "\\'"))}')">
                                    <i class="fa-regular fa-copy"></i> Copy
                                </button>
                            </div>
                        </div>
                        ${diffBtnHtml}
                    `;
                }

                item.innerHTML = `
                    <div class="remediation-header">
                        <span class="remediation-step-num">${step.step_number}</span>
                        <span>${escapeHtml(step.title)}</span>
                    </div>
                    <p class="section-desc">${escapeHtml(step.explanation)}</p>
                    ${cmdHtml}
                `;
                remList.appendChild(item);
            });
        }

        // Prevention Tips
        const tipsList = document.getElementById('prevention-tips-list');
        tipsList.innerHTML = '';
        if (report.prevention_tips && report.prevention_tips.length > 0) {
            report.prevention_tips.forEach(tip => {
                const li = document.createElement('li');
                li.textContent = tip;
                tipsList.appendChild(li);
            });
        }
    }

    window.previewYamlDiff = async function(kind, name, patchBody) {
        const targetCluster = clusterSelect ? clusterSelect.value : null;
        const targetNamespace = namespaceSelect.value || 'default';

        diffModal.classList.remove('hidden');
        diffContent.innerHTML = '<div class="diff-loading"><i class="fa-solid fa-circle-notch fa-spin"></i> Generating Dry-run YAML configuration diff...</div>';

        try {
            const res = await fetch('/api/v1/dry-run/diff', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    cluster: targetCluster,
                    namespace: targetNamespace,
                    kind: kind,
                    name: name,
                    patch_body: patchBody
                })
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Dry-run failed');
            }

            const data = await res.json();
            
            // Format Diff Lines Color Coding
            const lines = data.diff_text.split('\n');
            const formattedLines = lines.map(line => {
                if (line.startsWith('+') && !line.startsWith('+++')) {
                    return `<span class="diff-add">${escapeHtml(line)}</span>`;
                } else if (line.startsWith('-') && !line.startsWith('---')) {
                    return `<span class="diff-remove">${escapeHtml(line)}</span>`;
                } else if (line.startsWith('@@')) {
                    return `<span class="diff-meta">${escapeHtml(line)}</span>`;
                } else if (line.startsWith('Current') || line.startsWith('Proposed')) {
                    return `<span class="diff-meta" style="font-weight:bold;">${escapeHtml(line)}</span>`;
                }
                return `<span>${escapeHtml(line)}</span>`;
            }).join('\n');

            diffContent.innerHTML = `<div class="diff-output">${formattedLines}</div>`;

        } catch (error) {
            diffContent.innerHTML = `<div class="diff-error"><i class="fa-solid fa-circle-exclamation"></i> ${escapeHtml(error.message)}</div>`;
        }
    };

    window.copyToClipboard = function(text) {
        navigator.clipboard.writeText(text).then(() => {
            alert('Command copied to clipboard!');
        }).catch(err => {
            console.error('Failed to copy command: ', err);
        });
    };

    function escapeHtml(str) {
        if (!str) return '';
        return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
    }
});
