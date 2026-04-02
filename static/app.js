let scoreChart = null;
let pollInterval = null;
let currentArtifact = null;
let modelEvaluationRevealed = false;
const ADMIN_TOKEN_STORAGE_KEY = 'labAdminToken';

document.addEventListener('DOMContentLoaded', () => {
    initChart();
    refresh();
    startPolling();
});

function startPolling() {
    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(refresh, 4000);
}

async function refresh() {
    try {
        const [stateRes, historyRes, timelineRes, analysisRes] = await Promise.all([
            fetch('/api/state').then(r => r.json()),
            fetch('/api/history').then(r => r.json()),
            fetch('/api/timeline').then(r => r.json()),
            fetch('/api/analysis').then(r => r.json()),
        ]);
        updateStats(stateRes);
        updateDimensions(stateRes.best_scores);
        updateTrends(stateRes.trends);
        updateState(stateRes.state);
        updateAnalysis(analysisRes);
        updateHistory(historyRes);
        updateChart(timelineRes);
    } catch (e) {
        console.error('Refresh failed:', e);
    }
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
        html += `<br><span class="state-key">MUSE-HERMES \u0394: </span><span class="state-val">${trends.muse_critic_divergence.toFixed(2)}</span>`;
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
    const headline = data?.headline;
    const lanes = data?.lane_summaries || [];
    if (!headline && lanes.length === 0) {
        el.innerHTML = '<div class="analysis-empty">Not enough data yet.</div>';
        return;
    }
    const laneHtml = lanes.map(row => `
        <div class="analysis-summary-line">
            <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
            <span>${row.performance_takeaway}. Tilt read: ${row.takeaway}. ${row.creativity_led} creativity-led, ${row.counterpart_led} ${row.counterpart_label}-led, ${row.balanced} balanced.</span>
        </div>
    `).join('');
    el.innerHTML = `
        <div class="analysis-summary-headline">${headline || ''}</div>
        ${laneHtml || '<div class="analysis-empty">Not enough lane detail yet.</div>'}
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
    ].filter(([, value]) => value);

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
            <div class="analysis-main">${row.hypothesis_id || 'no hypothesis'}</div>
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
                <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
            </div>
            <div class="analysis-main">${row.hypothesis_id || 'no hypothesis'}</div>
            <div class="analysis-sub">${truncateMiddle(row.hypothesis_description || '', 88)}</div>
            <div class="analysis-metrics">
                <span>score ${row.mean_composite?.toFixed(2) || '--'}</span>
                <span>shadow ${formatPct(row.shadow_rate)}</span>
                <span>&Delta; ${row.mean_divergence?.toFixed(2) || '--'}</span>
                <span>n=${row.trials || 0}</span>
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
                    <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
                </div>
                <div class="analysis-main">${row.hypothesis_id || 'no hypothesis'}</div>
                <div class="analysis-sub">${truncateMiddle(row.prompt || '', 88)}</div>
                <div class="analysis-metrics">
                    <span>creativity ${row.creativity_mean?.toFixed(2) || '--'}</span>
                    <span>${counterpart} ${row.counterpart_mean?.toFixed(2) || '--'}</span>
                    <span class="${gapClass}">gap ${signed(row.balance_gap)}</span>
                </div>
                <div class="analysis-note">
                    ${balanceLabel}. Composite ${row.mean_composite?.toFixed(2) || '--'} with n=${row.trials || 0}.
                </div>
            </div>
        `;
    });
}

