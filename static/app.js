let scoreChart = null;
let pollInterval = null;
let currentArtifact = null;
let currentReviewPacket = null;
let currentReviewBlindMode = false;
let modelEvaluationRevealed = false;
let currentReviewQueue = [];
let currentCouncilHistory = [];
let currentCouncilSession = null;
let currentCouncilActions = [];
let currentRulePromotionReport = null;
let reviewTagCatalog = null;
let lastPacketAt = null;
const ADMIN_TOKEN_STORAGE_KEY = 'labAdminToken';
const POLL_INTERVAL_MS = 4000;
const REASON_TAG_TARGETS = ['winner', 'loser', 'both'];

// ── Cast activity animation ──
// When the lab is running, agents light up in sequence to show the flow:
// generators first, then judges, then the human seat stays dim until review.
let castActivityTimers = [];

function updateCastActivity(isRunning) {
    // Clear any pending staged activations
    castActivityTimers.forEach(t => clearTimeout(t));
    castActivityTimers = [];

    const cards = document.querySelectorAll('.cast-card[data-agent]');
    if (!isRunning) {
        cards.forEach(c => c.classList.remove('cast-active'));
        return;
    }

    // Staged activation: generators -> judges -> external
    // Human stays idle (they act later during review)
    const stages = [
        { agents: ['genesis', 'theron'], delay: 0 },
        { agents: ['muse'], delay: 800 },
        { agents: ['athena'], delay: 1400 },
        { agents: ['apollo'], delay: 2000 },
    ];

    stages.forEach(stage => {
        const timer = setTimeout(() => {
            cards.forEach(c => {
                if (stage.agents.includes(c.dataset.agent)) {
                    c.classList.add('cast-active');
                }
            });
        }, stage.delay);
        castActivityTimers.push(timer);
    });
}

// Light up human card when there are packets waiting for review
function updateHumanActivity(hasReviewWork) {
    const humanCard = document.querySelector('.cast-card[data-agent="human"]');
    if (!humanCard) return;
    if (hasReviewWork) {
        humanCard.classList.add('cast-active');
    } else {
        humanCard.classList.remove('cast-active');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('paired-generate-external')?.addEventListener('change', syncTheronSubmissionMode);
    document.getElementById('paired-external-artifact')?.addEventListener('input', syncTheronSubmissionMode);
    document.getElementById('packet-review-verdict')?.addEventListener('change', syncPacketReviewVerdictState);
    syncTheronSubmissionMode();
    initChart();
    refresh();
    startPolling();
    initDesignMotion();
});

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(refresh, POLL_INTERVAL_MS);
}

async function refresh() {
    try {
        const [stateRes, historyRes, timelineRes, analysisRes, providerRes, disagreementRes, councilRes, councilActionsRes, rulePromotionRes] = (
            await Promise.allSettled([
                fetch('/api/state').then(r => r.json()),
                fetch('/api/history').then(r => r.json()),
                fetch('/api/timeline').then(r => r.json()),
                fetch('/api/analysis').then(r => r.json()),
                fetch('/api/providers').then(r => r.json()),
                fetch('/api/review/disagreements').then(r => r.json()),
                fetch('/api/council/history').then(r => r.json()),
                fetch('/api/council/actions').then(r => r.json()),
                fetch('/api/rules/promotions').then(r => r.json()),
            ])
        ).map(result => result.status === 'fulfilled' ? result.value : null);

        if (stateRes) {
            updateStats(stateRes);
            updateDimensions(stateRes.best_scores);
            updateTrends(stateRes.trends);
            updateState(stateRes.state);
        }
        if (analysisRes) updateAnalysis(analysisRes);
        if (historyRes) updateHistory(historyRes);
        if (timelineRes) updateChart(timelineRes);
        if (providerRes) updateProviderStatus(providerRes);
        if (disagreementRes) renderReviewQueue(disagreementRes);
        if (councilRes) updateCouncilSurface(councilRes);
        if (councilActionsRes) updateCouncilGovernance(councilActionsRes);
        if (rulePromotionRes) renderRulePromotionProposals(rulePromotionRes);
    } catch (e) {
        console.error('Refresh failed:', e);
    }
}

function normalizeCouncilSession(entry) {
    if (!entry) return null;
    if (entry.payload) {
        return {
            council_id: entry.id,
            id: entry.id,
            created_at: entry.created_at,
            ...entry.payload,
        };
    }
    return entry;
}

function updateCouncilSurface(history) {
    currentCouncilHistory = Array.isArray(history) ? history : [];
    currentCouncilSession = currentCouncilHistory.length ? normalizeCouncilSession(currentCouncilHistory[0]) : null;

    const statusEl = document.getElementById('council-surface-status');
    const metaEl = document.getElementById('council-surface-meta');
    const confidenceEl = document.getElementById('council-surface-confidence');
    const strongestEl = document.getElementById('council-surface-strongest');
    const diagnosisEl = document.getElementById('council-surface-diagnosis');
    const educationEl = document.getElementById('council-surface-education');
    const nextEl = document.getElementById('council-surface-next');
    const promptCountEl = document.getElementById('council-surface-prompt-count');
    const educationCountEl = document.getElementById('council-surface-education-count');
    const contrastCountEl = document.getElementById('council-surface-contrast-count');

    if (!currentCouncilSession) {
        if (statusEl) statusEl.textContent = 'No council session has been filed yet.';
        if (metaEl) metaEl.textContent = 'Waiting for the first supervisory pass.';
        if (confidenceEl) confidenceEl.textContent = '--';
        if (strongestEl) strongestEl.textContent = 'No council session yet.';
        if (diagnosisEl) diagnosisEl.textContent = 'The council has not yet issued a diagnosis refinement.';
        if (educationEl) educationEl.textContent = 'The council has not yet proposed a panel-characterization probe.';
        if (nextEl) nextEl.textContent = 'Run a council session to synthesize the current workflow.';
        if (promptCountEl) promptCountEl.textContent = '0';
        if (educationCountEl) educationCountEl.textContent = '0';
        if (contrastCountEl) contrastCountEl.textContent = '0';
        return;
    }

    const createdAt = currentCouncilSession.created_at ? currentCouncilSession.created_at.replace('T', ' ').slice(0, 16) : 'timestamp unavailable';
    if (statusEl) {
        statusEl.textContent = `Latest council session #${currentCouncilSession.session_number || currentCouncilSession.id || '--'} is shaping the lab's current supervisory stance.`;
    }
    if (metaEl) {
        metaEl.textContent = `Session #${currentCouncilSession.session_number || currentCouncilSession.id || '--'} · ${createdAt} · ${currentCouncilSession.analysis_epoch || '--'}`;
    }
    if (confidenceEl) confidenceEl.textContent = currentCouncilSession.confidence_level || '--';
    if (strongestEl) strongestEl.textContent = currentCouncilSession.strongest_supported_finding || '--';
    if (diagnosisEl) diagnosisEl.textContent = currentCouncilSession.prompt_diagnosis_assessment || '--';
    if (educationEl) educationEl.textContent = currentCouncilSession.evaluator_education_assessment || '--';
    if (nextEl) nextEl.textContent = currentCouncilSession.one_experiment_to_run_next || '--';
    if (promptCountEl) promptCountEl.textContent = String((currentCouncilSession.prompt_diagnosis_recommendations || []).length);
    if (educationCountEl) educationCountEl.textContent = String((currentCouncilSession.evaluator_education_recommendations || []).length);
    if (contrastCountEl) contrastCountEl.textContent = String((currentCouncilSession.contrast_set_candidates || []).length);
}

function updateCouncilGovernance(payload) {
    currentCouncilActions = Array.isArray(payload?.rows) ? payload.rows : [];
    renderCouncilGovernanceBoard();
}

function renderCouncilGovernanceBoard() {
    const promptEl = document.getElementById('council-governance-prompt');
    const educationEl = document.getElementById('council-governance-education');
    const contrastEl = document.getElementById('council-governance-contrast');
    if (!promptEl || !educationEl || !contrastEl) return;

    const renderGroup = (actionType, status, emptyText) => {
        const rows = currentCouncilActions.filter(row => row.action_type === actionType && row.status === status);
        if (!rows.length) return `<div class="analysis-empty">${emptyText}</div>`;
        return rows.slice(0, 5).map(row => `
            <div class="council-governance-item">
                <div class="council-governance-item-title">${escapeHtml(row.title || 'Untitled')}</div>
                <div class="council-governance-item-meta">${escapeHtml(row.status || '--')}${row.updated_at ? ` · ${escapeHtml(row.updated_at.slice(0, 16).replace('T', ' '))}` : ''}</div>
            </div>
        `).join('');
    };

    promptEl.innerHTML = renderGroup('prompt_diagnosis_refinement', 'adopted', 'No adopted diagnosis probes yet.');
    educationEl.innerHTML = renderGroup('evaluator_education_target', 'active', 'No active panel-characterization probes yet.');
    contrastEl.innerHTML = renderGroup('contrast_set_candidate', 'queued', 'No queued contrast sets yet.');
}

function renderRulePromotionProposals(report) {
    currentRulePromotionReport = report || null;
    updateDesignCompilerLearning(report);
    const strip = document.getElementById('rule-proposal-strip');
    const countEl = document.getElementById('rule-proposal-count');
    const bodyEl = document.getElementById('rule-proposal-body');
    if (!strip || !countEl || !bodyEl) return;

    const proposals = Array.isArray(report?.proposals) ? report.proposals : [];
    const visible = proposals.filter(item => ['promote', 'watch', 'hold'].includes(item.recommendation));
    const promotions = visible.filter(item => item.recommendation === 'promote');
    const watches = visible.filter(item => item.recommendation === 'watch');
    const holds = visible.filter(item => item.recommendation === 'hold');
    countEl.textContent = `${promotions.length} promotion${promotions.length === 1 ? '' : 's'} · ${watches.length} watch · ${holds.length} hold`;
    strip.classList.toggle('has-proposals', visible.length > 0);
    const characterizationMap = renderRuleCharacterizationMap(proposals);

    if (!visible.length) {
        bodyEl.innerHTML = `
            <div class="rule-proposal-stack">
                ${characterizationMap}
                <span class="rule-proposal-empty">No rule has accumulated enough evidence yet.</span>
            </div>
            <span class="rule-proposal-thresholds">${formatRulePromotionThresholds(report?.thresholds)}</span>
        `;
        return;
    }

    const actionRows = visible.slice(0, 3).map(item => {
        const metrics = item.metrics || {};
        const transition = item.recommendation === 'promote'
            ? `${item.current_status} → ${item.proposed_status}`
            : item.recommendation;
        const humanWinRate = metrics.human_win_rate == null ? 'no decisive human rate' : `${Number(metrics.human_win_rate).toFixed(2)} human win rate`;
        const characterization = item.characterization || 'insufficient_data';
        const eligibleSlices = metrics.eligible_slices ?? metrics.total_slices ?? 0;
        const suppressedSlices = metrics.suppressed_dual_constraint_fail || 0;
        const suppressedNote = suppressedSlices ? ` · ${suppressedSlices} suppressed dual-fail` : '';
        const unreviewedNote = metrics.human_unreviewed ? ` · ${metrics.human_unreviewed} unreviewed` : '';
        return `
            <div class="rule-proposal-item ${item.recommendation} rule-characterization-${escapeHtml(characterization)}">
                <div class="rule-proposal-item-main">
                    <span class="rule-proposal-transition">${escapeHtml(transition)}</span>
                    <span class="rule-proposal-title">${escapeHtml(item.title || item.rule_key || 'Untitled rule')}</span>
                </div>
                <div class="rule-proposal-item-meta">
                    ${escapeHtml(`${metrics.support_packets || 0} packets · ${metrics.support_families || 0} prompt families · ${metrics.support_model_families || 0} model families · ${humanWinRate}`)}
                </div>
                <div class="rule-proposal-item-meta rule-proposal-characterization">
                    ${escapeHtml(`${formatRuleCharacterizationLabel(characterization)} · panel ${metrics.evaluator_helped || 0}/${eligibleSlices}${suppressedNote} · human ${metrics.human_decisive || 0} decisive${unreviewedNote}`)}
                </div>
            </div>
        `;
    }).join('');
    bodyEl.innerHTML = `<div class="rule-proposal-stack">${characterizationMap}<div class="rule-proposal-items">${actionRows}</div></div>`;
}

function formatRulePromotionThresholds(thresholds = {}) {
    const provisionalPackets = thresholds.provisional_packets ?? 5;
    const provisionalFamilies = thresholds.provisional_families ?? 2;
    const activePackets = thresholds.active_packets ?? 15;
    const activeFamilies = thresholds.active_families ?? 3;
    return `Provisional needs ${provisionalPackets} packets / ${provisionalFamilies} families; active needs ${activePackets} packets / ${activeFamilies} families plus human signal.`;
}

function formatRuleCharacterizationLabel(label) {
    return String(label || 'insufficient_data');
}

function renderRuleCharacterizationMap(proposals) {
    const labels = ['aligned', 'llm_specific', 'divergent', 'human_specific', 'insufficient_data'];
    const counts = Object.fromEntries(labels.map(label => [label, 0]));
    for (const proposal of proposals || []) {
        const label = proposal.characterization || 'insufficient_data';
        counts[label] = (counts[label] || 0) + 1;
    }
    const chips = labels.map(label => `
        <span class="rule-characterization-chip rule-characterization-${escapeHtml(label)}">
            ${counts[label] || 0} ${escapeHtml(formatRuleCharacterizationLabel(label))}
        </span>
    `).join('');
    return `<div class="rule-characterization-map"><span class="rule-characterization-map-title">Characterization map</span>${chips}</div>`;
}

function openLatestCouncilSession() {
    if (!currentCouncilSession) {
        alert('No council session has been recorded yet.');
        return;
    }
    showCouncilModal(currentCouncilSession);
}

function focusPairedRunner() {
    document.querySelector('.runner-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    document.getElementById('paired-prompt')?.focus();
}

function syncTheronSubmissionMode() {
    const generateEl = document.getElementById('paired-generate-external');
    const artifactEl = document.getElementById('paired-external-artifact');
    if (!generateEl || !artifactEl) return;
    if (generateEl.checked) {
        artifactEl.value = '';
        artifactEl.disabled = true;
        artifactEl.placeholder = 'Theron will be generated automatically for this packet.';
        return;
    }
    artifactEl.disabled = false;
    artifactEl.placeholder = 'Paste Theron’s artifact here for manual submission.';
}

function syncPacketReviewVerdictState() {
    const verdictEl = document.getElementById('packet-review-verdict');
    const choiceEl = document.getElementById('packet-review-choice');
    const winnerExtra = document.getElementById('packet-review-extra-tags-winner');
    const loserExtra = document.getElementById('packet-review-extra-tags-loser');
    const statusEl = document.getElementById('packet-review-status');
    if (!verdictEl || !choiceEl) return;
    const requiresPreferred = verdictEl.value === 'preferred';
    choiceEl.disabled = !requiresPreferred;
    if (!requiresPreferred) {
        choiceEl.value = '';
    }
    [winnerExtra, loserExtra].forEach(el => {
        if (!el) return;
        el.disabled = !requiresPreferred;
        if (!requiresPreferred) {
            el.value = '';
        }
    });
    document.querySelectorAll('.packet-review-reason-tag-scope').forEach(select => {
        if (requiresPreferred) {
            select.disabled = !document.querySelector(`.packet-review-reason-tag[data-tag="${select.dataset.tag}"]`)?.checked;
            return;
        }
        select.value = 'both';
        select.disabled = true;
    });
    if (statusEl && !requiresPreferred) {
        statusEl.style.display = 'none';
    }
}

function formatConditionLabel(condition) {
    if (condition === 'critique_on') return 'With critique';
    if (condition === 'critique_off') return 'Without critique';
    return condition || 'Unknown mode';
}

function formatTrackLabel(track) {
    const labels = {
        paired: 'Paired packet',
        paired_external: 'External pair member',
        custom: 'Single run',
        open_ended: 'Open prompt',
    };
    return labels[track] || (track ? track.replaceAll('_', ' ') : 'Unknown track');
}

function formatOutcomeLabel(status, promotionStatus) {
    if (status === 'promoted' && promotionStatus === 'shadow') return 'Advanced';
    if (status === 'kept') return 'Kept';
    if (status === 'discard') return 'Rejected';
    if (status === 'constraint_fail') return 'Missed brief';
    if (status === 'invalid') return 'Invalid';
    if (status === 'error') return 'Error';
    if (status === 'running') return 'In progress';
    return status || '--';
}

function updateProviderStatus(data) {
    // Theron status line
    const el = document.getElementById('paired-theron-status');
    if (el) {
        const theron = data?.theron;
        if (!theron) {
            el.textContent = 'Theron: unavailable';
            el.className = 'modal-inline-note theron-status-line error';
        } else if (!theron.enabled) {
            el.textContent = 'Theron: disabled';
            el.className = 'modal-inline-note theron-status-line warning';
        } else if (theron.reachable) {
            const mode = theron.gateway_status?.mode || theron.backend;
            el.textContent = `Theron: ready via ${mode}`;
            el.className = 'modal-inline-note theron-status-line ready';
        } else {
            el.textContent = `Theron: not reachable${theron.error ? ` · ${theron.error}` : ''}`;
            el.className = 'modal-inline-note theron-status-line error';
        }
    }

    // Populate cast model labels from the cast metadata
    const cast = data?.cast;
    if (cast) {
        const setModel = (id, info) => {
            const mel = document.getElementById(id);
            if (mel && info) mel.textContent = formatProviderModel(info) || '--';
        };
        setModel('cast-model-genesis', cast.genesis);
        setModel('cast-model-theron', cast.theron);
        setModel('cast-model-muse', cast.muse);
        setModel('cast-model-athena', cast.athena);
        setModel('cast-model-apollo', cast.apollo);
        // Design panel model display
        const dp = (id, info) => { const e = document.getElementById(id); if (e && info) e.textContent = formatProviderModel(info) || '--'; };
        dp('design-panel-muse', cast.muse);
        dp('design-panel-athena', cast.athena);
        dp('design-panel-apollo', cast.apollo);
    }
}

function formatProviderModel(info) {
    if (!info) return '';
    const backend = formatBackendLabel(info.backend);
    const model = formatModelLabel(info.model);
    if (backend && model) return `${backend} / ${model}`;
    return model || backend || '';
}

function formatBackendLabel(backend) {
    const key = String(backend || '').trim().toLowerCase();
    const labels = {
        openai: 'OpenAI',
        openclaw: 'OpenClaw',
        openclaw_gateway: 'OpenClaw',
        openclaw_local: 'OpenClaw',
        hermes: 'Hermes',
        hermes_cli: 'Hermes',
        theron: 'Theron',
        theron_gateway: 'Theron',
    };
    return labels[key] || backend || '';
}

function formatModelLabel(model) {
    const raw = String(model || '').trim();
    const normalized = raw.toLowerCase();
    if (!raw) return '';
    if (normalized.includes('claude-opus-4-7') || normalized.includes('opus-4-7')) return 'Opus 4.7';
    if (normalized.includes('claude-opus-4-6') || normalized.includes('opus-4-6')) return 'Opus 4.6';
    if (normalized === 'gpt-5.4' || normalized.endsWith('/gpt-5.4')) return 'GPT-5.4';
    if (normalized === 'gpt-5.4-mini' || normalized.endsWith('/gpt-5.4-mini')) return 'GPT-5.4 Mini';
    if (normalized === 'gpt-5.1' || normalized.endsWith('/gpt-5.1')) return 'GPT-5.1';
    return raw;
}

function renderReviewQueue(data) {
    const el = document.getElementById('review-queue-grid');
    if (!el) return;
    currentReviewQueue = data?.rows || [];
    const assemblingRows = data?.assembling_rows || [];
    const stalledRows = data?.stalled_rows || [];
    const graveyardRows = data?.graveyard_rows || [];
    updateHumanActivity(currentReviewQueue.length > 0);

    // Update header metrics and review summary
    const countEl = document.getElementById('stat-disagreements');
    if (countEl) countEl.textContent = currentReviewQueue.length;
    const summaryCount = document.getElementById('review-summary-count');
    if (summaryCount) summaryCount.textContent = currentReviewQueue.length;

    if (!currentReviewQueue.length && !assemblingRows.length && !stalledRows.length && !graveyardRows.length) {
        el.innerHTML = '<div class="analysis-empty">No human judgment queue yet.</div>';
        updateDesignQueue(data);
        return;
    }
    const readyHtml = currentReviewQueue.map((row, index) => {
        const roleCounts = {};
        (row.members || []).forEach(member => {
            const key = member.role_id || 'artifact';
            roleCounts[key] = (roleCounts[key] || 0) + 1;
        });
        const preferred = Array.isArray(row.judge_preferences)
            ? row.judge_preferences.map(summary => {
                const winner = summary.winner_experiment_id ? `#${summary.winner_experiment_id}` : 'split';
                return `${formatRoleLabel(summary.judge)}→${winner}`;
            }).join(' · ')
            : 'mixed';
        const queueHeadline = !row.has_review_ready_panel && (row.missing_judges || []).length
            ? `Primary judges ready · pending ${row.missing_judges.map(formatRoleLabel).join(', ')}`
            : row.has_noticeable_disagreement
                ? (row.has_complete_panel
                    ? 'Judges diverged'
                    : `Judges diverged · pending ${(row.missing_judges || []).map(formatRoleLabel).join(', ') || 'third judge'}`)
                : 'Judges broadly agree';
        const preview = row.members?.map(member => `#${member.experiment_id} ${formatRoleLabel(member.role_id)} · Muse ${fmtScore(member.muse_composite)} · Athena ${fmtScore(member.athena_composite)}${member.apollo_composite != null ? ` · Apollo ${fmtScore(member.apollo_composite)}` : ''}`).join('<br>') || '';
        const memberButtons = (row.members || []).map(member => `
            <button class="btn-refresh queue-member-button" onclick="openReviewQueueMember(${index}, ${member.experiment_id})">
                ${escapeHtml(formatQueueMemberLabel(member, roleCounts))}
            </button>
        `).join('');
        return `
            <div class="review-queue-card">
                <div class="analysis-head">
                    <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                    <span class="analysis-kicker">${escapeHtml((row.family || 'unclassified').replaceAll('_', ' '))}</span>
                    <span class="analysis-kicker">${escapeHtml(formatConditionLabel(row.condition))}</span>
                </div>
                <div class="review-queue-prompt">${escapeHtml(truncateMiddle(row.prompt || row.members?.[0]?.artifact_preview || 'Packet ready for review.', 220))}</div>
                <div class="analysis-subtle">${queueHeadline}: ${escapeHtml(preferred)}</div>
                <div class="analysis-metrics stacked">${preview}</div>
                <div class="queue-member-actions">
                    ${memberButtons}
                </div>
                <div class="queue-actions">
                    <button class="btn-refresh primary" onclick="openReviewQueueItem(${index})">Open For Judgment</button>
                    <button class="btn-refresh" onclick="loadReviewPrompt(${index})">Use Prompt In Packet</button>
                </div>
            </div>
        `;
    }).join('');
    const assemblingHtml = assemblingRows.length ? `
        <div class="review-queue-assembling">
            <div class="analysis-summary-headline">${escapeHtml(data?.assembling_headline || 'Paired packets still assembling.')}</div>
            ${assemblingRows.map(row => {
                const stage = row.assembly_stage === 'awaiting_pair_member'
                    ? 'Awaiting paired member'
                    : 'Awaiting evaluator panel';
                const members = (row.members || []).map(member => `#${member.experiment_id} ${formatRoleLabel(member.role_id)}`).join(' · ');
                return `
                    <div class="analysis-item">
                        <div class="analysis-head">
                            <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                            <span class="analysis-kicker">${escapeHtml((row.family || 'unclassified').replaceAll('_', ' '))}</span>
                            <span class="analysis-kicker">${escapeHtml(stage)}</span>
                        </div>
                        <div class="analysis-sub">${escapeHtml(truncateMiddle(row.prompt || 'Packet assembling.', 180))}</div>
                        <div class="analysis-metrics">
                            <span>${escapeHtml(members || 'No members yet')}</span>
                        </div>
                    </div>
                `;
            }).join('')}
        </div>
    ` : '';
    const stalledHtml = stalledRows.length ? `
        <div class="review-queue-assembling review-queue-stalled">
            <div class="analysis-summary-headline">${escapeHtml(data?.stalled_headline || 'Paired packets are stalled and need repair.')}</div>
            ${stalledRows.map(row => {
                const stage = row.assembly_stage === 'awaiting_pair_member'
                    ? 'Missing paired member'
                    : 'Missing evaluator outputs';
                const missing = (row.missing_judges || []).length ? ` · missing ${row.missing_judges.map(formatRoleLabel).join(', ')}` : '';
                return `
                    <div class="analysis-item">
                        <div class="analysis-head">
                            <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                            <span class="analysis-kicker">${escapeHtml((row.family || 'unclassified').replaceAll('_', ' '))}</span>
                            <span class="analysis-kicker">${escapeHtml(stage)}</span>
                        </div>
                        <div class="analysis-sub">${escapeHtml(truncateMiddle(row.prompt || 'Packet stalled.', 180))}</div>
                        <div class="analysis-metrics">
                            <span>${escapeHtml(`last activity ${row.latest_activity_at || 'unknown'}`)}</span>
                            <span>${escapeHtml(`${row.members?.length || 0} member(s)${missing}`)}</span>
                        </div>
                        <div class="queue-actions">
                            <button class="btn-refresh" onclick="discardStalledPacket('${row.packet_id}')">Discard Failed Packet</button>
                        </div>
                    </div>
                `;
            }).join('')}
        </div>
    ` : '';
    const graveyardHtml = graveyardRows.length ? `
        <div class="review-queue-assembling review-queue-graveyard">
            <div class="analysis-summary-headline">${escapeHtml(data?.graveyard_headline || 'Packet graveyard')}</div>
            ${graveyardRows.map(row => `
                <div class="analysis-item">
                    <div class="analysis-head">
                        <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                        <span class="analysis-kicker">${escapeHtml((row.prompt_family || 'unclassified').replaceAll('_', ' '))}</span>
                        <span class="analysis-kicker">${escapeHtml((row.resolution || 'resolved').replaceAll('_', ' '))}</span>
                    </div>
                    <div class="analysis-sub">${escapeHtml(truncateMiddle(row.prompt || row.packet_id || 'Resolved packet', 180))}</div>
                    <div class="analysis-metrics">
                        <span>${escapeHtml(`resolved ${row.updated_at || '--'}`)}</span>
                        <span>${escapeHtml(truncateMiddle(row.rationale || '', 100))}</span>
                    </div>
                </div>
            `).join('')}
        </div>
    ` : '';
    el.innerHTML = `${readyHtml}${assemblingHtml}${stalledHtml}${graveyardHtml}`;
    updateDesignQueue(data);
}

function formatQueueMemberLabel(member, roleCounts = {}) {
    const roleLabel = formatRoleLabel(member.role_id || 'artifact');
    const count = roleCounts[member.role_id || 'artifact'] || 0;
    const experimentId = getMemberExperimentId(member);
    if (count > 1) {
        return `Open ${roleLabel} #${experimentId}`;
    }
    return `Open ${roleLabel}`;
}

function getMemberExperimentId(member) {
    return member?.experiment_id ?? member?.id;
}

function humanizeReasonTag(tag) {
    if (!tag) return 'Unnamed tag';
    return tag
        .split('_')
        .filter(Boolean)
        .map(part => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ');
}

function getReasonTagGroups() {
    return [
        { key: 'quality_signals', label: 'Quality Signals' },
        { key: 'anti_patterns', label: 'Anti-Patterns' },
        { key: 'evaluator_failure_modes', label: 'Evaluator Failure Modes' },
    ];
}

function flattenReasonTagCatalog(catalog) {
    return getReasonTagGroups().flatMap(group => (catalog?.[group.key] || []).map(entry => entry.tag)).filter(Boolean);
}

function emptyReasonTagAttribution() {
    return { winner: [], loser: [], both: [], unattributed: [] };
}

function describeHumanReview(review) {
    if (!review) return '';
    const metadata = review.metadata || {};
    const verdict = metadata.review_verdict || (review.preferred_experiment_id ? 'preferred' : 'abstain');
    const confidence = metadata.review_confidence ? metadata.review_confidence.replaceAll('_', ' ') : 'unspecified confidence';
    const distinctiveness = metadata.pair_distinctiveness ? metadata.pair_distinctiveness.replaceAll('_', ' ') : null;
    if (verdict === 'preferred' && review.preferred_experiment_id != null) {
        return `Saved judgment: preferred #${review.preferred_experiment_id} with ${confidence}${distinctiveness ? ` · ${distinctiveness}` : ''}.`;
    }
    return `Saved judgment: ${verdict.replaceAll('_', ' ')} with ${confidence}${distinctiveness ? ` · ${distinctiveness}` : ''}.`;
}

function normalizeReasonTagAttribution(metadata) {
    const attribution = metadata?.reason_tag_attribution || {};
    const normalized = emptyReasonTagAttribution();
    Object.keys(normalized).forEach(key => {
        const values = Array.isArray(attribution[key]) ? attribution[key] : [];
        normalized[key] = Array.from(new Set(values.map(tag => String(tag || '').trim()).filter(Boolean)));
    });
    const flatTags = Array.isArray(metadata?.reason_tags) ? metadata.reason_tags : [];
    if (flatTags.length && !REASON_TAG_TARGETS.some(key => normalized[key].length) && !normalized.unattributed.length) {
        normalized.unattributed = Array.from(new Set(flatTags.map(tag => String(tag || '').trim()).filter(Boolean)));
    }
    return normalized;
}

function normalizeReasonTagEvidence(metadata) {
    const evidence = Array.isArray(metadata?.reason_tag_evidence) ? metadata.reason_tag_evidence : [];
    const byTag = new Map();
    evidence.forEach(item => {
        const tag = String(item?.tag || '').trim();
        const excerpt = String(item?.excerpt || '').trim();
        const target = String(item?.target || '').trim() || 'unattributed';
        if (!tag || !excerpt) return;
        byTag.set(tag, { tag, target, excerpt });
    });
    return byTag;
}

async function ensureReviewTagCatalog() {
    if (reviewTagCatalog) return reviewTagCatalog;
    const res = await fetch('/api/review/reason-tags');
    reviewTagCatalog = await res.json();
    return reviewTagCatalog;
}

function renderReviewReasonTagCatalog(catalog, attribution = emptyReasonTagAttribution(), evidenceByTag = new Map()) {
    const host = document.getElementById('packet-review-reason-tags');
    if (!host) return;
    const selectedScope = new Map();
    REASON_TAG_TARGETS.forEach(scope => {
        (attribution?.[scope] || []).forEach(tag => selectedScope.set(tag, scope));
    });
    const html = getReasonTagGroups().map(group => {
        const entries = catalog?.[group.key] || [];
        if (!entries.length) {
            return `
                <div class="review-tag-group">
                    <div class="review-tag-group-title">${group.label}</div>
                    <div class="review-tag-empty">No ${group.label.toLowerCase()} available yet.</div>
                </div>
            `;
        }
        return `
            <div class="review-tag-group">
                <div class="review-tag-group-title">${group.label}</div>
                <div class="review-tag-list">
                    ${entries.map(entry => `
                        <label class="review-tag-option">
                            <input
                                type="checkbox"
                                class="packet-review-reason-tag"
                                value="${escapeHtml(entry.tag)}"
                                ${selectedScope.has(entry.tag) ? 'checked' : ''}
                                onchange="toggleReasonTagScope(this)"
                            >
                            <span class="review-tag-label">${escapeHtml(entry.name || humanizeReasonTag(entry.tag))}</span>
                            <span class="review-tag-scope">
                                <select class="packet-review-reason-tag-scope" data-tag="${escapeHtml(entry.tag)}" ${selectedScope.has(entry.tag) ? '' : 'disabled'}>
                                    <option value="winner" ${selectedScope.get(entry.tag) === 'winner' ? 'selected' : ''}>Winner</option>
                                    <option value="loser" ${selectedScope.get(entry.tag) === 'loser' ? 'selected' : ''}>Loser</option>
                                    <option value="both" ${selectedScope.get(entry.tag) === 'both' ? 'selected' : ''}>Both</option>
                                </select>
                            </span>
                            ${entry.description ? `<span class="review-tag-description">${escapeHtml(entry.description)}</span>` : ''}
                            <span class="review-tag-evidence">
                                <input
                                    type="text"
                                    class="packet-review-reason-tag-evidence"
                                    data-tag="${escapeHtml(entry.tag)}"
                                    placeholder="optional quote or excerpt from the artifact"
                                    value="${escapeHtml(evidenceByTag.get(entry.tag)?.excerpt || '')}"
                                    ${selectedScope.has(entry.tag) ? '' : 'disabled'}
                                >
                            </span>
                        </label>
                    `).join('')}
                </div>
            </div>
        `;
    }).join('');
    host.innerHTML = html;
}

function toggleReasonTagScope(input) {
    const tag = input?.value;
    if (!tag) return;
    const select = document.querySelector(`.packet-review-reason-tag-scope[data-tag="${tag}"]`);
    const evidence = document.querySelector(`.packet-review-reason-tag-evidence[data-tag="${tag}"]`);
    if (!select) return;
    const verdict = document.getElementById('packet-review-verdict')?.value || 'preferred';
    if (verdict !== 'preferred') {
        select.value = 'both';
    }
    select.disabled = !input.checked || verdict !== 'preferred';
    if (evidence) evidence.disabled = !input.checked;
}

function parseExtraReviewTags(value) {
    return value
        .split(',')
        .map(tag => tag.trim().toLowerCase().replace(/\s+/g, '_'))
        .filter(Boolean);
}

function collectSelectedReasonTagAttribution() {
    const attribution = emptyReasonTagAttribution();
    Array.from(document.querySelectorAll('.packet-review-reason-tag:checked')).forEach(input => {
        const tag = input.value.trim();
        const scope = document.querySelector(`.packet-review-reason-tag-scope[data-tag="${tag}"]`)?.value || 'winner';
        if (attribution[scope] && tag) attribution[scope].push(tag);
    });
    attribution.winner.push(...parseExtraReviewTags(document.getElementById('packet-review-extra-tags-winner')?.value || ''));
    attribution.loser.push(...parseExtraReviewTags(document.getElementById('packet-review-extra-tags-loser')?.value || ''));
    attribution.both.push(...parseExtraReviewTags(document.getElementById('packet-review-extra-tags-both')?.value || ''));
    if (Array.isArray(currentReviewPacket?.human_review?.metadata?.reason_tag_attribution?.unattributed)) {
        attribution.unattributed.push(...currentReviewPacket.human_review.metadata.reason_tag_attribution.unattributed);
    }
    Object.keys(attribution).forEach(key => {
        attribution[key] = Array.from(new Set(attribution[key]));
    });
    return attribution;
}

function collectSelectedReasonTagEvidence() {
    const evidence = [];
    const verdict = document.getElementById('packet-review-verdict')?.value || 'preferred';
    Array.from(document.querySelectorAll('.packet-review-reason-tag:checked')).forEach(input => {
        const tag = input.value.trim();
        const target = verdict === 'preferred'
            ? (document.querySelector(`.packet-review-reason-tag-scope[data-tag="${tag}"]`)?.value || 'winner')
            : 'both';
        const excerpt = (document.querySelector(`.packet-review-reason-tag-evidence[data-tag="${tag}"]`)?.value || '').trim();
        if (tag && excerpt) {
            evidence.push({ tag, target, excerpt });
        }
    });
    return evidence;
}

function openReviewQueueItem(index) {
    const item = currentReviewQueue[index];
    if (!item?.packet_id) return;
    showReviewPacket(item.packet_id);
}

function openBlindRereviewCandidate(packetId) {
    if (!packetId) return;
    showReviewPacket(packetId, { blindRereview: true });
}

function openReviewQueueMember(index, experimentId) {
    const item = currentReviewQueue[index];
    if (!item || !item.members || !item.members.length || !experimentId) return;
    const member = item.members.find(candidate => getMemberExperimentId(candidate) === experimentId);
    const memberId = getMemberExperimentId(member);
    if (memberId) {
        showArtifact(memberId);
    }
}

async function discardStalledPacket(packetId) {
    if (!packetId) return;
    const message = 'Discard this stalled packet as a failed comparison and remove it from the live queue?';
    if (typeof window !== 'undefined' && window.confirm && !window.confirm(message)) {
        return;
    }
    try {
        const headers = buildAdminHeaders();
        if (!headers) return;
        const res = await fetch(`/api/review/disagreements/${packetId}/resolution`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                resolution: 'discarded_failure',
                rationale: 'Discarded from the live queue after stalling without producing a complete comparison.',
                reviewer: 'human_operator',
                metadata: {
                    source: 'stalled_queue_ui',
                },
            }),
        });
        const data = await res.json();
        if (!res.ok) {
            console.error('Failed to discard stalled packet:', data.error || data);
            return;
        }
        refresh();
    } catch (e) {
        console.error('Failed to discard stalled packet:', e);
    }
}