function renderPaired(rows) {
    const el = document.getElementById('analysis-paired');
    const ranked = rows
        .filter(row => row.composite_delta != null)
        .sort((a, b) => (b.composite_delta || 0) - (a.composite_delta || 0))
        .slice(0, 6);
    el.innerHTML = renderMetricList(ranked, row => `
        <div class="analysis-item">
            <div class="analysis-head">
                <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
            </div>
            <div class="analysis-main">${row.hypothesis_id || 'no hypothesis'}</div>
            <div class="analysis-sub">${truncateMiddle(row.prompt || '', 88)}</div>
            <div class="analysis-metrics">
                <span>w/ critique ${row.critique_on_mean?.toFixed(2) || '--'}</span>
                <span>w/o ${row.critique_off_mean?.toFixed(2) || '--'}</span>
                <span class="${(row.composite_delta || 0) >= 0 ? 'metric-up' : 'metric-down'}">delta ${signed(row.composite_delta)}</span>
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
            <div class="analysis-main">${row.hypothesis_id || 'no hypothesis'}</div>
            <div class="analysis-sub">${truncateMiddle(row.prompt || '', 88)}</div>
            <div class="analysis-metrics">
                <span>novelty ${row.mean_novelty?.toFixed(2) || '--'}</span>
                <span>utility ${row.utility_mean?.toFixed(2) || '--'}</span>
                <span class="${(row.creativity_tax || 0) > 0 ? 'metric-down' : 'metric-up'}">tax ${signed(row.creativity_tax)}</span>
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
                <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
            </div>
            <div class="analysis-main">${row.hypothesis_id || 'no hypothesis'}</div>
            <div class="analysis-sub">${truncateMiddle(row.prompt || '', 88)}</div>
            <div class="analysis-metrics">
                <span>score ${row.mean_composite?.toFixed(2) || '--'}</span>
                <span>shadow ${formatPct(row.shadow_rate)}</span>
                <span>n=${row.trials || 0}</span>
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
        `validated ${overview.approved_validated || 0}`,
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
    if (!data || !data.sample_size) {
        el.innerHTML = '<div class="analysis-empty">Not enough data yet.</div>';
        return;
    }

    const warnings = (data.warnings || []).slice(0, 3).map(text => `
        <div class="analysis-item">
            <div class="analysis-main">Evaluator Risk</div>
            <div class="analysis-sub">${text}</div>
        </div>
    `).join('');

    const overall = data.overall || {};
    const topPairs = (overall.pairwise || [])
        .filter(row => row.correlation != null)
        .sort((a, b) => Math.abs(b.correlation || 0) - Math.abs(a.correlation || 0))
        .slice(0, 3)
        .map(row => `${row.left}/${row.right} ${signed(row.correlation)}`)
        .join(' · ');

    const repeatability = (data.repeatability || [])[0];
    const baseline = (data.baseline_stability || [])[0];
    const agreement = data.muse_critic_agreement || {};

    el.innerHTML = `
        <div class="analysis-item">
            <div class="analysis-main">Halo Check</div>
            <div class="analysis-sub">Mean absolute dimension correlation: ${overall.halo_index != null ? overall.halo_index.toFixed(2) : '--'} across n=${data.sample_size} scored runs.</div>
            <div class="analysis-metrics">
                <span>top pairs ${topPairs || '--'}</span>
            </div>
        </div>
        <div class="analysis-item">
            <div class="analysis-main">Repeatability</div>
            <div class="analysis-sub">${repeatability ? truncateMiddle(repeatability.prompt || '', 84) : 'No repeated prompt/condition pairs yet.'}</div>
            <div class="analysis-metrics">
                <span>range ${repeatability ? signed(repeatability.composite_range).replace('+', '') : '--'}</span>
                <span>std ${repeatability ? repeatability.composite_stddev.toFixed(2) : '--'}</span>
                <span>${repeatability ? `n=${repeatability.trials}` : ''}</span>
            </div>
        </div>
        <div class="analysis-item">
            <div class="analysis-main">Baseline Stability</div>
            <div class="analysis-sub">${baseline ? truncateMiddle(baseline.prompt || '', 84) : 'No baseline canary data yet.'}</div>
            <div class="analysis-metrics">
                <span>range ${baseline ? signed(baseline.composite_range).replace('+', '') : '--'}</span>
                <span>std ${baseline ? baseline.composite_stddev.toFixed(2) : '--'}</span>
                <span>${baseline ? `n=${baseline.trials}` : ''}</span>
            </div>
        </div>
        <div class="analysis-item">
            <div class="analysis-main">MUSE / HERMES Agreement</div>
            <div class="analysis-sub">Mean composite divergence ${agreement.mean_divergence != null ? agreement.mean_divergence.toFixed(2) : '--'} across ${agreement.paired_trials || 0} paired evaluations.</div>
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
                <span>branch ${formatPct(overview.branch_fallback_rate)}</span>
                <span>selection ${formatPct(overview.selection_fallback_rate)}</span>
                <span>interlocutor ${formatPct(overview.interlocutor_fallback_rate)}</span>
                <span>revision parse ${formatPct(overview.revision_parse_failure_rate)}</span>
                <span>HERMES skip ${formatPct(overview.hermes_skip_rate)}</span>
                <span>forced HERMES ${formatPct(overview.hermes_forced_rate)}</span>
            </div>
            <div class="analysis-sub">${protocolVersions || 'No protocol version split yet.'}</div>
        </div>
        ${rows.slice(0, 6).map(row => `
            <div class="analysis-item">
                <div class="analysis-head">
                    <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                    <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
                    <span class="analysis-kicker">n=${row.tracked_runs || 0}</span>
                </div>
                <div class="analysis-metrics">
                    <span>branch ${formatPct(row.branch_fallback_rate)}</span>
                    <span>selection ${formatPct(row.selection_fallback_rate)}</span>
                    <span>interlocutor ${formatPct(row.interlocutor_fallback_rate)}</span>
                    <span>repair ${formatPct(row.verifier_repair_rate)}</span>
                    <span>skip ${formatPct(row.hermes_skip_rate)}</span>
                    <span>forced ${formatPct(row.hermes_forced_rate)}</span>
                </div>
            </div>
        `).join('') || '<div class="analysis-empty">No family-level reliability slices yet.</div>'}
    `;
}

function renderHumanCalibration(data) {
    const el = document.getElementById('analysis-human-calibration');
    if (!data || !data.sample_size) {
        el.innerHTML = '<div class="analysis-empty">No human reviews yet.</div>';
        return;
    }

    const summary = data.summary || {};
    const lanes = summary.lane_summaries || [];
    const laneHtml = lanes.map(row => {
        const deltas = row.dimension_deltas || {};
        const ranked = ['novelty', 'surprise', 'value', 'elaboration', 'coherence']
            .filter(dim => deltas[dim] != null)
            .map(dim => `${dim} ${signed(deltas[dim])}`)
            .join(' · ');
        return `
            <div class="analysis-item">
                <div class="analysis-head">
                    <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                    <span class="analysis-kicker">n=${row.sample_size}</span>
                </div>
                <div class="analysis-main">Fast-pass ${row.mean_fastpass?.toFixed(2) || '--'} / 5</div>
                <div class="analysis-sub">MUSE ${row.mean_muse_composite?.toFixed(2) || '--'}${row.mean_hermes_composite != null ? ` · HERMES ${row.mean_hermes_composite.toFixed(2)}` : ''}</div>
                <div class="analysis-metrics">
                    <span>${ranked || 'No direct human-vs-MUSE dimension overlap yet.'}</span>
                </div>
            </div>
        `;
    }).join('');

    const recentRows = (data.rows || []).slice(0, 4).map(row => {
        const ranked = ['novelty', 'surprise', 'value', 'elaboration', 'coherence']
            .map(dim => ({ dim, val: row[`delta_${dim}`] }))
            .filter(item => item.val != null)
            .sort((a, b) => Math.abs(b.val) - Math.abs(a.val))
            .slice(0, 2)
            .map(item => `${item.dim} ${signed(item.val)}`)
            .join(' · ');
        return `
            <div class="analysis-item">
                <div class="analysis-head">
                    <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                    <span class="analysis-kicker">#${row.experiment_id}</span>
                </div>
                <div class="analysis-sub">${truncateMiddle(row.prompt || '', 88)}</div>
                <div class="analysis-metrics">
                    <span>${ranked || 'No dimension deltas recorded.'}</span>
                    <span>MUSE ${row.muse_composite?.toFixed(2) || '--'}</span>
                    <span>${row.hermes_composite != null ? `HERMES ${row.hermes_composite.toFixed(2)}` : ''}</span>
                </div>
            </div>
        `;
    }).join('');

    el.innerHTML = `
        <div class="analysis-summary-headline">${summary.headline || 'Human calibration in progress.'}</div>
        ${laneHtml || '<div class="analysis-empty">No lane summaries yet.</div>'}
        ${recentRows || '<div class="analysis-empty">No reviewed artifacts yet.</div>'}
    `;
}

function renderConstraintVerifier(data) {
    const el = document.getElementById('analysis-constraint-verifier');
    if (!data || !data.sample_size) {
        el.innerHTML = '<div class="analysis-empty">No verifier data yet.</div>';
        return;
    }

    const summary = data.summary || {};
    const totals = summary.totals || {};
    const familyRows = (summary.families || []).map(row => `
        <div class="analysis-item">
            <div class="analysis-head">
                <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
                <span class="analysis-kicker">n=${row.tracked_runs || 0}</span>
            </div>
            <div class="analysis-sub">
                machine-checked ${row.machine_checked_runs || 0} · repaired ${row.passed_after_repair || 0} · failed ${row.constraint_fails || 0}
            </div>
        </div>
    `).join('');

    el.innerHTML = `
        <div class="analysis-summary-headline">${summary.headline || 'Verifier tracking in progress.'}</div>
        <div class="analysis-item">
            <div class="analysis-main">Verifier Totals</div>
            <div class="analysis-metrics">
                <span>tracked ${totals.tracked_runs || 0}</span>
                <span>machine-checked ${totals.machine_checked_runs || 0}</span>
                <span>rescued ${totals.passed_after_repair || 0}</span>
                <span>constraint fail ${formatPct(totals.constraint_fail_rate)}</span>
            </div>
        </div>
        ${familyRows || '<div class="analysis-empty">No family-level verifier data yet.</div>'}
    `;
}

function renderCalibrationMetrics(data) {
    const el = document.getElementById('analysis-calibration-metrics');
    if (!el) return;
    if (!data || !data.overview || !data.families) {
        el.innerHTML = '<div class="analysis-empty">No calibration metrics yet.</div>';
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
                <span>repair ${formatPct(row.constraint_recovery_rate)}</span>
                <span>critique-help ${formatPct(row.critique_help_rate)}</span>
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
                <span>repair ${formatPct(overview.constraint_recovery_rate)}</span>
                <span>unknown constraints ${formatPct(overview.unknown_constraint_rate)}</span>
                <span>critique-help ${formatPct(overview.critique_help_rate)}</span>
                <span>gap ${signed(overview.mean_novelty_gap)}</span>
                <span>human agreement ${formatPct(overview.human_agreement_rate)}</span>
            </div>
        </div>
        ${familyRows || '<div class="analysis-empty">Not enough family-level calibration data yet.</div>'}
    `;
}

function renderDisagreementQueue(data) {
    const el = document.getElementById('analysis-disagreement-queue');
    if (!el) return;
    const rows = data.rows || [];
    if (!rows.length) {
        el.innerHTML = '<div class="analysis-empty">No disagreement cases queued yet.</div>';
        return;
    }
    el.innerHTML = `
        <div class="analysis-summary-headline">${data.headline || 'Human review queue in progress.'}</div>
        ${rows.slice(0, 6).map(row => `
            <div class="analysis-item">
                <div class="analysis-head">
                    <span class="lane-badge ${row.lane || 'creative'}">${row.lane || 'unknown'}</span>
                    <span class="analysis-kicker">${row.prompt_family || 'unclassified'}</span>
                    <span class="analysis-kicker">#${row.experiment_id}</span>
                </div>
                <div class="analysis-sub">${truncateMiddle(row.prompt || '', 96)}</div>
                <div class="analysis-metrics">
                    ${row.reasons.map(reason => `<span>${escapeHtml(reason)}</span>`).join('')}
                </div>
            </div>
        `).join('')}
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
        tbody.innerHTML = '<tr><td colspan="12" style="text-align:center; color: var(--text-dim); padding: 24px;">No experiments yet. Click Start Lab to begin.</td></tr>';
        return;
    }
    tbody.innerHTML = history.map(h => {
        const statusClass = h.status || 'pending';
        const condClass = h.condition === 'critique_off' ? 'control' : '';
        const promoIcon = h.promotion_status === 'shadow' ? ' \u2b06' : '';
        const constraintIcon = h.constraints_met === 0 ? ' \u26a0' : '';
        const balanceClass = !h.balance_label
            ? 'balance-badge unknown'
            : h.balance_label === 'balanced'
                ? 'balance-badge balanced'
                : h.balance_label.includes('creativity')
                    ? 'balance-badge creativity'
                    : 'balance-badge utility';

        return `<tr onclick="showArtifact(${h.id})" class="${condClass}">
            <td>${h.id}</td>
            <td><strong>${h.composite != null ? h.composite.toFixed(2) : '--'}</strong>${constraintIcon}${promoIcon}</td>
            <td>${fmtScore(h.novelty)}</td>
            <td>${fmtScore(h.surprise)}</td>
            <td>${fmtScore(h.value)}</td>
            <td>${fmtScore(h.elaboration)}</td>
            <td>${fmtScore(h.coherence)}</td>
            <td><span class="lane-badge ${h.lane || 'creative'}">${h.lane || 'creative'}</span></td>
            <td><span class="${balanceClass}">${h.balance_label || '--'}</span></td>
            <td><span class="condition-badge ${h.condition || ''}">${h.condition === 'critique_off' ? 'CTRL' : ''}</span></td>
            <td><span class="status-badge ${statusClass}">${statusClass}</span></td>
            <td class="desc-cell">${truncate(h.prompt || '', 50)}</td>
        </tr>`;
    }).join('');
}

function fmtScore(v) { return v != null ? v.toFixed(1) : '--'; }
function truncate(s, n) { return s.length > n ? s.substring(0, n) + '...' : s; }
function scoreCard(dim, value, extraClass = '') {
    return `<div class="modal-score ${extraClass}"><div class="label">${dim}</div><div class="val">${value != null ? value.toFixed(1) : '--'}</div></div>`;
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
        return ['genesis', 'muse', 'hermes', 'holdout']
            .filter(role => data[role])
            .map(role => `${role}:${data[role].backend}/${data[role].model}`)
            .join(' | ');
    } catch {
        return modelVersion;
    }
}

async function showArtifact(id) {
    try {
        const data = await fetch('/api/artifact/' + id).then(r => r.json());
        if (data.error) return;
        currentArtifact = data;
        modelEvaluationRevealed = !!data.human_review;
        updateReviewCopy(data.lane);

        document.getElementById('modal-title').textContent = 'Experiment #' + data.id + ' \u2014 ' + (data.lane || '') + ' / ' + (data.track || '');

        let meta = '';
        if (data.condition) meta += `Condition: ${data.condition}`;
        if (data.promotion_status) meta += ` | Tier: ${data.promotion_status}`;
        if (data.hypothesis_id) meta += ` | Hypothesis: ${data.hypothesis_id}`;
        if (data.prompt_family) meta += ` | Family: ${data.prompt_family}`;
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

        const dims = ['novelty', 'surprise', 'value', 'elaboration', 'coherence'];
        const businessDims = ['actionability', 'brand_fit', 'factual_reliability'];
        const activeDims = businessDims.some(d => data[d] != null) ? dims.concat(businessDims) : dims;
        document.getElementById('modal-scores').innerHTML =
            '<div class="modal-scorer-label">MUSE (internal)</div>' +
            activeDims.map(d => scoreCard(d, data[d])).join('');

        const holdoutEl = document.getElementById('modal-holdout');
        if (data.holdout_scores && data.holdout_scores.length > 0) {
            const h = data.holdout_scores[0];
            holdoutEl.innerHTML =
                '<div class="modal-scorer-label">HERMES (independent)</div>' +
                activeDims.map(d => scoreCard(d, h[d], 'holdout')).join('');
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

        document.getElementById('modal-artifact').textContent = data.artifact_content || '(no artifact)';
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

async function triggerCouncil() {
    try {
        const headers = buildAdminHeaders(false);
        if (!headers) return;
        const res = await fetch('/api/council', { method: 'POST', headers }).then(r => r.json());
        if (res.research_memo || res.recommendation) {
            showCouncilModal(res);
        } else {
            alert('Council: ' + JSON.stringify(res));
        }
    } catch (e) { console.error('Council failed:', e); }
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
    }
});