async function showReviewPacket(packetId, options = {}) {
    try {
        const catalog = await ensureReviewTagCatalog();
        const data = await fetch(`/api/review/disagreements/${packetId}`).then(r => r.json());
        if (data.error) return;
        currentReviewPacket = data;
        currentReviewBlindMode = !!options.blindRereview;
        const tagAttribution = normalizeReasonTagAttribution(data.human_review?.metadata);
        const evidenceByTag = normalizeReasonTagEvidence(data.human_review?.metadata);
        const seededTags = new Set(flattenReasonTagCatalog(catalog));
        const extraWinnerTags = (tagAttribution.winner || []).filter(tag => !seededTags.has(tag));
        const extraLoserTags = (tagAttribution.loser || []).filter(tag => !seededTags.has(tag));
        const extraSharedTags = (tagAttribution.both || []).filter(tag => !seededTags.has(tag));
        const legacyHost = document.getElementById('packet-review-legacy-tags');
        const blindHost = document.getElementById('packet-review-blind-note');
        const savedNoteEl = document.getElementById('packet-review-last-saved');
        const saveButtonEl = document.getElementById('packet-review-save-button');
        const legacyTags = tagAttribution.unattributed || [];
        const reviewMeta = data.human_review?.metadata || {};

        document.getElementById('packet-review-title').textContent = currentReviewBlindMode
            ? `Packet ${data.packet_id} — Blind Re-review`
            : `Packet ${data.packet_id} — Human Judgment`;
        document.getElementById('packet-review-meta').textContent = `${data.lane || 'unknown'} / ${(data.family || 'unclassified').replaceAll('_', ' ')} / ${formatConditionLabel(data.condition)}`;
        document.getElementById('packet-review-prompt').textContent = data.prompt || '(no prompt)';
        document.getElementById('packet-review-rationale').value = currentReviewBlindMode ? '' : (data.human_review?.rationale || '');
        document.getElementById('packet-review-extra-tags-winner').value = currentReviewBlindMode ? '' : extraWinnerTags.join(', ');
        document.getElementById('packet-review-extra-tags-loser').value = currentReviewBlindMode ? '' : extraLoserTags.join(', ');
        document.getElementById('packet-review-extra-tags-both').value = currentReviewBlindMode ? '' : extraSharedTags.join(', ');
        document.getElementById('packet-review-confidence').value = currentReviewBlindMode ? '' : (reviewMeta.review_confidence || '');
        document.getElementById('packet-review-distinctiveness').value = currentReviewBlindMode ? '' : (reviewMeta.pair_distinctiveness || '');
        document.getElementById('packet-review-verdict').value = currentReviewBlindMode
            ? 'preferred'
            : (reviewMeta.review_verdict || (data.human_review?.preferred_experiment_id ? 'preferred' : 'abstain'));
        document.getElementById('packet-review-revisit-later').checked = !currentReviewBlindMode && reviewMeta.review_decision_state === 'revisit_later';
        document.getElementById('packet-review-status').style.display = 'none';
        if (saveButtonEl) {
            saveButtonEl.disabled = false;
            saveButtonEl.textContent = 'Save Human Judgment';
        }
        if (savedNoteEl) {
            if (!currentReviewBlindMode && data.human_review?.updated_at) {
                savedNoteEl.textContent = `${describeHumanReview(data.human_review)} Last saved ${data.human_review.updated_at}.`;
                savedNoteEl.classList.remove('hidden');
            } else {
                savedNoteEl.textContent = '';
                savedNoteEl.classList.add('hidden');
            }
        }
        renderReviewReasonTagCatalog(
            catalog,
            currentReviewBlindMode ? emptyReasonTagAttribution() : tagAttribution,
            currentReviewBlindMode ? new Map() : evidenceByTag,
        );
        if (legacyHost) {
            if (!currentReviewBlindMode && legacyTags.length) {
                legacyHost.textContent = `Legacy unattributed tags preserved from older reviews: ${legacyTags.join(', ')}. Re-save with new attribution if you want to classify them.`;
                legacyHost.classList.remove('hidden');
            } else {
                legacyHost.textContent = '';
                legacyHost.classList.add('hidden');
            }
        }
        if (blindHost) {
            if (currentReviewBlindMode) {
                const updatedAt = data.human_review?.updated_at || 'an earlier session';
                blindHost.textContent = `Blind re-review mode is active. Your previous judgment from ${updatedAt} is hidden so we can measure your stability, not your memory.`;
                blindHost.classList.remove('hidden');
            } else {
                blindHost.textContent = '';
                blindHost.classList.add('hidden');
            }
        }

        const judgeSummary = Array.isArray(data.judge_preferences)
            ? data.judge_preferences.map(summary => {
                const winner = summary.winner_experiment_id ? `#${summary.winner_experiment_id}` : 'split';
                const margin = summary.margin != null ? ` (Δ ${summary.margin.toFixed(2)})` : '';
                return `${formatRoleLabel(summary.judge)}→${winner}${margin}`;
            }).join(' · ')
            : 'No judge preferences recorded.';
        const panelSuffix = !data.has_complete_panel && (data.missing_judges || []).length
            ? ` · pending ${data.missing_judges.map(formatRoleLabel).join(', ')}`
            : '';
        document.getElementById('packet-review-judges').textContent = currentReviewBlindMode
            ? 'Hidden during blind re-review.'
            : `${judgeSummary}${panelSuffix}`;

        const roleCounts = {};
        (data.members || []).forEach(member => {
            const key = member.role_id || 'artifact';
            roleCounts[key] = (roleCounts[key] || 0) + 1;
        });

        const members = (data.members || []).map((member, idx) => ({
            ...member,
            reviewLabel: `Artifact ${String.fromCharCode(65 + idx)}`,
            experimentRef: getMemberExperimentId(member),
        }));

        const choiceEl = document.getElementById('packet-review-choice');
        choiceEl.innerHTML = `
            <option value="">Select</option>
            ${members.map(member => `
                <option value="${member.experimentRef}" ${(!currentReviewBlindMode && data.human_review?.preferred_experiment_id === member.experimentRef) ? 'selected' : ''}>
                    ${member.reviewLabel} · ${escapeHtml(formatQueueMemberLabel(member, roleCounts))}
                </option>
            `).join('')}
        `;
        syncPacketReviewVerdictState();

        document.getElementById('packet-review-grid').innerHTML = members.map(member => `
            <div class="packet-review-card">
                <div class="packet-review-card-header">
                    <div>
                        <div class="packet-review-card-label">${escapeHtml(member.reviewLabel)}</div>
                        <div class="packet-review-card-title">${escapeHtml(formatQueueMemberLabel(member, roleCounts))}</div>
                    </div>
                    <div class="packet-review-card-meta">
                        #${member.experimentRef}<br>
                        ${escapeHtml(formatOutcomeLabel(member.status, member.promotion_status))}
                    </div>
                </div>
                <div class="packet-review-card-scores">
                    <span>Muse ${fmtScore(member.scores?.muse ?? member.muse_composite)}</span>
                    <span>Athena ${fmtScore(member.scores?.athena ?? member.athena_composite)}</span>
                    <span>Apollo ${fmtScore(member.scores?.apollo ?? member.apollo_composite)}</span>
                </div>
                <div class="packet-review-artifact">${escapeHtml(member.artifact || '(no artifact)')}</div>
                <div class="packet-review-actions">
                    <button class="btn-refresh primary" onclick="showArtifact(${member.experimentRef})">Open Individual Artifact</button>
                </div>
            </div>
        `).join('');

        document.getElementById('packet-review-overlay').classList.add('active');
    } catch (e) {
        console.error('Failed to load review packet:', e);
    }
}

function closePacketReviewModal(event) {
    if (event.target === document.getElementById('packet-review-overlay')) {
        document.getElementById('packet-review-overlay').classList.remove('active');
    }
}

async function savePacketReviewDecision() {
    if (!currentReviewPacket?.packet_id) return;
    let preferredExperimentId = Number(document.getElementById('packet-review-choice').value || '');
    const rationale = document.getElementById('packet-review-rationale').value.trim();
    const reviewConfidence = (document.getElementById('packet-review-confidence').value || '').trim();
    const pairDistinctiveness = (document.getElementById('packet-review-distinctiveness').value || '').trim();
    const revisitLater = !!document.getElementById('packet-review-revisit-later').checked;
    const reviewVerdict = (document.getElementById('packet-review-verdict').value || 'preferred').trim();
    let reasonTagAttribution = collectSelectedReasonTagAttribution();
    const reasonTagEvidence = collectSelectedReasonTagEvidence();
    if (reviewVerdict !== 'preferred') {
        reasonTagAttribution = {
            winner: [],
            loser: [],
            both: Array.from(new Set([
                ...(reasonTagAttribution.winner || []),
                ...(reasonTagAttribution.loser || []),
                ...(reasonTagAttribution.both || []),
            ])),
            unattributed: reasonTagAttribution.unattributed || [],
        };
        preferredExperimentId = null;
    }
    const reasonTags = Array.from(new Set([
        ...(reasonTagAttribution.winner || []),
        ...(reasonTagAttribution.loser || []),
        ...(reasonTagAttribution.both || []),
        ...(reasonTagAttribution.unattributed || []),
    ]));
    const statusEl = document.getElementById('packet-review-status');
    const savedNoteEl = document.getElementById('packet-review-last-saved');
    const saveButtonEl = document.getElementById('packet-review-save-button');

    if (reviewVerdict === 'preferred' && !preferredExperimentId) {
        statusEl.textContent = 'Choose a preferred artifact for a preferred-artifact verdict.';
        statusEl.className = 'modal-review-status error';
        statusEl.style.display = 'block';
        return;
    }
    if (!rationale) {
        statusEl.textContent = 'Add a short explanation of why you preferred it.';
        statusEl.className = 'modal-review-status error';
        statusEl.style.display = 'block';
        return;
    }
    if (!reviewConfidence) {
        statusEl.textContent = 'Set your confidence so future re-reviews mean something.';
        statusEl.className = 'modal-review-status error';
        statusEl.style.display = 'block';
        return;
    }
    if (!pairDistinctiveness) {
        statusEl.textContent = 'Mark whether the pair felt clearly distinct, somewhat distinct, or like the same writer.';
        statusEl.className = 'modal-review-status error';
        statusEl.style.display = 'block';
        return;
    }

    try {
        const headers = buildAdminHeaders();
        if (!headers) {
            statusEl.textContent = 'Admin token required to save the judgment.';
            statusEl.className = 'modal-review-status error';
            statusEl.style.display = 'block';
            return;
        }
        if (saveButtonEl) {
            saveButtonEl.disabled = true;
            saveButtonEl.textContent = 'Saving...';
        }
        const res = await fetch(`/api/review/disagreements/${currentReviewPacket.packet_id}/decision`, {
            method: 'POST',
            headers,
            body: JSON.stringify({
                preferred_experiment_id: preferredExperimentId,
                rationale,
                reviewer: 'human_operator',
                review_channel: 'ui',
                metadata: {
                    review_verdict: reviewVerdict,
                    review_confidence: reviewConfidence,
                    pair_distinctiveness: pairDistinctiveness,
                    review_decision_state: revisitLater ? 'revisit_later' : 'final',
                    review_mode: currentReviewBlindMode ? 'blind_rereview' : 'standard',
                    reason_tags: reasonTags,
                    reason_tag_attribution: reasonTagAttribution,
                    reason_tag_evidence: reasonTagEvidence,
                },
            }),
        });
        const data = await res.json();
        if (!res.ok) {
            statusEl.textContent = data.error || 'Failed to save human judgment.';
            statusEl.className = 'modal-review-status error';
            statusEl.style.display = 'block';
            return;
        }
        currentReviewPacket.human_review = data.review;
        statusEl.textContent = `Human judgment saved at ${data.review?.updated_at || 'just now'}.`;
        statusEl.className = 'modal-review-status saved';
        statusEl.style.display = 'block';
        if (savedNoteEl) {
            savedNoteEl.textContent = `${describeHumanReview(data.review)} Last saved ${data.review?.updated_at || 'just now'}.`;
            savedNoteEl.classList.remove('hidden');
        }
        if (saveButtonEl) {
            saveButtonEl.textContent = 'Saved';
        }
        refresh();
    } catch (e) {
        statusEl.textContent = 'Failed to save human judgment.';
        statusEl.className = 'modal-review-status error';
        statusEl.style.display = 'block';
        console.error('Failed to save packet review decision:', e);
    } finally {
        if (saveButtonEl) {
            saveButtonEl.disabled = false;
            if (!statusEl.classList.contains('saved')) {
                saveButtonEl.textContent = 'Save Human Judgment';
            }
        }
    }
}

function loadReviewPrompt(index) {
    const item = currentReviewQueue[index];
    if (!item) return;
    document.getElementById('paired-lane').value = item.lane || 'creative';
    document.getElementById('paired-condition').value = item.condition || 'critique_off';
    document.getElementById('paired-family').value = item.family || 'paired_operator';
    document.getElementById('paired-prompt').value = item.prompt || '';
    document.getElementById('paired-constraints').value = (item.constraints || []).join('\n');
    focusPairedRunner();
}

function updateStats(data) {
    const s = data.state;
    if (!s) return;

    document.getElementById('stat-experiments').textContent = s.total_experiments || 0;
    document.getElementById('stat-kept').textContent = s.kept || 0;
    document.getElementById('stat-discarded').textContent = s.discarded || 0;
    document.getElementById('stat-promoted').textContent = s.promoted || 0;

    const best = s.best_score || 0;
    document.getElementById('stat-best').textContent = best.toFixed(2);

    const trends = data.trends;
    if (trends && trends.early_mean && trends.recent_mean) {
        const imp = ((trends.recent_mean - trends.early_mean) / trends.early_mean * 100);
        const el = document.getElementById('stat-improvement');
        el.textContent = (imp >= 0 ? '+' : '') + imp.toFixed(1) + '%';
        el.className = 'stat-value ' + (imp >= 0 ? 'green' : 'red');
        document.getElementById('stat-baseline').textContent = 'early \u03BC: ' + trends.early_mean.toFixed(2);
    } else {
        document.getElementById('stat-improvement').textContent = '--';
        document.getElementById('stat-baseline').textContent = '--';
    }

    const cost = s.total_cost || 0;
    const cap = s.cost_cap || 50;
    const hasKnownCost = cost > 0;
    document.getElementById('stat-cost').textContent = hasKnownCost ? ('$' + cost.toFixed(2)) : '$0.00';
    document.getElementById('stat-cap').textContent = cap.toFixed(0);

    const pct = Math.min(100, (cost / cap) * 100);
    const bar = document.getElementById('cost-bar');
    bar.style.width = pct + '%';
    bar.style.background = pct > 80 ? 'var(--red)' : pct > 50 ? 'var(--yellow)' : 'var(--green)';
    bar.title = hasKnownCost ? `Estimated spend: $${cost.toFixed(2)} of $${cap.toFixed(0)}` : 'Estimated spend unavailable until priced model usage is recorded';

    const badge = document.getElementById('runner-badge');
    badge.textContent = s.running ? 'RUNNING' : 'IDLE';
    badge.className = s.running ? 'badge' : 'badge pending';

    // Animate cast strip: light up agents during a run
    updateCastActivity(s.running);

    // Design instrument: runner state + experiments counter + last-activity timestamp
    const _dse = document.getElementById('design-stat-experiments');
    if (_dse) _dse.textContent = s.total_experiments || 0;
    updateDesignRunnerState(!!s.running);
    if (s.updated_at) {
        const _d = new Date(s.updated_at);
        if (!isNaN(_d.getTime())) lastPacketAt = _d;
    }
}

function updateTrends(trends) {
    if (!trends) return;
    const el = document.getElementById('trend-details');
    if (!el) return;

    let html = '';
    if (trends.mean_composite != null) {
        html += `<span class="state-key">Mean: </span><span class="state-val">${trends.mean_composite.toFixed(2)}</span> `;
    }
    if (trends.median_composite != null) {
        html += `<span class="state-key">Median: </span><span class="state-val">${trends.median_composite.toFixed(2)}</span>`;
    }
    if (trends.muse_critic_divergence != null) {
        html += `<br><span class="state-key">Muse-Athena \u0394: </span><span class="state-val">${trends.muse_critic_divergence.toFixed(2)}</span>`;
        html += ` <span class="state-key">(${trends.muse_critic_pairs} pairs)</span>`;
    }
    if (trends.lanes && trends.lanes.length > 0) {
        html += '<br>';
        trends.lanes.forEach(l => {
            html += `<span class="lane-badge ${l.lane}">${l.lane}</span> `;
            html += `<span class="state-val">${l.lane_mean.toFixed(2)}</span> <span class="state-key">(n=${l.lane_count})</span> `;
        });
    }
    if (trends.conditions && trends.conditions.length > 1) {
        html += '<br>';
        trends.conditions.forEach(c => {
            const label = c.condition === 'critique_on' ? 'w/ critique' : 'w/o critique';
            html += `<span class="state-key">${label}: </span><span class="state-val">${c.condition_mean.toFixed(2)} (n=${c.condition_count})</span> `;
        });
    }
    el.innerHTML = html || '<span class="state-key">Waiting for data...</span>';
}

function updateDimensions(scores) {
    if (!scores) return;
    ['novelty', 'surprise', 'value', 'elaboration', 'coherence'].forEach(d => {
        const val = scores[d];
        if (val != null) {
            document.getElementById('dim-' + d).textContent = val.toFixed(1);
            document.getElementById('bar-' + d).style.width = (val / 10 * 100) + '%';
        }
    });
}

function updateState(s) {
    if (!s) return;
    document.getElementById('state-running').textContent = s.running ? 'running' : 'idle';
    document.getElementById('state-lane').textContent = s.current_lane || '--';
    document.getElementById('state-track').textContent = s.current_track || '--';
    document.getElementById('state-experiment').textContent = s.current_experiment_id ? '#' + s.current_experiment_id : '#--';
    document.getElementById('state-updated').textContent = s.updated_at || '--';
}

function signed(value) {
    if (value == null || Number.isNaN(value)) return '--';
    return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`;
}

function truncateMiddle(s, n) {
    if (!s || s.length <= n) return s || '';
    const keep = Math.floor((n - 3) / 2);
    return `${s.slice(0, keep)}...${s.slice(-keep)}`;
}

function formatPct(value) {
    if (value == null || Number.isNaN(value)) return '--';
    return `${(value * 100).toFixed(0)}%`;
}

function getAdminToken() {
    return window.localStorage.getItem(ADMIN_TOKEN_STORAGE_KEY) || '';
}

function ensureAdminToken() {
    let token = getAdminToken();
    if (token) return token;
    token = window.prompt('Enter the lab admin token to continue:') || '';
    if (!token) return '';
    window.localStorage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
    return token;
}

function buildAdminHeaders(includeJson = true) {
    const token = ensureAdminToken();
    if (!token) return null;
    const headers = {};
    if (includeJson) headers['Content-Type'] = 'application/json';
    headers['X-Admin-Token'] = token;
    return headers;
}

function renderMetricList(items, formatter) {
    if (!items || items.length === 0) {
        return '<div class="analysis-empty">Not enough data yet.</div>';
    }
    return items.map(formatter).join('');
}

function updateAnalysis(data) {
    renderSummary(data?.balance_summary || {});
    renderLearningSnapshot(data?.learning_snapshot || {});
    renderGeneratorLearning(data?.generator_learning || {});
    renderRecommendations(data?.recommendations || {});
    renderHypotheses(data?.hypotheses || []);
    renderBalance(data?.creativity_balance || []);
    renderPaired(data?.paired_conditions || []);
    renderTax(data?.business_creativity_tax || []);
    renderChampions(data?.champions || []);
    renderPolicyEffects(data?.policy_effects || {});
    renderPolicyValidation(data?.policy_validation || {});
    renderDiagnostics(data?.evaluator_diagnostics || {});
    renderProtocolReliability(data?.protocol_reliability || {});
    renderHumanCalibration(data?.human_calibration || {});
    renderConstraintVerifier(data?.constraint_verifier || {});
    renderCalibrationMetrics(data?.calibration_metrics || {});
    renderDisagreementQueue(data?.disagreement_queue || {});
    renderPolicyRecommendations(data?.policy_recommendations || {});
}

function renderSummary(data) {
    const el = document.getElementById('analysis-summary');
    const thesis = 'Hamlet’s Ghost compares rival model voices under automated and human judgment to discover what actually makes an artifact strong.';
    const headline = data?.headline;
    const lanes = data?.lane_summaries || [];
    const laneHtml = lanes.slice(0, 2).map(row => `
        <div class="analysis-summary-line">
            <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
            <span>
                ${row.sample_size != null ? `n=${row.sample_size}` : 'tracked'}
                ${row.novelty_pressure != null ? ` · novelty ${row.novelty_pressure.toFixed(2)}` : ''}
                ${row.value_grounding != null ? ` · grounding ${row.value_grounding.toFixed(2)}` : ''}
                ${row.balance_gap != null ? ` · gap ${signed(row.balance_gap)}` : ''}
            </span>
        </div>
    `).join('');
    el.innerHTML = `
        <div class="analysis-summary-headline">${thesis}</div>
        <div class="analysis-subtle">${headline || 'The lab is comparing generators, tracking evaluator disagreement, and using human review to build revisable judgment memory.'}</div>
        ${laneHtml || '<div class="analysis-empty">Lane-level learning will appear here as the current epoch grows.</div>'}
    `;
}

function renderLearningSnapshot(data) {
    const el = document.getElementById('analysis-learning-snapshot');
    if (!el) return;
    if (!data || (!data.headline && !data.improved && !data.regressed && !data.still_noisy && !data.next_move)) {
        el.innerHTML = '<div class="analysis-empty">No learning snapshot yet.</div>';
        return;
    }

    const lines = [
        ['Improved', data.improved],
        ['Regressed', data.regressed],
        ['Still Noisy', data.still_noisy],
        ['Next', data.next_move],
    ].filter(([, value]) => value).slice(0, 2);

    el.innerHTML = `
        <div class="analysis-summary-headline">${data.headline || 'Learning snapshot in progress.'}</div>
        ${lines.map(([label, value]) => `
            <div class="analysis-item">
                <div class="analysis-main">${label}</div>
                <div class="analysis-sub">${escapeHtml(value)}</div>
            </div>
        `).join('')}
    `;
}

function renderGeneratorLearning(data) {
    const el = document.getElementById('analysis-generator-learning');
    if (!el) return;
    const rows = data?.rows || [];
    if (!rows.length) {
        el.innerHTML = '<div class="analysis-empty">No generator coaching yet.</div>';
        return;
    }
    el.innerHTML = `
        <div class="analysis-summary-headline">${escapeHtml(data.headline || 'Generator coaching in progress.')}</div>
        ${rows.map(row => {
            const role = escapeHtml((row.role_id || 'generator').replaceAll('_', ' '));
            const focusFamily = escapeHtml((row.focus_family || 'all families').replaceAll('_', ' '));
            const topFlaws = (row.focus_top_flaws || row.top_flaws || []).slice(0, 2).map(escapeHtml).join(', ');
            const topStrengths = (row.focus_top_strengths || row.top_strengths || []).slice(0, 2).map(escapeHtml).join(', ');
            const pairFailures = (row.focus_top_pair_failures || row.top_pair_failures || []).slice(0, 2).map(escapeHtml).join(', ');
            const scope = escapeHtml((row.focus_scope_applied || 'global').replaceAll('_', ' '));
            return `
                <div class="analysis-item">
                    <div class="analysis-head">
                        <span class="analysis-kicker">${role}</span>
                        <span class="analysis-kicker">${focusFamily}</span>
                    </div>
                    <div class="analysis-main">${row.losses || 0} loss${(row.losses || 0) === 1 ? '' : 'es'} from ${row.final_reviewed_packets || 0} final review${(row.final_reviewed_packets || 0) === 1 ? '' : 's'}</div>
                    <div class="analysis-sub">Coaching scope: ${scope}. ${topFlaws ? `Suppress ${topFlaws}. ` : ''}${pairFailures ? `Fix pair failures: ${pairFailures}. ` : ''}${topStrengths ? `Preserve ${topStrengths}.` : 'No stable preserve signal yet.'}</div>
                    <div class="analysis-metrics">
                        <span>wins ${row.wins || 0}</span>
                        <span>losses ${row.losses || 0}</span>
                        <span>same writer ${row.same_writer_reviews || 0}</span>
                        <span>low confidence ${row.low_confidence_reviews || 0}</span>
                        <span>revisit later ${row.revisit_later_reviews || 0}</span>
                    </div>
                </div>
            `;
        }).join('')}
    `;
}

function renderDecision(elId, label, row, detailBuilder) {
    const el = document.getElementById(elId);
    if (!row) {
        el.innerHTML = '<div class="analysis-empty">Not enough data yet.</div>';
        return;
    }
    const lane = row.lane || (elId === 'analysis-stop' ? 'business' : 'creative');
    const family = row.prompt_family || 'unclassified';
    el.innerHTML = `
        <div class="analysis-item">
            <div class="analysis-head">
                <span class="lane-badge ${lane}">${lane}</span>
                <span class="analysis-kicker">${family}</span>
            </div>
            <div class="analysis-main">${row.hypothesis_id || row.hypothesis || 'no hypothesis'}</div>
            <div class="analysis-sub">${detailBuilder(row)}</div>
        </div>
    `;
}

function renderRecommendations(data) {
    renderDecision('analysis-scale', 'Scale', data.scale, row =>
        `Best current bet to scale. Composite ${row.mean_composite?.toFixed(2) || '--'}, shadow rate ${formatPct(row.shadow_rate)}, n=${row.trials || 0}.`
    );
    renderDecision('analysis-watch', 'Watch', data.watch, row =>
        `Largest critique effect observed. Critique delta ${signed(row.composite_delta)} on matched prompt family; this is where critique policy may matter most.`
    );
    renderDecision('analysis-stop', 'Stop', data.stop, row =>
        `Highest business creativity tax. Novelty ${row.mean_novelty?.toFixed(2) || '--'} versus utility ${row.utility_mean?.toFixed(2) || '--'} suggests cleverness may be outrunning usefulness.`
    );
    renderDecision('analysis-question', 'Open Question', data.question, row => {
        if (row.mean_divergence != null) {
            return `Evaluator disagreement is elevated here (\u0394 ${row.mean_divergence.toFixed(2)}). This may need human review before drawing conclusions.`;
        }
        return `Critique delta is close to zero (${signed(row.composite_delta)}). Useful test case for asking whether creativity or critique is actually helping this family.`;
    });
}

function renderHypotheses(rows) {
    const el = document.getElementById('analysis-hypotheses');
    const top = rows.slice(0, 6);
    el.innerHTML = renderMetricList(top, row => `
        <div class="analysis-item">
            <div class="analysis-head">
                <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                <span class="analysis-kicker">${row.prompt_family || row.family || 'unclassified'}</span>
            </div>
            <div class="analysis-main">${row.hypothesis_id || row.hypothesis || 'no hypothesis'}</div>
            <div class="analysis-sub">${truncateMiddle(row.hypothesis_description || 'Recent performance on this hypothesis family.', 88)}</div>
            <div class="analysis-metrics">
                <span>score ${row.mean_composite?.toFixed(2) || '--'}</span>
                <span>keep ${formatPct(row.keep_rate)}</span>
                <span>n=${row.sample_size || row.trials || 0}</span>
            </div>
        </div>
    `);
}

function renderBalance(rows) {
    const el = document.getElementById('analysis-balance');
    const ranked = rows
        .filter(row => row.balance_gap != null)
        .sort((a, b) => Math.abs(b.balance_gap || 0) - Math.abs(a.balance_gap || 0))
        .slice(0, 6);
    el.innerHTML = renderMetricList(ranked, row => {
        const gapClass = Math.abs(row.balance_gap || 0) < 0.5
            ? 'metric-neutral'
            : (row.balance_gap || 0) > 0
                ? 'metric-down'
                : 'metric-up';
        const counterpart = row.counterpart_label || 'utility';
        const balanceLabel = row.balance_class || 'balanced';
        return `
            <div class="analysis-item">
                <div class="analysis-head">
                    <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                    <span class="analysis-kicker">${row.prompt_family || row.family || 'unclassified'}</span>
                </div>
                <div class="analysis-main">${row.hypothesis_id || row.hypothesis || `${row.lane || 'creative'} balance`}</div>
                <div class="analysis-sub">Creativity pressure versus grounding in recent scored work.</div>
                <div class="analysis-metrics">
                    <span>creativity ${row.novelty_pressure?.toFixed(2) || '--'}</span>
                    <span>${counterpart} ${row.value_grounding?.toFixed(2) || '--'}</span>
                    <span class="${gapClass}">gap ${signed(row.balance_gap)}</span>
                </div>
                <div class="analysis-note">
                    ${balanceLabel}. n=${row.sample_size || row.trials || 0}.
                </div>
            </div>
        `;
    });
}

function renderPaired(rows) {
    const el = document.getElementById('analysis-paired');
    const ranked = rows
        .filter(row => row.mean_composite != null || row.composite_delta != null)
        .sort((a, b) => ((b.composite_delta ?? b.mean_composite) || 0) - ((a.composite_delta ?? a.mean_composite) || 0))
        .slice(0, 6);
    el.innerHTML = renderMetricList(ranked, row => `
        <div class="analysis-item">
            <div class="analysis-head">
                <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
            </div>
            <div class="analysis-main">${formatConditionLabel(row.condition)}</div>
            <div class="analysis-sub">Comparison outcome summary from recent paired packets.</div>
            <div class="analysis-metrics">
                <span>mean ${row.mean_composite?.toFixed(2) || '--'}</span>
                <span>keep ${formatPct(row.keep_rate)}</span>
                <span>n=${row.sample_size || 0}</span>
            </div>
        </div>
    `);
}

function renderTax(rows) {
    const el = document.getElementById('analysis-tax');
    const top = rows.slice(0, 6);
    el.innerHTML = renderMetricList(top, row => `
        <div class="analysis-item">
            <div class="analysis-head">
                <span class="lane-badge business">business</span>
                <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
            </div>
            <div class="analysis-main">Business creativity tax</div>
            <div class="analysis-sub">Where novelty may be outrunning commercial grounding.</div>
            <div class="analysis-metrics">
                <span>novelty ${row.novelty?.toFixed(2) || '--'}</span>
                <span>grounding ${row.grounding?.toFixed(2) || '--'}</span>
                <span class="${(row.creativity_tax || 0) > 0 ? 'metric-down' : 'metric-up'}">tax ${signed(row.creativity_tax)}</span>
                <span>n=${row.sample_size || 0}</span>
            </div>
        </div>
    `);
}

function renderChampions(rows) {
    const el = document.getElementById('analysis-champions');
    const top = rows.slice(0, 6);
    el.innerHTML = renderMetricList(top, row => `
        <div class="analysis-item">
            <div class="analysis-head">
                <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                <span class="analysis-kicker">${row.family || row.prompt_family || 'unclassified'}</span>
            </div>
            <div class="analysis-main">Experiment #${row.experiment_id || '--'}</div>
            <div class="analysis-sub">${truncateMiddle(row.prompt_preview || '', 88)}</div>
            <div class="analysis-metrics">
                <span>score ${row.composite?.toFixed(2) || '--'}</span>
                <span>${formatOutcomeLabel(row.status, row.promotion_status)}</span>
            </div>
        </div>
    `);
}

function renderPolicyEffects(data) {
    const el = document.getElementById('analysis-policy-effects');
    if (!el) return;
    if (!data || (!data.headline && !(data.rows || []).length)) {
        el.innerHTML = '<div class="analysis-empty">No policy-effect readout yet.</div>';
        return;
    }

    const overview = data.overview || {};
    const best = overview.best_variant;
    const riskiest = overview.riskiest_variant;
    const critiqueSensitive = overview.critique_sensitive_variant;
    const overviewBits = [
        best ? `best ${best.prompt_policy_variant} ${signed(best.composite_lift)}` : null,
        critiqueSensitive ? `critique ${critiqueSensitive.prompt_policy_variant} ${signed(critiqueSensitive.critique_delta)}` : null,
        riskiest ? `risk ${riskiest.prompt_policy_variant} ${formatPct(riskiest.constraint_fail_rate)}` : null,
    ].filter(Boolean).map(text => `<span>${text}</span>`).join('');

    const rows = (data.rows || []).slice(0, 6).map(row => `
        <div class="analysis-item">
            <div class="analysis-head">
                <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
                <span class="analysis-kicker">${row.policy_source || 'policy source unknown'}</span>
            </div>
            <div class="analysis-main">${row.prompt_policy_variant || 'unknown policy'}</div>
            <div class="analysis-sub">${[row.framing_style, row.novelty_pressure, row.audience_grounding_level, row.approved_family_policy_variant ? `approved ${row.approved_family_policy_variant}` : null].filter(Boolean).join(' · ') || 'No policy metadata.'}</div>
            <div class="analysis-metrics">
                <span>score ${row.mean_composite?.toFixed(2) || '--'}</span>
                <span class="${(row.composite_lift || 0) >= 0 ? 'metric-up' : 'metric-down'}">lift ${signed(row.composite_lift)}</span>
                <span>critique ${signed(row.critique_delta)}</span>
                <span>constraint fail ${formatPct(row.constraint_fail_rate)}</span>
                <span>unknown ${formatPct(row.unknown_constraint_rate)}</span>
                <span>n=${row.trials || 0}</span>
            </div>
        </div>
    `).join('');

    el.innerHTML = `
        <div class="analysis-summary-headline">${data.headline || 'Policy effects in progress.'}</div>
        ${overviewBits ? `<div class="analysis-item"><div class="analysis-metrics">${overviewBits}</div></div>` : ''}
        ${rows || '<div class="analysis-empty">Not enough policy-variant data yet.</div>'}
    `;
}

function renderPolicyValidation(data) {
    const el = document.getElementById('analysis-policy-validation');
    if (!el) return;
    const rows = data.rows || [];
    if (!data || (!data.headline && !rows.length)) {
        el.innerHTML = '<div class="analysis-empty">No policy validation campaigns yet.</div>';
        return;
    }

    const overview = data.overview || {};
    const chips = [
        `tracked ${overview.tracked_defaults || 0}`,
        `pending ${overview.approved_pending_use || 0}`,
        `trial ${overview.approved_in_trial || 0}`,
        `review-cleared ${overview.approved_validated || 0}`,
    ].map(text => `<span>${text}</span>`).join('');

    el.innerHTML = `
        <div class="analysis-summary-headline">${data.headline || 'Policy validation in progress.'}</div>
        <div class="analysis-item"><div class="analysis-metrics">${chips}</div></div>
        ${rows.slice(0, 6).map(row => `
            <div class="analysis-item">
                <div class="analysis-head">
                    <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                    <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
                    <span class="analysis-kicker">${row.operational_status || row.approval_status || 'pending'}</span>
                </div>
                <div class="analysis-main">${escapeHtml(row.approved_value || row.recommended_value || '--')}</div>
                <div class="analysis-metrics">
                    <span>trials ${row.adopted_trials || 0}</span>
                    <span>mean ${row.adopted_mean_composite != null ? row.adopted_mean_composite.toFixed(2) : '--'}</span>
                    <span>constraint fail ${formatPct(row.adopted_constraint_fail_rate)}</span>
                    <span>human keep ${formatPct(row.adopted_human_keep_rate)}</span>
                </div>
            </div>
        `).join('') || '<div class="analysis-empty">No approved defaults have entered validation yet.</div>'}
    `;
}

function renderDiagnostics(data) {
    const el = document.getElementById('analysis-diagnostics');
    if (!data || (!data.headline && !data.warnings?.length && data.disagreement_rate == null)) {
        el.innerHTML = '<div class="analysis-empty">Not enough data yet.</div>';
        return;
    }

    const warnings = (data.warnings || []).slice(0, 3).map(text => `
        <div class="analysis-item">
            <div class="analysis-main">Evaluator Risk</div>
            <div class="analysis-sub">${text}</div>
        </div>
    `).join('');

    el.innerHTML = `
        <div class="analysis-item">
            <div class="analysis-main">Evaluator Diagnostics</div>
            <div class="analysis-sub">${escapeHtml(data.headline || 'Evaluator diagnostics in progress.')}</div>
            <div class="analysis-metrics">
                <span>disagreement ${formatPct(data.disagreement_rate)}</span>
                <span>human reviews ${data.human_reviews || 0}</span>
            </div>
        </div>
        ${warnings || '<div class="analysis-empty">No evaluator warnings yet.</div>'}
    `;
}

function renderProtocolReliability(data) {
    const el = document.getElementById('analysis-protocol-reliability');
    if (!el) return;
    const rows = data.rows || [];
    if (!data || (!data.headline && !rows.length)) {
        el.innerHTML = '<div class="analysis-empty">No protocol reliability data yet.</div>';
        return;
    }

    const overview = data.overview || {};
    const protocolVersions = Object.entries(data.protocol_versions || {})
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
        .map(([label, count]) => `${label} ${count}`)
        .join(' · ');

    el.innerHTML = `
        <div class="analysis-summary-headline">${data.headline || 'Protocol reliability in progress.'}</div>
        <div class="analysis-item">
            <div class="analysis-main">Overall</div>
            <div class="analysis-metrics">
                <span>selection ${formatPct(overview.selection_fallback_rate)}</span>
                <span>interlocutor ${formatPct(overview.interlocutor_fallback_rate)}</span>
                <span>Athena skip ${formatPct(overview.athena_skip_rate)}</span>
                <span>forced Athena ${formatPct(overview.athena_forced_rate)}</span>
            </div>
            <div class="analysis-sub">${protocolVersions || 'No protocol version split yet.'}</div>
        </div>
        <div class="analysis-empty">Family-level reliability slices are not surfaced yet in the current payload.</div>
    `;
}

function renderHumanCalibration(data) {
    const el = document.getElementById('analysis-human-characterization');
    if (!data || (!data.headline && !data.lane_summaries?.length)) {
        el.innerHTML = '<div class="analysis-empty">No human reviews yet.</div>';
        return;
    }

    const lanes = (data.lane_summaries || []).slice(0, 2);
    const laneHtml = lanes.map(row => {
        return `
            <div class="analysis-item">
                <div class="analysis-head">
                    <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                    <span class="analysis-kicker">n=${row.sample_size}</span>
                </div>
                <div class="analysis-main">Muse ${row.mean_muse_composite?.toFixed(2) || '--'}</div>
                <div class="analysis-sub">Human characterization present in this lane.</div>
                <div class="analysis-metrics">
                    <span>${row.lane === data.priority ? 'current priority lane' : 'tracked lane'}</span>
                </div>
            </div>
        `;
    }).join('');
    const confidenceMix = Object.entries(data.confidence_mix || {})
        .map(([label, count]) => `${label.replaceAll('_', ' ')} ${count}`)
        .join(' · ');
    const distinctivenessMix = Object.entries(data.distinctiveness_mix || {})
        .filter(([label]) => label !== 'unspecified')
        .map(([label, count]) => `${label.replaceAll('_', ' ')} ${count}`)
        .join(' · ');
    const blindCandidates = (data.blind_candidates || []).map(row => `
        <div class="analysis-item">
            <div class="analysis-head">
                <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                <span class="analysis-kicker">${escapeHtml((row.family || 'unclassified').replaceAll('_', ' '))}</span>
            </div>
            <div class="analysis-main">Last reviewed ${escapeHtml(row.updated_at || '--')}</div>
            <div class="analysis-sub">
                ${escapeHtml((row.review_confidence || 'unspecified').replaceAll('_', ' '))}
                · revisions ${row.review_revision_count || 0}
                · reversals ${row.review_reversal_count || 0}
            </div>
            <div class="analysis-metrics">
                <button class="btn-refresh primary" onclick="openBlindRereviewCandidate('${row.packet_id}')">Blind Re-review</button>
            </div>
        </div>
    `).join('');

    el.innerHTML = `
        <div class="analysis-summary-headline">${data.headline || 'Human characterization in progress.'}</div>
        <div class="analysis-item">
            <div class="analysis-main">Operator Stability</div>
            <div class="analysis-metrics">
                <span>confidence ${escapeHtml(confidenceMix || 'not enough data')}</span>
                <span>low confidence ${data.low_confidence_count || 0}</span>
                <span>revisit later ${data.revisit_later_count || 0}</span>
                <span>reversals ${data.reversal_count || 0}</span>
            </div>
        </div>
        <div class="analysis-item">
            <div class="analysis-main">Comparative Usefulness</div>
            <div class="analysis-metrics">
                <span>usefulness ${data.comparative_usefulness_score != null ? formatPct(data.comparative_usefulness_score) : 'not enough data'}</span>
                <span>same writer ${data.same_writer_count || 0}</span>
            </div>
            <div class="analysis-sub">${escapeHtml(distinctivenessMix || 'Distinctiveness judgments will appear after packet reviews start classifying generator separation.')}</div>
        </div>
        ${laneHtml || '<div class="analysis-empty">No lane summaries yet.</div>'}
        ${blindCandidates || '<div class="analysis-empty">No blind re-review candidates yet.</div>'}
    `;
}

function renderConstraintVerifier(data) {
    const el = document.getElementById('analysis-constraint-verifier');
    if (!data || (!data.headline && !data.families?.length && !data.totals)) {
        el.innerHTML = '<div class="analysis-empty">No verifier data yet.</div>';
        return;
    }

    const totals = data.totals || {};
    const familyRows = (data.families || []).map(row => `
        <div class="analysis-item">
            <div class="analysis-head">
                <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
                <span class="analysis-kicker">n=${row.sample_size || 0}</span>
            </div>
            <div class="analysis-sub">
                verification pass ${formatPct(row.verification_pass_rate)}
            </div>
        </div>
    `).join('');

    el.innerHTML = `
        <div class="analysis-summary-headline">${data.headline || 'Verifier tracking in progress.'}</div>
        <div class="analysis-item">
            <div class="analysis-main">Verifier Totals</div>
            <div class="analysis-metrics">
                <span>tracked ${totals.runs_with_verifier || 0}</span>
                <span>pass ${formatPct(totals.verification_pass_rate)}</span>
                <span>repair attempts ${formatPct(totals.repair_attempt_rate)}</span>
            </div>
        </div>
        ${familyRows || '<div class="analysis-empty">No family-level verifier data yet.</div>'}
    `;
}

function renderCalibrationMetrics(data) {
    const el = document.getElementById('analysis-calibration-metrics');
    if (!el) return;
    if (!data || !data.overview || !data.families) {
        el.innerHTML = '<div class="analysis-empty">No characterization metrics yet.</div>';
        return;
    }

    const overview = data.overview || {};
    const familyRows = (data.families || []).slice(0, 6).map(row => `
        <div class="analysis-item">
            <div class="analysis-head">
                <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
            </div>
            <div class="analysis-metrics">
                <span>overreach ${formatPct(row.overreach_rate)}</span>
                <span>gap ${signed(row.novelty_gap)}</span>
                <span>n=${row.sample_size || 0}</span>
            </div>
        </div>
    `).join('');

    el.innerHTML = `
        <div class="analysis-summary-headline">${data.headline || 'Calibration metrics in progress.'}</div>
        <div class="analysis-item">
            <div class="analysis-main">Overall</div>
            <div class="analysis-metrics">
                <span>overreach ${formatPct(overview.creativity_overreach_rate)}</span>
                <span>unknown constraints ${formatPct(overview.unknown_constraint_rate)}</span>
                <span>gap ${signed(overview.mean_novelty_gap)}</span>
                <span>human agreement ${formatPct(overview.human_agreement_rate)}</span>
            </div>
        </div>
        ${familyRows || '<div class="analysis-empty">Not enough family-level characterization data yet.</div>'}
    `;
}

function renderDisagreementQueue(data) {
    const el = document.getElementById('analysis-disagreement-queue');
    if (!el) return;
    const rows = data.rows || [];
    const assemblingRows = data.assembling_rows || [];
    const stalledRows = data.stalled_rows || [];
    const graveyardRows = data.graveyard_rows || [];
    if (!rows.length && !assemblingRows.length && !stalledRows.length && !graveyardRows.length) {
        el.innerHTML = '<div class="analysis-empty">No disagreement cases queued yet.</div>';
        return;
    }
    el.innerHTML = `
        <div class="analysis-summary-headline">${data.headline || 'Human review queue in progress.'}</div>
        ${rows.slice(0, 3).map(row => `
            <div class="analysis-item">
                <div class="analysis-head">
                    <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                    <span class="analysis-kicker">${row.family || row.prompt_family || 'unclassified'}</span>
                    <span class="analysis-kicker">${formatConditionLabel(row.condition)}</span>
                </div>
                <div class="analysis-sub">${truncateMiddle(row.prompt || '', 96)}</div>
                <div class="analysis-metrics">
                    <span>${Object.entries(row.vote_counts || {}).map(([winner, count]) => `#${winner} ${count} vote${count === 1 ? '' : 's'}`).join(' · ') || 'mixed preferences'}</span>
                    ${!row.has_complete_panel && (row.missing_judges || []).length ? `<span>pending ${row.missing_judges.map(formatRoleLabel).join(', ')}</span>` : ''}
                </div>
            </div>
        `).join('')}
        ${assemblingRows.length ? `
            <div class="analysis-item">
                <div class="analysis-main">${escapeHtml(data.assembling_headline || 'Paired packets still assembling.')}</div>
                <div class="analysis-sub">${assemblingRows.map(row => escapeHtml(truncateMiddle(row.prompt || 'Packet assembling.', 56))).join(' · ')}</div>
            </div>
        ` : ''}
        ${stalledRows.length ? `
            <div class="analysis-item">
                <div class="analysis-main">${escapeHtml(data.stalled_headline || 'Paired packets are stalled and need repair.')}</div>
                <div class="analysis-sub">${stalledRows.map(row => escapeHtml(truncateMiddle(row.prompt || 'Packet stalled.', 56))).join(' · ')}</div>
            </div>
        ` : ''}
        ${graveyardRows.length ? `
            <div class="analysis-item">
                <div class="analysis-main">${escapeHtml(data.graveyard_headline || 'Packet graveyard')}</div>
                <div class="analysis-sub">${graveyardRows.map(row => escapeHtml(truncateMiddle(row.prompt || row.packet_id || 'Resolved packet', 56))).join(' · ')}</div>
            </div>
        ` : ''}
    `;
}

function renderPolicyRecommendations(data) {
    const el = document.getElementById('analysis-policy-ledger');
    if (!el) return;
    const rows = data.rows || [];
    if (!rows.length) {
        el.innerHTML = '<div class="analysis-empty">No policy recommendations yet.</div>';
        return;
    }
    el.innerHTML = `
        <div class="analysis-summary-headline">${data.headline || 'Policy recommendations in progress.'}</div>
        ${rows.slice(0, 6).map(row => `
            <div class="analysis-item">
                <div class="analysis-head">
                    <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                    <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
                    <span class="analysis-kicker">${escapeHtml(row.policy_key || 'policy')}</span>
                </div>
                <div class="analysis-main">${escapeHtml(row.recommended_value || '--')}</div>
                <div class="analysis-sub">${escapeHtml(row.rationale || '')}</div>
                <div class="analysis-metrics">
                    <span>status ${escapeHtml(row.approval_status || 'pending')}</span>
                    <span>ops ${escapeHtml(row.operational_status || row.approval_status || 'pending')}</span>
                    <span>${row.approved_value ? `approved ${escapeHtml(row.approved_value)}` : 'awaiting human review'}</span>
                    ${row.approval_status === 'approved' ? `<span>used n=${row.adopted_trials || 0}</span>` : ''}
                    ${row.adopted_mean_composite != null ? `<span>post-adopt ${row.adopted_mean_composite.toFixed(2)}</span>` : ''}
                </div>
            </div>
        `).join('')}
    `;
}

function initChart() {
    const ctx = document.getElementById('score-chart').getContext('2d');
    scoreChart = new Chart(ctx, {
        type: 'bar',
        data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderWidth: 0, barPercentage: 0.85, categoryPercentage: 0.9 }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: {
                backgroundColor: '#0f1419', borderColor: '#1a2030', borderWidth: 1,
                titleFont: { family: 'JetBrains Mono', size: 11 },
                bodyFont: { family: 'JetBrains Mono', size: 11 },
                callbacks: {
                    title: (items) => 'Experiment #' + items[0].label,
                    label: (item) => 'Score: ' + item.raw.toFixed(2),
                }
            }},
            scales: {
                x: { display: false },
                y: { display: true, min: 0, max: 10,
                    grid: { color: 'rgba(26, 32, 48, 0.5)', drawTicks: false },
                    ticks: { color: '#5c6773', font: { family: 'JetBrains Mono', size: 10 }, stepSize: 2 },
                    border: { display: false }
                }
            }
        }
    });
}

function updateChart(timeline) {
    if (!scoreChart || !timeline || timeline.length === 0) return;
    scoreChart.data.labels = timeline.map(t => t.experiment_id);
    scoreChart.data.datasets[0].data = timeline.map(t => t.composite || 0);
    scoreChart.data.datasets[0].backgroundColor = timeline.map(t => {
        if (t.parse_failure) return '#ffd740';
        if (t.constraints_met === 0) return '#ff9800';
        if (t.promotion_status === 'shadow') return '#b388ff';
        if (t.status === 'kept' || t.status === 'promoted') return '#00e676';
        return '#c62828';
    });
    scoreChart.update('none');
}

function updateHistory(history) {
    const tbody = document.getElementById('history-body');
    if (!history || history.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center; color: var(--text-dim); padding: 24px;">No experiments yet. Run a paired packet or start a batch to begin.</td></tr>';
        return;
    }
    tbody.innerHTML = history.map(h => {
        const statusClass = h.status || 'pending';
        const primaryGenerator = h.role_packets?.generators?.[0];
        const comparison = h.comparison_packet;
        const evaluators = h.role_packets?.evaluators || [];
        const judgeLine = evaluators.length
            ? evaluators.slice(0, 3).map(evaluator => `${formatRoleLabel(evaluator.role_id)} ${fmtScore(evaluator.scores?.composite)}`).join(' · ')
            : `Muse ${fmtScore(h.composite)}`;
        const packetLabel = comparison && comparison.size > 1
            ? `${comparison.size} voices`
            : 'Single';
        const familyLabel = (h.family || h.prompt_family || 'unclassified').replaceAll('_', ' ');
        return `<tr onclick="showArtifact(${h.id})">
            <td>${h.id}</td>
            <td><span class="status-badge ${statusClass}">${escapeHtml(formatOutcomeLabel(h.status, h.promotion_status))}</span></td>
            <td class="desc-cell">
                <div class="history-prompt-preview">${truncate(h.prompt || '', 72)}</div>
                <div class="history-role-line">${escapeHtml(h.lane || 'creative')} · ${escapeHtml(familyLabel)}</div>
            </td>
            <td><div class="history-role-line">${primaryGenerator ? `${escapeHtml(formatRoleLabel(primaryGenerator.role_id))} · ${escapeHtml(primaryGenerator.provider || 'local')}` : '--'}</div></td>
            <td><div class="history-role-line history-judge-line">${escapeHtml(judgeLine)}</div></td>
            <td><div class="history-role-line">${escapeHtml(packetLabel)}</div></td>
            <td><div class="history-role-line">${escapeHtml(`${formatConditionLabel(h.condition)} · ${formatTrackLabel(h.track)}`)}</div></td>
        </tr>`;
    }).join('');
}

function fmtScore(v) { return v != null ? v.toFixed(1) : '--'; }
function truncate(s, n) { return s.length > n ? s.substring(0, n) + '...' : s; }
function formatRoleLabel(roleId) {
    const labels = {
        genesis: 'Genesis',
        raw_prompt: 'Raw Prompt',
        compiled_prompt: 'Compiled Prompt',
        genesis_openclaw: 'Genesis OpenClaw',
        theron: 'Theron',
        muse: 'Muse',
        athena: 'Athena',
        hermes: 'Athena',
        apollo: 'Apollo',
        hermes_external: 'Apollo',
        critic_holdout: 'Critic Holdout',
    };
    return labels[roleId] || roleId;
}
function scoreCard(dim, value, extraClass = '') {
    return `<div class="modal-score ${extraClass}"><div class="label">${dim}</div><div class="val">${value != null ? value.toFixed(1) : '--'}</div></div>`;
}

function renderEvaluatorCards(evaluators, activeDims) {
    if (!evaluators || evaluators.length === 0) return '';
    return evaluators.map(evaluator => `
        <div class="modal-scorer-label">${escapeHtml(formatRoleLabel(evaluator.role_id))}${evaluator.shadow_only ? ' (shadow)' : ''}${evaluator.provider ? ` · ${escapeHtml(evaluator.provider)}` : ''}</div>
        ${activeDims.map(d => scoreCard(d, evaluator.scores?.[d], evaluator.shadow_only ? 'holdout' : '')).join('')}
        ${evaluator.constraints_met != null ? `<div class="modal-inline-note">constraints: ${evaluator.constraints_met ? 'met' : 'failed'}</div>` : ''}
        ${evaluator.critique ? `<div class="modal-inline-note">${escapeHtml(truncate(evaluator.critique, 220))}</div>` : ''}
    `).join('');
}

function renderRolePackets(data) {
    const section = document.getElementById('modal-role-packets-section');
    const el = document.getElementById('modal-role-packets');
    const packets = data.role_packets;
    if (!packets || ((!packets.generators || packets.generators.length === 0) && (!packets.evaluators || packets.evaluators.length === 0))) {
        section.style.display = 'none';
        el.textContent = '';
        return;
    }

    const generatorHtml = (packets.generators || []).map(packet => `
        <div class="packet-card ${packet.primary ? 'primary' : 'shadow'}">
            <div class="packet-title">${escapeHtml(formatRoleLabel(packet.role_id))}${packet.primary ? ' · primary generator' : ' · shadow generator'}</div>
            <div class="packet-meta">${escapeHtml(packet.provider || 'local')}${packet.model ? ` / ${escapeHtml(packet.model)}` : ''}</div>
            ${packet.artifact_contract_status ? `<div class="packet-note">artifact contract: ${escapeHtml(packet.artifact_contract_status)}</div>` : ''}
        </div>
    `).join('');

    const evaluatorHtml = (packets.evaluators || []).map(packet => `
        <div class="packet-card ${packet.shadow_only ? 'shadow' : 'primary'}">
            <div class="packet-title">${escapeHtml(formatRoleLabel(packet.role_id))}${packet.shadow_only ? ' · shadow evaluator' : ' · evaluator'}</div>
            <div class="packet-meta">${escapeHtml(packet.provider || 'local')}${packet.model ? ` / ${escapeHtml(packet.model)}` : ''}</div>
            <div class="packet-note">composite: ${packet.scores?.composite != null ? packet.scores.composite.toFixed(2) : '--'}</div>
        </div>
    `).join('');

    el.innerHTML = `
        <div class="packet-group">
            <div class="packet-group-title">Generators</div>
            <div class="packet-grid">${generatorHtml || '<div class="analysis-empty">No generator packets recorded.</div>'}</div>
        </div>
        <div class="packet-group">
            <div class="packet-group-title">Evaluators</div>
            <div class="packet-grid">${evaluatorHtml || '<div class="analysis-empty">No evaluator packets recorded.</div>'}</div>
        </div>
    `;
    section.style.display = 'block';
}

function renderComparisonPacket(data) {
    const section = document.getElementById('modal-comparison-section');
    const el = document.getElementById('modal-comparison');
    const packet = data.comparison_packet;
    const siblings = data.comparison_siblings || [];
    if (!packet || packet.size <= 1) {
        section.style.display = 'none';
        el.textContent = '';
        return;
    }

    const packetMemberForCurrent = (packet.members || []).find(m => m.experiment_id === data.id) || {};
    const currentSummary = {
        experiment_id: data.id,
        role_id: data.role_packets?.generators?.[0]?.role_id || packetMemberForCurrent.role_id || 'genesis',
        provider: data.role_packets?.generators?.[0]?.provider || packetMemberForCurrent.provider || 'local',
        status: data.status || packetMemberForCurrent.status,
        promotion_status: data.promotion_status || packetMemberForCurrent.promotion_status,
        composite: data.composite ?? packetMemberForCurrent.composite,
        artifact: data.artifact_content || data.artifact || '',
    };
    const normalizedSiblings = (siblings || []).map(sibling => ({
        experiment_id: sibling.experiment_id ?? sibling.id,
        role_id: sibling.role_id || sibling.role_packets?.generators?.[0]?.role_id || sibling.packet_role_id || 'generator',
        provider: sibling.provider || sibling.role_packets?.generators?.[0]?.provider || 'local',
        status: sibling.status,
        promotion_status: sibling.promotion_status,
        composite: sibling.composite,
        artifact: sibling.artifact_content || sibling.artifact || '',
    }));
    const members = [currentSummary, ...normalizedSiblings].sort((a, b) => (a.experiment_id || 0) - (b.experiment_id || 0));
    el.innerHTML = `
        <div class="packet-summary">Packet ${escapeHtml(packet.packet_id)} · ${packet.size} linked runs · ${escapeHtml((packet.role_ids || []).map(formatRoleLabel).join(' / '))}</div>
        <div class="packet-compare-grid">
            ${members.map(member => `
                <div class="packet-card compare clickable" onclick="showArtifact(${member.experiment_id})">
                    <div class="packet-title">#${member.experiment_id} · ${escapeHtml(formatRoleLabel(member.role_id || 'generator'))}</div>
                    <div class="packet-meta">${escapeHtml(member.provider || 'local')} · ${escapeHtml(member.status || '--')} / ${escapeHtml(member.promotion_status || '--')}</div>
                    <div class="packet-note packet-composite-line">primary composite: ${member.composite != null ? Number(member.composite).toFixed(2) : '--'}</div>
                    <div class="packet-artifact-preview">${escapeHtml(truncate(member.artifact || '', 260))}</div>
                    <div class="packet-open-hint">Open full artifact</div>
                </div>
            `).join('')}
        </div>
    `;
    section.style.display = 'block';
}

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
}

function setReviewValue(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    el.value = value == null ? '' : value;
}

function readReviewValue(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
}

function setReviewStatus(message, kind = 'saved') {
    const el = document.getElementById('modal-review-status');
    if (!el) return;
    el.textContent = message;
    el.className = `modal-review-status ${kind}`;
    el.style.display = 'block';
}

function populateHumanReview(review) {
    setReviewValue('review-interesting', review?.interesting);
    setReviewValue('review-effective', review?.effective);
    setReviewValue('review-constraint-fit', review?.constraint_fit);
    setReviewValue('review-worth-saving', review?.worth_saving);
    setReviewValue('review-novelty', review?.novelty);
    setReviewValue('review-surprise', review?.surprise);
    setReviewValue('review-value', review?.value);
    setReviewValue('review-elaboration', review?.elaboration);
    setReviewValue('review-coherence', review?.coherence);
    setReviewValue('review-best-part', review?.best_part);
    setReviewValue('review-missed-opportunity', review?.missed_opportunity);
    setReviewValue('review-socratic-question', review?.socratic_question);
}

function updateReviewCopy(lane) {
    const intro = document.getElementById('modal-review-intro');
    const label = document.getElementById('review-interesting-label');
    if (!intro || !label) return;

    if (lane === 'business') {
        label.textContent = 'Thoughtfulness (1-5)';
        intro.textContent = 'Score this artifact before revealing the model evaluation. For business tasks, thoughtfulness means it feels well-considered, human-aware, and emotionally attuned rather than generic or procedural. Then optionally add 1-10 dimension scores to compare directly with MUSE.';
        return;
    }

    label.textContent = 'Interesting (1-5)';
    intro.textContent = 'Score this artifact before revealing the model evaluation. For creative tasks, interesting means it feels alive, non-generic, and worth sustained attention. Then optionally add 1-10 dimension scores to compare directly with MUSE.';
}

function renderReviewComparison(data) {
    const el = document.getElementById('modal-review-comparison');
    const review = data?.human_review;
    if (!review) {
        el.style.display = 'none';
        return;
    }

    const mismatches = [];
    ['novelty', 'surprise', 'value', 'elaboration', 'coherence'].forEach(dim => {
        if (review[dim] != null && data[dim] != null) {
            const delta = review[dim] - data[dim];
            mismatches.push(`${dim} ${signed(delta)}`);
        }
    });

    const fastAverage = ['interesting', 'effective', 'constraint_fit', 'worth_saving']
        .map(key => review[key])
        .filter(v => v != null);
    const fastMean = fastAverage.length
        ? (fastAverage.reduce((sum, v) => sum + v, 0) / fastAverage.length)
        : null;

    el.innerHTML = `
        <strong>Your review is saved.</strong>
        ${fastMean != null ? ` Fast-pass mean ${fastMean.toFixed(2)}/5.` : ''}
        ${mismatches.length ? ` Human vs MUSE deltas: ${mismatches.join(' · ')}.` : ' Add optional 1-10 dimension scores to compare directly with MUSE.'}
    `;
    el.style.display = 'block';
}

function setModelEvaluationVisibility(forceVisible = false) {
    const wrapper = document.getElementById('modal-model-eval');
    const button = document.getElementById('review-reveal-button');
    modelEvaluationRevealed = forceVisible || modelEvaluationRevealed;
    wrapper.classList.toggle('hidden', !modelEvaluationRevealed);
    button.textContent = modelEvaluationRevealed ? 'Hide Model Evaluation' : 'Reveal Model Evaluation';
}

function toggleModelEvaluation() {
    modelEvaluationRevealed = !modelEvaluationRevealed;
    setModelEvaluationVisibility(modelEvaluationRevealed);
}
function summarizeModels(modelVersion) {
    if (!modelVersion) return '';
    try {
        const data = typeof modelVersion === 'string' ? JSON.parse(modelVersion) : modelVersion;
        return ['genesis', 'muse', 'athena', 'apollo', 'holdout']
            .filter(role => data[role])
            .map(role => `${role}:${data[role].backend}/${data[role].model}`)
            .join(' | ');
    } catch {
        return modelVersion;
    }
}

async function showArtifact(id) {
    try {
        const headers = buildAdminHeaders(false);
        if (!headers) return;
        const data = await fetch('/api/artifact/' + id, { headers }).then(r => r.json());
        if (data.error) return;
        currentArtifact = data;
        modelEvaluationRevealed = !!data.human_review;
        updateReviewCopy(data.lane);

        document.getElementById('modal-title').textContent = 'Experiment #' + data.id + ' \u2014 ' + (data.lane || '') + ' / ' + formatTrackLabel(data.track);

        let meta = '';
        if (data.condition) meta += `Mode: ${formatConditionLabel(data.condition)}`;
        if (data.status || data.promotion_status) meta += ` | Outcome: ${formatOutcomeLabel(data.status, data.promotion_status)}`;
        if (data.hypothesis_id) meta += ` | Hypothesis: ${data.hypothesis_id}`;
        if (data.prompt_family) meta += ` | Family: ${data.prompt_family.replaceAll('_', ' ')}`;
        if (data.critique_source) meta += ` | Critique: ${data.critique_source}`;
        if (data.model_version) meta += ` | Models: ${summarizeModels(data.model_version)}`;
        if (data.exp_parse_failure || data.score_parse_failure) meta += ' | \u26a0 PARSE FAILURE';
        document.getElementById('modal-meta').textContent = meta;

        const balanceEl = document.getElementById('modal-balance');
        if (data.balance_label) {
            const counterpart = data.balance_counterpart_label || 'counterpart';
            balanceEl.textContent = `${data.balance_label} | novelty ${data.novelty?.toFixed(2) || '--'} vs ${counterpart} ${data.balance_counterpart?.toFixed(2) || '--'} | gap ${signed(data.balance_gap)}`;
            balanceEl.style.display = 'block';
        } else {
            balanceEl.style.display = 'none';
        }

        document.getElementById('modal-prompt').textContent = data.prompt || '';

        const provenanceSection = document.getElementById('modal-provenance-section');
        const provenanceEl = document.getElementById('modal-provenance');
        const sourceContext = data.source_context || {};
        const referencePack = sourceContext.reference_pack || null;
        if (referencePack || sourceContext.internet_grounded || sourceContext.repair_occurred) {
            const lines = [];
            lines.push(`<div class="verifier-summary"><strong>Internet grounded:</strong> ${sourceContext.internet_grounded ? 'yes' : 'no'}</div>`);
            lines.push(`<div class="verifier-summary"><strong>Repair occurred:</strong> ${sourceContext.repair_occurred ? 'yes' : 'no'}</div>`);
            if (referencePack) {
                lines.push(`<div class="verifier-summary"><strong>Reference pack:</strong> ${escapeHtml(referencePack.title || 'untitled')} (#${escapeHtml(referencePack.id || '--')})</div>`);
                lines.push(`<div class="verifier-summary"><strong>Family:</strong> ${escapeHtml(referencePack.prompt_family || '--')} · ${escapeHtml(referencePack.lane || '--')}</div>`);
                if (referencePack.task_definition) {
                    lines.push(`<div class="verifier-summary"><strong>Task definition:</strong> ${escapeHtml(referencePack.task_definition)}</div>`);
                }
            }
            provenanceEl.innerHTML = lines.join('');
            provenanceSection.style.display = 'block';
        } else {
            provenanceSection.style.display = 'none';
            provenanceEl.textContent = '';
        }
        renderRolePackets(data);
        renderComparisonPacket(data);

        const dims = ['novelty', 'surprise', 'value', 'elaboration', 'coherence'];
        const businessDims = ['actionability', 'brand_fit', 'factual_reliability'];
        const activeDims = businessDims.some(d => data[d] != null) ? dims.concat(businessDims) : dims;
        const primaryEvaluators = (data.role_packets?.evaluators || []).filter(packet => !packet.shadow_only && packet.role_id === 'muse');
        document.getElementById('modal-scores').innerHTML = renderEvaluatorCards(primaryEvaluators, activeDims);

        const holdoutEl = document.getElementById('modal-holdout');
        const nonMuseEvaluators = (data.role_packets?.evaluators || []).filter(packet => packet.role_id !== 'muse');
        if (nonMuseEvaluators.length > 0) {
            holdoutEl.innerHTML = renderEvaluatorCards(nonMuseEvaluators, activeDims);
            holdoutEl.style.display = 'grid';
        } else {
            holdoutEl.style.display = 'none';
        }

        const constraintEl = document.getElementById('modal-constraints');
        if (data.constraints_met != null) {
            let text = data.constraints_met ? '\u2705 Constraints met' : '\u274c Constraints violated';
            if (data.constraint_notes) text += '\n' + data.constraint_notes;
            constraintEl.textContent = text;
            constraintEl.style.display = 'block';
        } else {
            constraintEl.style.display = 'none';
        }

        document.getElementById('modal-artifact').textContent = data.artifact || data.artifact_content || '(no artifact)';
        document.getElementById('modal-critique').textContent = data.critique || '(no critique)';
        populateHumanReview(data.human_review);
        if (data.human_review?.updated_at) {
            setReviewStatus(`Saved review from ${data.human_review.updated_at}. You can update it anytime.`, 'saved');
        } else {
            document.getElementById('modal-review-status').style.display = 'none';
        }
        renderReviewComparison(data);
        setModelEvaluationVisibility(!!data.human_review);

        let trace = '';
        let parsedTrace = null;
        if (data.process_trace) {
            try {
                parsedTrace = typeof data.process_trace === 'string' ? JSON.parse(data.process_trace) : data.process_trace;
                trace = JSON.stringify(parsedTrace, null, 2);
            } catch { trace = data.process_trace; }
        }
        document.getElementById('modal-trace').textContent = trace || '(no trace)';

        const verifierSection = document.getElementById('modal-verifier-section');
        const verifierEl = document.getElementById('modal-verifier');
        const verifierStatus = parsedTrace?.verification_status;
        const verifierChecks = parsedTrace?.verifier_checks || [];
        const verifierInferred = parsedTrace?.verifier_inferred_constraints || [];
        const verifierFindings = parsedTrace?.verifier_findings || [];
        const verifierRepair = parsedTrace?.verifier_repair_summary || '';
        if (verifierStatus || verifierChecks.length || verifierInferred.length || verifierFindings.length) {
            const checksHtml = verifierChecks.length
                ? verifierChecks.map((check) => {
                    const marker = check.passed ? 'PASS' : 'FAIL';
                    const machine = check.machine_checked ? 'machine' : 'manual';
                    return `<div class="verifier-check"><strong>${marker}</strong> ${escapeHtml(check.constraint)} <span class="verifier-meta">(${machine})</span><div class="verifier-detail">${escapeHtml(check.detail || '')}</div></div>`;
                }).join('')
                : '<div class="analysis-empty">No verifier checks recorded.</div>';
            verifierEl.innerHTML = `
                <div class="verifier-summary"><strong>Status:</strong> ${escapeHtml(verifierStatus || 'not_run')}</div>
                <div class="verifier-summary"><strong>Inferred constraints:</strong> ${verifierInferred.length ? escapeHtml(verifierInferred.join(' | ')) : 'none'}</div>
                ${verifierFindings.length ? `<div class="verifier-summary"><strong>Findings:</strong> ${escapeHtml(verifierFindings.join(' | '))}</div>` : ''}
                ${verifierRepair ? `<div class="verifier-summary"><strong>Repair summary:</strong> ${escapeHtml(verifierRepair)}</div>` : ''}
                <div class="verifier-list">${checksHtml}</div>
            `;
            verifierSection.style.display = 'block';
        } else {
            verifierSection.style.display = 'none';
            verifierEl.textContent = '';
        }

        const errorSection = document.getElementById('modal-error-section');
        if (data.error_traceback) {
            document.getElementById('modal-error').textContent = data.error_traceback;
            errorSection.style.display = 'block';
        } else {
            errorSection.style.display = 'none';
        }

        document.getElementById('modal-overlay').classList.add('active');
    } catch (e) {
        console.error('Failed to load artifact:', e);
    }
}

async function saveHumanReview() {
    if (!currentArtifact?.id) return;
    const payload = {
        interesting: readReviewValue('review-interesting'),
        effective: readReviewValue('review-effective'),
        constraint_fit: readReviewValue('review-constraint-fit'),
        worth_saving: readReviewValue('review-worth-saving'),
        novelty: readReviewValue('review-novelty'),
        surprise: readReviewValue('review-surprise'),
        value: readReviewValue('review-value'),
        elaboration: readReviewValue('review-elaboration'),
        coherence: readReviewValue('review-coherence'),
        best_part: readReviewValue('review-best-part'),
        missed_opportunity: readReviewValue('review-missed-opportunity'),
        socratic_question: readReviewValue('review-socratic-question'),
    };

    if (!payload.interesting || !payload.effective || !payload.constraint_fit || !payload.worth_saving) {
        setReviewStatus('Fill in the four 1-5 human judgment fields before saving.', 'error');
        return;
    }

    try {
        const headers = buildAdminHeaders();
        if (!headers) {
            setReviewStatus('Admin token required to save review.', 'error');
            return;
        }
        const res = await fetch(`/api/artifact/${currentArtifact.id}/human-review`, {
            method: 'POST',
            headers,
            body: JSON.stringify(payload),
        }).then(r => r.json());

        if (res.error) {
            setReviewStatus(res.error, 'error');
            return;
        }

        currentArtifact.human_review = res.review;
        setReviewStatus('Human review saved. You can reveal the model evaluation now or keep editing.', 'saved');
        renderReviewComparison(currentArtifact);
        modelEvaluationRevealed = true;
        setModelEvaluationVisibility(true);
        refresh();
    } catch (e) {
        setReviewStatus('Failed to save review.', 'error');
        console.error('Failed to save review:', e);
    }
}

function closeModal(event) {
    if (event.target === document.getElementById('modal-overlay')) {
        document.getElementById('modal-overlay').classList.remove('active');
    }
}

async function startLab() {
    const batchInput = document.getElementById('batch-size');
    const nExperiments = batchInput ? Number(batchInput.value || 10) : 10;
    try {
        const headers = buildAdminHeaders();
        if (!headers) return;
        await fetch('/api/start', {
            method: 'POST',
            headers,
            body: JSON.stringify({ n_experiments: nExperiments }),
        });
        refresh();
    } catch (e) {
        console.error('Start failed:', e);
    }
}

async function stopLab() {
    try {
        const headers = buildAdminHeaders(false);
        if (!headers) return;
        await fetch('/api/stop', { method: 'POST', headers });
        refresh();
    } catch (e) { console.error('Stop failed:', e); }
}

async function runCustomExperiment() {
    const statusEl = document.getElementById('custom-runner-status');
    const prompt = document.getElementById('custom-prompt').value.trim();
    const constraints = document.getElementById('custom-constraints').value;

    if (!prompt) {
        statusEl.textContent = 'Prompt required.';
        return;
    }

    statusEl.textContent = 'Running custom experiment...';

    try {
        const headers = buildAdminHeaders();
        if (!headers) {
            statusEl.textContent = 'Admin token required to run a custom experiment.';
            return;
        }
        const res = await fetch('/api/experiment/custom', {
            method: 'POST',
            headers,
            body: JSON.stringify({
                lane: document.getElementById('custom-lane').value,
                track: document.getElementById('custom-track').value.trim() || 'custom',
                condition: document.getElementById('custom-condition').value,
                family: document.getElementById('custom-family').value.trim() || 'custom_operator',
                creativity_type: document.getElementById('custom-creativity-type').value.trim() || 'custom',
                hypothesis: document.getElementById('custom-hypothesis').value.trim(),
                prompt,
                constraints,
            }),
        });
        const data = await res.json();
        if (!res.ok) {
            statusEl.textContent = data.error || 'Custom experiment failed.';
            return;
        }
        statusEl.textContent = `Completed experiment #${data.experiment_id}.`;
        document.getElementById('custom-prompt').value = '';
        document.getElementById('custom-constraints').value = '';
        await refresh();
        if (data.experiment_id) {
            showArtifact(data.experiment_id);
        }
    } catch (e) {
        statusEl.textContent = 'Custom experiment failed.';
        console.error('Custom experiment failed:', e);
    }
}

function splitConstraintLines(raw) {
    return String(raw || '')
        .split('\n')
        .map(line => line.trim())
        .filter(Boolean);
}

async function runPairedExperiment() {
    const statusEl = document.getElementById('paired-runner-status');
    const prompt = document.getElementById('paired-prompt').value.trim();
    const theronArtifact = document.getElementById('paired-external-artifact').value.trim();
    const generateTheron = document.getElementById('paired-generate-external').checked;

    if (!prompt) {
        statusEl.textContent = 'Prompt required.';
        return;
    }
    if (generateTheron && theronArtifact) {
        statusEl.textContent = 'Choose one Theron source: generate it or paste it manually.';
        return;
    }

    statusEl.textContent = theronArtifact
        ? 'Running the packet and scoring both generators...'
        : 'Running the packet...';

    const payload = {
        lane: document.getElementById('paired-lane').value,
        track: document.getElementById('paired-track').value.trim() || 'paired',
        condition: document.getElementById('paired-condition').value,
        family: document.getElementById('paired-family').value.trim() || 'paired_operator',
        local_role_id: document.getElementById('paired-local-role').value.trim() || 'genesis',
        prompt,
        constraints: splitConstraintLines(document.getElementById('paired-constraints').value),
        external_artifacts: [],
        generate_external: generateTheron,
        external_role_id: document.getElementById('paired-external-role').value.trim() || 'theron',
        external_provider: document.getElementById('paired-external-provider').value.trim() || 'theron_manual',
        external_generation_protocol: document.getElementById('paired-external-protocol').value.trim() || 'theron_paired_native',
    };

    if (theronArtifact) {
        payload.external_artifacts.push({
            artifact: theronArtifact,
            generator_role_id: document.getElementById('paired-external-role').value.trim() || 'theron',
            generator_provider: document.getElementById('paired-external-provider').value.trim() || 'theron_manual',
            generation_protocol: document.getElementById('paired-external-protocol').value.trim() || 'paired_external_manual',
            process_trace: {
                protocol: document.getElementById('paired-external-protocol').value.trim() || 'paired_external_manual',
                artifact_contract_status: 'ok',
                submission_mode: 'paired_ui',
            },
            source_context: {
                external_submission: true,
                submission_mode: 'paired_ui',
                generator_role_id: document.getElementById('paired-external-role').value.trim() || 'theron',
                generator_provider: document.getElementById('paired-external-provider').value.trim() || 'theron_manual',
            },
        });
    }

    try {
        const headers = buildAdminHeaders();
        if (!headers) {
            statusEl.textContent = 'Admin token required to run a paired packet.';
            return;
        }
        const res = await fetch('/api/experiment/paired', {
            method: 'POST',
            headers,
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) {
            statusEl.textContent = data.error || 'Paired packet failed.';
            return;
        }

        statusEl.textContent = `Completed packet ${data.packet_id} with ${data.results?.length || 0} member(s).`;
        document.getElementById('paired-prompt').value = '';
        document.getElementById('paired-constraints').value = '';
        document.getElementById('paired-external-artifact').value = '';
        document.getElementById('paired-generate-external').checked = false;
        syncTheronSubmissionMode();
        await refresh();
        if (data.packet_id) {
            await showReviewPacket(data.packet_id);
        }
    } catch (e) {
        statusEl.textContent = 'Paired packet failed.';
        console.error('Paired packet failed:', e);
    }
}

async function runCompilerCompare() {
    const statusEl = document.getElementById('paired-runner-status');
    const prompt = document.getElementById('paired-prompt').value.trim();

    if (!prompt) {
        statusEl.textContent = 'Prompt required.';
        return;
    }

    statusEl.textContent = 'Running raw vs compiled prompt comparison...';

    const payload = {
        lane: document.getElementById('paired-lane').value,
        track: 'compiler_compare',
        condition: document.getElementById('paired-condition').value,
        family: document.getElementById('paired-family').value.trim() || 'custom_operator',
        local_role_id: document.getElementById('paired-local-role').value.trim() || 'genesis',
        prompt,
        constraints: splitConstraintLines(document.getElementById('paired-constraints').value),
    };

    try {
        const headers = buildAdminHeaders();
        if (!headers) {
            statusEl.textContent = 'Admin token required to run compiler comparison.';
            return;
        }
        const res = await fetch('/api/experiment/compiler-compare', {
            method: 'POST',
            headers,
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) {
            statusEl.textContent = data.error || 'Compiler comparison failed.';
            return;
        }

        statusEl.textContent = `Completed compiler packet ${data.packet_id}.`;
        await refresh();
        if (data.packet_id) {
            await showReviewPacket(data.packet_id);
        }
    } catch (e) {
        statusEl.textContent = 'Compiler comparison failed.';
        console.error('Compiler comparison failed:', e);
    }
}

async function triggerCouncil() {
    try {
        const headers = buildAdminHeaders(false);
        if (!headers) return;
        const res = await fetch('/api/council/trigger', { method: 'POST', headers }).then(r => r.json());
        currentCouncilSession = normalizeCouncilSession(res);
        currentCouncilHistory = currentCouncilSession ? [{ id: currentCouncilSession.council_id || currentCouncilSession.session_number, created_at: currentCouncilSession.created_at, payload: res }] : currentCouncilHistory;
        updateCouncilSurface(currentCouncilHistory.map(entry => entry.payload ? entry : { payload: entry }));
        if (res.research_memo || res.recommendation) {
            showCouncilModal(res);
        } else {
            alert('Council: ' + JSON.stringify(res));
        }
    } catch (e) { console.error('Council failed:', e); }
}

function renderCouncilList(items, formatter) {
    if (!Array.isArray(items) || items.length === 0) return '--';
    return `<ul>${items.map(item => `<li>${formatter(item)}</li>`).join('')}</ul>`;
}

function findCouncilAction(actionType, title) {
    return currentCouncilActions.find(row => row.action_type === actionType && row.title === title) || null;
}

function councilActionStatusLabel(action) {
    if (!action) return '';
    const label = action.status || 'saved';
    return `<span class="council-action-status">${escapeHtml(label)}</span>`;
}

function renderCouncilActionList(actionType, items, formatter) {
    if (!Array.isArray(items) || items.length === 0) return '--';
    return `<ul class="council-action-list">${items.map((item, index) => {
        const action = findCouncilAction(actionType, item.title);
        const buttonLabel = actionType === 'prompt_diagnosis_refinement'
            ? 'Adopt'
            : actionType === 'evaluator_education_target'
                ? 'Activate'
                : 'Queue';
        const button = action
            ? councilActionStatusLabel(action)
            : `<button class="btn-refresh council-inline-action" onclick="applyCouncilAction('${actionType}', ${index})">${buttonLabel}</button>`;
        return `<li class="council-action-row"><div class="council-action-copy">${formatter(item)}</div>${button}</li>`;
    }).join('')}</ul>`;
}

async function applyCouncilAction(actionType, index) {
    if (!currentCouncilSession) return;
    const headers = buildAdminHeaders(true);
    if (!headers) return;
    const sourceKey = actionType === 'prompt_diagnosis_refinement'
        ? 'prompt_diagnosis_recommendations'
        : actionType === 'evaluator_education_target'
            ? 'evaluator_education_recommendations'
            : 'contrast_set_candidates';
    const item = (currentCouncilSession[sourceKey] || [])[index];
    if (!item) return;
    const status = actionType === 'prompt_diagnosis_refinement'
        ? 'adopted'
        : actionType === 'evaluator_education_target'
            ? 'active'
            : 'queued';
    const res = await fetch('/api/council/actions', {
        method: 'POST',
        headers,
        body: JSON.stringify({
            council_id: currentCouncilSession.council_id || currentCouncilSession.id || null,
            action_type: actionType,
            title: item.title,
            status,
            payload: item,
        }),
    }).then(r => r.json());
    if (res?.action) {
        await refresh();
        showCouncilModal(currentCouncilSession);
    } else if (res?.error) {
        alert(`Council action failed: ${res.error}`);
    }
}

function showCouncilModal(data) {
    document.getElementById('council-modal-title').textContent = `Lab Research Council${data.session_number ? ' #' + data.session_number : ''}`;
    document.getElementById('council-modal-meta').textContent =
        `${data.confidence_level || '--'} confidence${data.confidence_reason ? ' · ' + data.confidence_reason : ''}`;
    document.getElementById('council-confidence').textContent = data.confidence_level || '--';
    document.getElementById('council-strongest').textContent = data.strongest_supported_finding || '--';
    document.getElementById('council-recommendation').textContent = data.recommendation || '--';
    document.getElementById('council-next').textContent = data.one_experiment_to_run_next || '--';
    document.getElementById('council-stop').textContent = data.one_thing_to_stop_doing || '--';
    document.getElementById('council-evaluator').textContent = data.evaluator_trust_assessment || '--';
    document.getElementById('council-prompt-diagnosis').textContent = data.prompt_diagnosis_assessment || '--';
    document.getElementById('council-evaluator-education').textContent = data.evaluator_education_assessment || '--';
    document.getElementById('council-prompt-recommendations').innerHTML = renderCouncilActionList(
        'prompt_diagnosis_refinement',
        data.prompt_diagnosis_recommendations,
        item => `<strong>${escapeHtml(item.title || 'Untitled')}</strong>: ${escapeHtml(item.action || item.reason || '')}`
    );
    document.getElementById('council-evaluator-recommendations').innerHTML = renderCouncilActionList(
        'evaluator_education_target',
        data.evaluator_education_recommendations,
        item => `<strong>${escapeHtml(item.title || 'Untitled')}</strong>: ${escapeHtml(item.action || item.reason || '')}`
    );
    document.getElementById('council-contrast-candidates').innerHTML = renderCouncilActionList(
        'contrast_set_candidate',
        data.contrast_set_candidates,
        item => `<strong>${escapeHtml(item.title || 'Untitled')}</strong>: ${escapeHtml(item.why_now || item.focus || '')}`
    );
    document.getElementById('council-protocol').textContent = data.protocol_assessment || '--';
    document.getElementById('council-memo').textContent = data.research_memo || '--';
    document.getElementById('council-modal-overlay').classList.add('active');
}

function closeCouncilModal(event) {
    if (event.target === document.getElementById('council-modal-overlay')) {
        document.getElementById('council-modal-overlay').classList.remove('active');
    }
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        document.getElementById('modal-overlay').classList.remove('active');
        document.getElementById('council-modal-overlay').classList.remove('active');
        document.getElementById('packet-review-overlay').classList.remove('active');
    }
});

// ── Design Instrument Motion & Render ────────────────────────────────────────

let designLoopStateIndex = 0;
const DESIGN_LOOP_STATES = [
    { active: [],     legend: 'Runner idle. Awaiting next experiment.' },
    { active: [0],    legend: 'Genesis generating artifact…' },
    { active: [0, 1], legend: 'Theron generating paired artifact…' },
    { active: [2],    legend: 'Muse evaluating both artifacts…' },
    { active: [3],    legend: 'Athena evaluating both artifacts…' },
    { active: [4],    legend: 'Apollo evaluating both artifacts…' },
    { active: [],     legend: 'Packet complete. Awaiting human review.' },
];

function initDesignMotion() {
    // UTC clock tick every 1 s
    function tickClock() {
        const now = new Date();
        const hh = String(now.getUTCHours()).padStart(2, '0');
        const mm = String(now.getUTCMinutes()).padStart(2, '0');
        const ss = String(now.getUTCSeconds()).padStart(2, '0');
        const t = `${hh}:${mm}:${ss} UTC`;
        const cl = document.getElementById('design-snap-clock');
        if (cl) cl.textContent = t;
        const cf = document.getElementById('design-snap-clock-foot');
        if (cf) cf.textContent = t;
    }
    tickClock();
    setInterval(tickClock, 1000);

    // Last-packet-ago display every 30 s
    function updateAgoDisplay() {
        const ago = lastPacketAt ? formatAgoShort(lastPacketAt) : '—';
        const a1 = document.getElementById('design-last-packet-ago');
        if (a1) a1.textContent = ago;
        const a2 = document.getElementById('design-trace-last');
        if (a2) a2.textContent = ago;
    }
    updateAgoDisplay();
    setInterval(updateAgoDisplay, 30000);

    // Loop-state cadence every 9 s (cosmetic when idle; runner state overrides)
    setInterval(() => {
        designLoopStateIndex = (designLoopStateIndex + 1) % DESIGN_LOOP_STATES.length;
    }, 9000);
}

function formatAgoShort(date) {
    if (!date) return '—';
    const sec = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
    if (sec < 60) return `${sec}s`;
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}h`;
    return `${Math.floor(hr / 24)}d`;
}

function renderDesignLoopState(isRunning) {
    const track = document.getElementById('design-agent-track');
    const legendEl = document.getElementById('design-loop-legend');
    if (!track) return;
    const cells = Array.from(track.querySelectorAll('.cell'));
    if (!isRunning) {
        cells.forEach(c => c.classList.remove('active'));
        if (legendEl) legendEl.textContent = 'Runner idle. Last packet filed and awaiting human review.';
        return;
    }
    const state = DESIGN_LOOP_STATES[designLoopStateIndex % DESIGN_LOOP_STATES.length];
    cells.forEach((c, i) => c.classList.toggle('active', state.active.includes(i)));
    if (legendEl) legendEl.textContent = state.legend;
}

function updateDesignRunnerState(isRunning) {
    const stateEl = document.getElementById('design-runner-state');
    const labelEl = document.getElementById('design-runner-label');
    if (stateEl) {
        stateEl.classList.toggle('idle', !isRunning);
        stateEl.classList.toggle('running', !!isRunning);
    }
    if (labelEl) labelEl.textContent = isRunning ? 'Runner · running' : 'Runner · idle';
    renderDesignLoopState(isRunning);
}

function updateDesignCompilerLearning(report) {
    const proposals = Array.isArray(report?.proposals) ? report.proposals : [];
    const charLabels = ['aligned', 'llm_specific', 'divergent', 'human_specific', 'insufficient_data'];
    const counts = Object.fromEntries(charLabels.map(l => [l, 0]));
    let totalEligible = 0;
    let totalHuman = 0;
    let totalSuppressed = 0;

    for (const p of proposals) {
        const lbl = p.characterization || 'insufficient_data';
        counts[lbl] = (counts[lbl] || 0) + 1;
        const m = p.metrics || {};
        totalEligible += m.eligible_slices ?? m.total_slices ?? 0;
        totalHuman += m.human_decisive || 0;
        totalSuppressed += m.suppressed_dual_constraint_fail || 0;
    }
    const characterized = proposals.filter(
        p => p.characterization && p.characterization !== 'insufficient_data'
    ).length;

    // Ledger cells
    for (const lbl of charLabels) {
        const cell = document.getElementById(`design-ledger-${lbl}`);
        if (!cell) continue;
        const numEl = cell.querySelector('.num');
        if (numEl) {
            numEl.classList.toggle('dim', counts[lbl] === 0);
            numEl.innerHTML = `${counts[lbl]}<span class="of"> / ${proposals.length}</span>`;
        }
    }

    // Filemeta row
    const _st = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val; };
    const mode = report?.mode || 'dry-run (proposals only)';
    _st('design-fm-mode', mode);
    _st('design-fm-rules-tracked', proposals.length);
    _st('design-fm-decisive-human', totalHuman);
    _st('design-fm-characterized', `${characterized} / ${proposals.length}`);

    // § I.a claim headline
    const claimEl = document.getElementById('design-cl-claim');
    if (claimEl) {
        if (!proposals.length) {
            claimEl.innerHTML = '<strong>No rule evidence on record.</strong> Run compiler-compare packets to begin accumulating signal.';
        } else {
            const promotions = proposals.filter(p => p.recommendation === 'promote').length;
            const watches = proposals.filter(p => p.recommendation === 'watch').length;
            claimEl.innerHTML = promotions
                ? `<strong>${promotions} rule${promotions === 1 ? '' : 's'} eligible for promotion.</strong> ${watches} under watch. ${totalHuman} decisive human reviews on record.`
                : `<strong>${proposals.length} rule${proposals.length === 1 ? '' : 's'} under evaluation.</strong> ${watches} under watch. Awaiting decisive human signal before any promotion.`;
        }
    }

    // § III.a empirical state
    _st('design-stat-rules', proposals.length);
    const statPkEl = document.getElementById('design-stat-packets');
    if (statPkEl) statPkEl.textContent = (report?.total_packets ?? totalEligible) || '—';
    _st('design-stat-eligible', totalEligible || '—');
    _st('design-stat-families', report?.support_families ?? '—');
    _st('design-stat-human', totalHuman);
    _st('design-stat-characterized', `${characterized} / ${proposals.length}`);
    _st('design-stat-mode', mode);

    // Trace strip packet count
    _st('design-trace-n', totalEligible || '—');

    // Thresholds — only rewrite if the server sends threshold data
    const thresh = report?.thresholds || {};
    if (Object.keys(thresh).length) {
        const threshEl = document.getElementById('design-cl-thresh-v');
        if (threshEl) {
            const parts = [];
            if (thresh.characterization_min_human != null) {
                parts.push(`<span>characterization_min_human <b>= ${thresh.characterization_min_human}</b></span>`);
            }
            const famMin = thresh.support_families_min ?? thresh.provisional_families;
            if (famMin != null) parts.push(`<span>support_families_min <b>= ${famMin}</b></span>`);
            const pkMin = thresh.support_packets_min ?? thresh.provisional_packets;
            if (pkMin != null) parts.push(`<span>support_packets_min <b>= ${pkMin}</b></span>`);
            if (thresh.promote_human_win_rate != null) {
                parts.push(`<span>promote_human_win_rate <b>≥ ${Number(thresh.promote_human_win_rate).toFixed(2)}</b></span>`);
            }
            parts.push(`<span>suppress dual constraint-fail <b>= true</b></span>`);
            threshEl.innerHTML = parts.join('');
        }
    }

    // Stability: suppression rate bar
    const suppBar = document.getElementById('design-stability-suppression');
    if (suppBar) {
        const fill = suppBar.querySelector('.fill');
        const pct = totalEligible > 0 ? Math.min(100, Math.round((totalSuppressed / totalEligible) * 100)) : 0;
        if (fill) fill.style.width = `${pct}%`;
    }
    _st('design-stability-suppression-v', `${totalSuppressed} / ${totalEligible || '—'}`);

    // Stability: human coverage bar
    const humanFill = document.getElementById('design-stability-human-fill');
    if (humanFill) {
        const pct = totalEligible > 0 ? Math.min(100, Math.round((totalHuman / totalEligible) * 100)) : 0;
        humanFill.style.width = `${pct}%`;
    }
    _st('design-stability-human-v', `${totalHuman} / ${totalEligible || '—'}`);

    // Proposals table body
    const bodyEl = document.getElementById('design-proposals-body');
    if (!bodyEl) return;

    if (!proposals.length) {
        bodyEl.innerHTML = '<div class="q-empty">No rules under evaluation yet. Run compiler-compare packets to accumulate signal.</div>';
        return;
    }

    bodyEl.innerHTML = proposals.map(item => {
        const m = item.metrics || {};
        const rec = item.recommendation || 'hold';
        const charLabel = item.characterization || 'insufficient_data';
        const eligibleSlices = m.eligible_slices ?? m.total_slices ?? 0;
        const evalHelped = m.evaluator_helped ?? 0;
        const panelSupport = eligibleSlices ? `${evalHelped} / ${eligibleSlices}` : '—';
        const winRate = m.human_win_rate != null ? `${Number(m.human_win_rate).toFixed(2)} wr` : '—';
        const humanDecisive = m.human_decisive || 0;
        const humanNote = humanDecisive ? `${humanDecisive} decisive · ${winRate}` : 'no decisive reviews';
        const status = item.current_status || 'candidate';
        const provenance = item.proposed_status && rec === 'promote'
            ? `${status} → ${item.proposed_status}`
            : status;
        // .rec class goes directly on the first column div so CSS can target .rec.promote etc.
        const recText = rec === 'promote' ? '↑ promote' : rec === 'watch' ? '○ watch' : '— hold';
        return `
            <div class="proposals-row rule-characterization-${escapeHtml(charLabel)}" role="row">
                <div class="rec ${escapeHtml(rec)}"><span class="tag">${escapeHtml(recText)}</span></div>
                <div class="rule-id">${escapeHtml(item.title || item.rule_key || 'untitled')}</div>
                <div class="char">${escapeHtml(charLabel.replaceAll('_', '\u200b_'))}</div>
                <div class="evidence">${escapeHtml(panelSupport)}</div>
                <div class="human">${escapeHtml(humanNote)}</div>
                <div class="provenance">${escapeHtml(provenance)}</div>
            </div>
        `;
    }).join('');
}

function updateDesignQueue(data) {
    const countEl = document.getElementById('design-queue-count-n');
    const listEl = document.getElementById('design-queue-list');
    if (!listEl) return;

    const rows = Array.isArray(data?.rows) ? data.rows : [];
    if (countEl) countEl.textContent = rows.length;

    if (!rows.length) {
        listEl.innerHTML = '<div class="q-empty">Queue is clear — no packets awaiting decisive human review.</div>';
        return;
    }

    listEl.innerHTML = rows.map((row, index) => {
        const lane = row.lane || 'creative';
        const family = (row.family || 'unclassified').replaceAll('_', ' ');
        const prompt = truncateMiddle(
            row.prompt || row.members?.[0]?.artifact_preview || 'Packet awaiting review.',
            200
        );
        const preferred = Array.isArray(row.judge_preferences)
            ? row.judge_preferences.map(s => {
                const winner = s.winner_experiment_id ? `#${s.winner_experiment_id}` : 'split';
                return `${formatRoleLabel(s.judge)} → ${winner}`;
            }).join(' · ')
            : '—';
        const queueHeadline = !row.has_review_ready_panel && (row.missing_judges || []).length
            ? `Panel incomplete · missing ${row.missing_judges.map(formatRoleLabel).join(', ')}`
            : row.has_noticeable_disagreement
                ? (row.has_complete_panel
                    ? 'Panel diverged'
                    : `Panel diverged · missing ${(row.missing_judges || []).map(formatRoleLabel).join(', ') || 'third judge'}`)
                : 'Panel broadly agrees';
        const marginNote = row.judge_preferences?.[0]?.margin != null
            ? ` · Δ ${row.judge_preferences[0].margin.toFixed(2)}`
            : '';
        return `
            <div class="q-item">
                <div class="q-prompt">
                    <span class="lane-badge ${escapeHtml(lane)}">${escapeHtml(lane)}</span>
                    <span class="q-family">${escapeHtml(family)}</span>
                    <span class="q-text">${escapeHtml(prompt)}</span>
                </div>
                <div class="q-split">${escapeHtml(preferred)}</div>
                <div class="q-disagreement">${escapeHtml(queueHeadline + marginNote)}</div>
                <div class="q-actions-btn">
                    <button class="btn" onclick="openReviewQueueItem(${index})">Judge →</button>
                </div>
            </div>
        `;
    }).join('');
}
