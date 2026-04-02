from __future__ import annotations

import json
import math
import os
from contextlib import asynccontextmanager

import aiosqlite


DB_PATH = os.path.join(os.path.dirname(__file__), "creativity_lab.db")
HOLDOUT_SCORERS = ("critic_holdout", "hermes", "hermes_external")
SQLITE_BUSY_TIMEOUT_MS = 5000
SQLITE_JOURNAL_MODE = "WAL"
SQLITE_SYNCHRONOUS_MODE = "NORMAL"


def _mean(values):
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _safe_json_loads(value, default=None):
    if value is None:
        return default
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _pearson_correlation(xs, ys):
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 2:
        return None
    mean_x = sum(x for x, _ in pairs) / n
    mean_y = sum(y for _, y in pairs) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in pairs)
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x, _ in pairs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for _, y in pairs))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _correlation(xs, ys):
    return _pearson_correlation(xs, ys)


def _stddev(values):
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if n < 2:
        return 0.0
    mean = sum(vals) / n
    return math.sqrt(sum((v - mean) ** 2 for v in vals) / (n - 1))


def _classify_creativity_overreach(row):
    gap = row.get("balance_gap")
    composite = row.get("composite")
    novelty = row.get("novelty")
    surprise = row.get("surprise")
    status = row.get("status")
    expressive_pressure = _mean([novelty, surprise])
    counterpart = row.get("balance_counterpart")
    pressure_gap = None if expressive_pressure is None or counterpart is None else expressive_pressure - counterpart

    if composite is None:
        return False
    if status == "constraint_fail" and expressive_pressure is not None and expressive_pressure >= 5.5:
        return True
    if row.get("lane") == "business":
        return pressure_gap is not None and pressure_gap > 0.25 and composite < 7.5
    if pressure_gap is not None and pressure_gap > 0.5 and composite < 7.0:
        return True
    return gap is not None and gap > 0.5 and composite < 7.0


def _build_policy_validation_summary(rows):
    overview = {
        "approved_pending_use": 0,
        "approved_in_trial": 0,
        "approved_validated": 0,
    }
    for row in rows:
        status = row.get("operational_status")
        if status in overview:
            overview[status] += 1
    return {
        "headline": f"{len(rows)} approved family defaults tracked.",
        "overview": overview,
        "rows": rows,
    }


def _build_protocol_reliability(rows):
    total = len(rows)
    if not total:
        return {
            "headline": "Protocol reliability tracked across 0 runs.",
            "overview": {},
            "protocol_versions": {},
        }

    def rate(pred):
        return sum(1 for row in rows if pred(row)) / total

    versions = {}
    for row in rows:
        trace = row.get("process_trace") or {}
        revision_status = trace.get("revision_status") or "unknown"
        versions[f"socratic_revision_{revision_status}"] = versions.get(f"socratic_revision_{revision_status}", 0) + 1

    def hermes_gate(row):
        return ((row.get("process_trace") or {}).get("orchestration") or {}).get("gates", {}).get("hermes", {})

    overview = {
        "selection_fallback_rate": rate(lambda row: "fallback" in ((row.get("process_trace") or {}).get("selection_status") or "")),
        "interlocutor_fallback_rate": rate(lambda row: "fallback" in ((row.get("process_trace") or {}).get("interlocutor_status") or "")),
        "hermes_skip_rate": rate(lambda row: hermes_gate(row).get("decision") == "skipped"),
        "hermes_forced_rate": rate(lambda row: "forced_sample" in (hermes_gate(row).get("reason") or "")),
    }
    return {
        "headline": f"Protocol reliability tracked across {total} runs.",
        "overview": overview,
        "protocol_versions": versions,
        "rows": rows,
    }


def _build_policy_effects(rows):
    if not rows:
        return {"headline": "Policy effects tracked across 0 lane/family/variant cells.", "overview": {}, "rows": []}

    grouped = {}
    for row in rows:
        key = (row.get("lane"), row.get("prompt_family"))
        grouped.setdefault(key, []).append(row)

    enriched = []
    for (lane, family), bucket in grouped.items():
        family_mean = _mean(item.get("mean_composite") for item in bucket) or 0.0
        baseline_keep = _mean(item.get("human_keep_rate") for item in bucket) or 0.0
        for row in bucket:
            clone = dict(row)
            clone["composite_lift"] = (row.get("mean_composite") or 0.0) - family_mean
            clone["human_keep_lift"] = (row.get("human_keep_rate") or 0.0) - baseline_keep
            enriched.append(clone)

    enriched.sort(key=lambda row: (row.get("composite_lift") or 0, row.get("trials") or 0), reverse=True)
    best_variant = max(enriched, key=lambda row: row.get("mean_composite") or float("-inf"))
    critique_sensitive = max(enriched, key=lambda row: row.get("critique_delta") or float("-inf"))
    return {
        "headline": f"Policy effects tracked across {len(rows)} lane/family/variant cells.",
        "overview": {
            "best_variant": best_variant,
            "critique_sensitive_variant": critique_sensitive,
        },
        "rows": enriched,
    }


def _build_policy_recommendations(family_metrics, policy_effect_rows, registry_rows, adoption_rows=None):
    adoption_rows = adoption_rows or []
    adoption_index = {
        (row.get("lane"), row.get("prompt_family"), row.get("policy_key"), row.get("approved_value")): row
        for row in adoption_rows
    }

    rows = []
    if registry_rows:
        for row in registry_rows:
            clone = dict(row)
            adoption = adoption_index.get(
                (clone.get("lane"), clone.get("prompt_family"), clone.get("policy_key"), clone.get("approved_value"))
            )
            if adoption:
                clone.update(adoption)
                clone["operational_status"] = "approved_validated" if (adoption.get("adopted_trials") or 0) >= 3 else "approved_in_trial"
            else:
                clone["operational_status"] = "approved_pending_use"
            rows.append(clone)
        return {"headline": f"{len(rows)} policy recommendations tracked.", "rows": rows}

    family_lookup = {(row.get("lane"), row.get("prompt_family")): row for row in family_metrics}
    grouped = {}
    for row in policy_effect_rows:
        grouped.setdefault((row.get("lane"), row.get("prompt_family")), []).append(row)

    for key, bucket in grouped.items():
        best = max(bucket, key=lambda row: ((row.get("composite_lift") or 0), (row.get("human_keep_lift") or 0)))
        family = family_lookup.get(key, {})
        rationale = (
            f"Recommend {best.get('prompt_policy_variant')} as the family default after outperforming peers "
            f"with composite lift {best.get('composite_lift', 0):+.2f} and human keep lift {best.get('human_keep_lift', 0):+.2f}."
        )
        rows.append({
            "lane": key[0],
            "prompt_family": key[1],
            "policy_key": "prompt_policy_default",
            "recommended_value": best.get("prompt_policy_variant"),
            "approval_status": "recommended",
            "rationale": rationale,
            "sample_size": family.get("sample_size"),
        })
    return {"headline": f"{len(rows)} policy recommendations tracked.", "rows": rows}


def _build_calibration_metrics(rows, verifier_rows, paired_rows, calibration_rows):
    if not rows:
        return {"overview": {}, "families": [], "headline": "No calibration metrics yet."}

    family_groups = {}
    for row in rows:
        family_groups.setdefault((row.get("lane") or "creative", row.get("prompt_family") or "unclassified"), []).append(row)

    family_metrics = []
    for (lane, family), bucket in family_groups.items():
        family_metrics.append({
            "lane": lane,
            "prompt_family": family,
            "sample_size": len(bucket),
            "overreach_rate": _mean(1.0 if _classify_creativity_overreach(row) else 0.0 for row in bucket),
            "constraint_recovery_rate": None,
            "critique_help_rate": None,
            "novelty_gap": _mean(row.get("balance_gap") for row in bucket),
        })

    overview = {
        "tracked_runs": len(rows),
        "creativity_overreach_rate": _mean(1.0 if _classify_creativity_overreach(row) else 0.0 for row in rows),
        "unknown_constraint_rate": _mean(1.0 if row.get("constraints_met") is None else 0.0 for row in rows),
        "constraint_recovery_rate": None,
        "critique_help_rate": None,
        "mean_novelty_gap": _mean(row.get("balance_gap") for row in rows),
        "human_agreement_rate": None,
    }
    headline = (
        f"Calibration readout across {len(rows)} scored runs: overreach {overview['creativity_overreach_rate']:.0%}, "
        f"unknown constraints {overview['unknown_constraint_rate']:.0%}."
    )
    return {"overview": overview, "families": family_metrics[:8], "headline": headline}


def _build_learning_snapshot(rows, paired_rows, verifier_rows, calibration_rows):
    if not rows:
        return {
            "headline": "No learning snapshot yet.",
            "improved": "Need more scored runs before calling anything improved.",
            "regressed": "No clear regression yet.",
            "still_noisy": "Sample size is too small for a stable judgment.",
            "next_move": "Run a small paired batch in one family and compare critique-on versus critique-off.",
        }

    recent = rows[:10]
    prior = rows[10:20]

    def summarize_window(bucket):
        known_constraints = [row.get("constraints_met") for row in bucket if row.get("constraints_met") is not None]
        return {
            "composite": _mean(row.get("composite") for row in bucket),
            "overreach": _mean(1.0 if _classify_creativity_overreach(row) else 0.0 for row in bucket),
            "constraint_pass": _mean(1.0 if value else 0.0 for value in known_constraints),
        }

    recent_summary = summarize_window(recent)
    prior_summary = summarize_window(prior)

    improved = "Recent runs are still too isolated to name a clear improvement."
    regressed = "No clear regression yet."
    still_noisy = "Human agreement is still too sparse to anchor the calibration story."

    if prior:
        overreach_delta = None
        if recent_summary["overreach"] is not None and prior_summary["overreach"] is not None:
            overreach_delta = recent_summary["overreach"] - prior_summary["overreach"]
        constraint_delta = None
        if recent_summary["constraint_pass"] is not None and prior_summary["constraint_pass"] is not None:
            constraint_delta = recent_summary["constraint_pass"] - prior_summary["constraint_pass"]
        composite_delta = None
        if recent_summary["composite"] is not None and prior_summary["composite"] is not None:
            composite_delta = recent_summary["composite"] - prior_summary["composite"]

        if constraint_delta is not None and constraint_delta > 0.15:
            improved = f"Constraint pass rate improved {constraint_delta:+.0%} in the latest window, which is the clearest sign of correction recognition."
        elif overreach_delta is not None and overreach_delta < -0.10:
            improved = f"Creativity overreach fell {abs(overreach_delta):.0%} in the latest window, suggesting slightly better calibration."
        elif composite_delta is not None and composite_delta > 0.25:
            improved = f"Mean composite improved {composite_delta:+.2f} in the latest window, though the cause still needs attribution."

        if overreach_delta is not None and overreach_delta > 0.10:
            regressed = f"Creativity overreach rose {overreach_delta:+.0%}, so the lab may still be rewarding flourish where it should be restrained."
        elif constraint_delta is not None and constraint_delta < -0.15:
            regressed = f"Constraint pass rate fell {constraint_delta:+.0%}, which suggests the correction loop is not stable yet."
        elif composite_delta is not None and composite_delta < -0.25:
            regressed = f"Mean composite fell {composite_delta:+.2f} in the latest window."

    if paired_rows:
        ambiguous = min(paired_rows, key=lambda row: abs(row.get("composite_delta") or 0))
        still_noisy = (
            f"Critique effect is still noisy in {ambiguous.get('prompt_family') or 'unclassified'} "
            f"({(ambiguous.get('composite_delta') or 0):+.2f}), so that family still needs tighter paired testing."
        )

    if calibration_rows:
        agreement = []
        for row in calibration_rows:
            worth_saving = row.get("worth_saving")
            muse_composite = row.get("muse_composite")
            if worth_saving is None or muse_composite is None:
                continue
            agreement.append(1.0 if (worth_saving >= 4) == (muse_composite >= 6.5) else 0.0)
        agreement_rate = _mean(agreement)
        if agreement_rate is not None and agreement_rate < 0.7:
            still_noisy = (
                f"Human versus MUSE save/discard agreement is only {agreement_rate:.0%}, "
                "so evaluator trust is still the main source of uncertainty."
            )

    return {
        "headline": "Learning snapshot updated.",
        "improved": improved,
        "regressed": regressed,
        "still_noisy": still_noisy,
        "next_move": "Run one paired family with critique-on versus critique-off and compare overreach, constraint recovery, and human save/discard.",
    }


@asynccontextmanager
async def connect():
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    await conn.execute(f"PRAGMA journal_mode = {SQLITE_JOURNAL_MODE}")
    await conn.execute(f"PRAGMA synchronous = {SQLITE_SYNCHRONOUS_MODE}")
    try:
        yield conn
    finally:
        await conn.close()


async def init_db():
    async with connect() as conn:
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS lab_state (
                id INTEGER PRIMARY KEY,
                running INTEGER NOT NULL DEFAULT 0,
                total_experiments INTEGER NOT NULL DEFAULT 0,
                kept INTEGER NOT NULL DEFAULT 0,
                discarded INTEGER NOT NULL DEFAULT 0,
                invalid INTEGER NOT NULL DEFAULT 0,
                promoted INTEGER NOT NULL DEFAULT 0,
                best_score REAL,
                total_cost REAL NOT NULL DEFAULT 0,
                cost_cap REAL NOT NULL DEFAULT 50,
                consecutive_discards INTEGER NOT NULL DEFAULT 0,
                current_lane TEXT,
                current_track TEXT,
                current_experiment_id INTEGER,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lane TEXT,
                track TEXT,
                iteration INTEGER,
                creativity_type TEXT,
                prompt TEXT,
                prompt_family TEXT,
                constraints TEXT,
                condition TEXT,
                status TEXT,
                promotion_status TEXT,
                hypothesis_id TEXT,
                parse_failure INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                error_traceback TEXT,
                generation_protocol TEXT DEFAULT 'one_shot'
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
                content TEXT,
                process_trace TEXT,
                source_context TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id INTEGER NOT NULL,
                experiment_id INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
                scored_by TEXT NOT NULL,
                novelty REAL,
                surprise REAL,
                value REAL,
                elaboration REAL,
                coherence REAL,
                composite REAL,
                actionability REAL,
                brand_fit REAL,
                factual_reliability REAL,
                constraints_met INTEGER,
                constraint_notes TEXT,
                critique TEXT,
                parse_failure INTEGER NOT NULL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS policy_registry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lane TEXT NOT NULL,
                prompt_family TEXT NOT NULL,
                policy_key TEXT NOT NULL,
                recommended_value TEXT,
                approved_value TEXT,
                approval_status TEXT,
                operational_status TEXT,
                rationale TEXT,
                reviewer_note TEXT,
                source TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(lane, prompt_family, policy_key)
            );

            CREATE TABLE IF NOT EXISTS prompt_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_hash TEXT UNIQUE,
                prompt_family TEXT,
                prompt_text TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS hypotheses (
                id TEXT PRIMARY KEY,
                description TEXT,
                lane TEXT
            );

            CREATE TABLE IF NOT EXISTS reference_packs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                payload TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS council_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        await conn.execute("INSERT OR IGNORE INTO lab_state (id) VALUES (1)")
        columns = [row["name"] for row in await (await conn.execute("PRAGMA table_info(policy_registry)")).fetchall()]
        if "operational_status" not in columns:
            await conn.execute("ALTER TABLE policy_registry ADD COLUMN operational_status TEXT")
        await conn.commit()


async def get_state():
    await init_db()
    async with connect() as conn:
        row = await (await conn.execute("SELECT * FROM lab_state WHERE id = 1")).fetchone()
        return dict(row)


async def update_state(**fields):
    await init_db()
    if not fields:
        return await get_state()
    fields["updated_at"] = "CURRENT_TIMESTAMP"
    assignments = []
    values = []
    for key, value in fields.items():
        if value == "CURRENT_TIMESTAMP":
            assignments.append(f"{key} = CURRENT_TIMESTAMP")
        else:
            assignments.append(f"{key} = ?")
            values.append(value)
    async with connect() as conn:
        await conn.execute(f"UPDATE lab_state SET {', '.join(assignments)} WHERE id = 1", values)
        await conn.commit()
    return await get_state()


async def insert_hypothesis(hypothesis_id, description, lane):
    await init_db()
    async with connect() as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO hypotheses (id, description, lane) VALUES (?, ?, ?)",
            (hypothesis_id, description, lane),
        )
        await conn.commit()


async def store_prompt_version(prompt_hash, prompt_family, prompt_text):
    await init_db()
    async with connect() as conn:
        columns = [row["name"] for row in await (await conn.execute("PRAGMA table_info(prompt_versions)")).fetchall()]
        if {"prompt_hash", "prompt_family", "prompt_text"}.issubset(columns):
            await conn.execute(
                "INSERT OR REPLACE INTO prompt_versions (prompt_hash, prompt_family, prompt_text) VALUES (?, ?, ?)",
                (prompt_hash, prompt_family, prompt_text),
            )
        else:
            await conn.execute(
                "INSERT OR REPLACE INTO prompt_versions (hash, role, content) VALUES (?, ?, ?)",
                (prompt_hash, prompt_family, prompt_text),
            )
        await conn.commit()


async def create_experiment(task, status="running", iteration=None):
    await init_db()
    state = await get_state()
    async with connect() as conn:
        cur = await conn.execute(
            """
            INSERT INTO experiments (
                lane, track, iteration, creativity_type, prompt, prompt_family, constraints,
                condition, status, promotion_status, hypothesis_id, generation_protocol
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task.get("lane"),
                task.get("track"),
                iteration if iteration is not None else (state.get("total_experiments") or 0) + 1,
                task.get("creativity_type"),
                task.get("prompt"),
                task.get("family"),
                json.dumps(task.get("constraints") or []),
                task.get("condition"),
                status,
                "candidate",
                task.get("hypothesis"),
                task.get("generation_protocol", "socratic"),
            ),
        )
        await conn.commit()
        return cur.lastrowid


async def finalize_experiment(experiment_id, *, status, promotion_status="candidate", parse_failure=False, cost=0.0, error_traceback=None):
    async with connect() as conn:
        await conn.execute(
            """
            UPDATE experiments
            SET status = ?, promotion_status = ?, parse_failure = ?, error_traceback = ?
            WHERE id = ?
            """,
            (status, promotion_status, int(bool(parse_failure)), error_traceback, experiment_id),
        )
        await conn.commit()


async def insert_artifact(experiment_id, artifact, process_trace=None, source_context=None):
    async with connect() as conn:
        existing = await (await conn.execute("SELECT id FROM artifacts WHERE experiment_id = ?", (experiment_id,))).fetchone()
        if existing:
            artifact_id = existing["id"]
            await conn.execute(
                "UPDATE artifacts SET content = ?, process_trace = ?, source_context = ? WHERE experiment_id = ?",
                (artifact, json.dumps(process_trace or {}), json.dumps(source_context or {}), experiment_id),
            )
        else:
            cur = await conn.execute(
                "INSERT INTO artifacts (experiment_id, content, process_trace, source_context) VALUES (?, ?, ?, ?)",
                (experiment_id, artifact, json.dumps(process_trace or {}), json.dumps(source_context or {})),
            )
            artifact_id = cur.lastrowid
        await conn.commit()
        return artifact_id


async def update_artifact_process_trace(experiment_id, process_trace):
    async with connect() as conn:
        await conn.execute(
            "UPDATE artifacts SET process_trace = ? WHERE experiment_id = ?",
            (json.dumps(process_trace or {}), experiment_id),
        )
        await conn.commit()


async def update_artifact_source_context(experiment_id, source_context):
    async with connect() as conn:
        await conn.execute(
            "UPDATE artifacts SET source_context = ? WHERE experiment_id = ?",
            (json.dumps(source_context or {}), experiment_id),
        )
        await conn.commit()


async def insert_score(experiment_id, scored_by, payload, cost=0.0, parse_failure=False):
    async with connect() as conn:
        artifact_row = await (await conn.execute("SELECT id FROM artifacts WHERE experiment_id = ? ORDER BY id DESC LIMIT 1", (experiment_id,))).fetchone()
        artifact_id = artifact_row["id"] if artifact_row else 0
        await conn.execute(
            """
            INSERT INTO scores (
                artifact_id, experiment_id, novelty, surprise, value, elaboration, coherence, composite,
                actionability, brand_fit, factual_reliability, constraints_met, constraint_notes, critique,
                scored_by, parse_failure
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                experiment_id,
                payload.get("novelty"),
                payload.get("surprise"),
                payload.get("value"),
                payload.get("elaboration"),
                payload.get("coherence"),
                payload.get("composite"),
                payload.get("actionability"),
                payload.get("brand_fit"),
                payload.get("factual_reliability"),
                None if payload.get("constraints_met") is None else int(bool(payload.get("constraints_met"))),
                payload.get("constraint_notes"),
                payload.get("critique"),
                scored_by,
                int(bool(parse_failure)),
            ),
        )
        await conn.commit()


async def get_holdout_scores(experiment_id):
    async with connect() as conn:
        rows = await (await conn.execute(
            "SELECT * FROM scores WHERE experiment_id = ? AND scored_by IN ('critic_holdout', 'hermes', 'hermes_external') ORDER BY id",
            (experiment_id,),
        )).fetchall()
        return [dict(row) for row in rows]


async def get_experiment_by_id(experiment_id):
    async with connect() as conn:
        row = await (await conn.execute(
            """
            SELECT e.*, a.content, a.process_trace, a.source_context
            FROM experiments e
            LEFT JOIN artifacts a ON a.experiment_id = e.id
            WHERE e.id = ?
            """,
            (experiment_id,),
        )).fetchone()
        if not row:
            return None
        payload = dict(row)
        payload["artifact"] = payload.pop("content", payload.get("artifact"))
        payload["family"] = payload.get("prompt_family")
        payload["hypothesis"] = payload.get("hypothesis_id")
        payload["constraints"] = _safe_json_loads(payload.get("constraints"), [])
        payload["process_trace"] = _safe_json_loads(payload.get("process_trace"), {})
        payload["source_context"] = _safe_json_loads(payload.get("source_context"), {})
        return payload


async def get_recent_experiments(limit=40):
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT e.*, a.content, a.process_trace
            FROM experiments e
            LEFT JOIN artifacts a ON a.experiment_id = e.id
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (limit,),
        )).fetchall()
        records = []
        for row in rows:
            payload = dict(row)
            payload["artifact"] = payload.pop("content", None)
            payload["family"] = payload.get("prompt_family")
            payload["hypothesis"] = payload.get("hypothesis_id")
            payload["constraints"] = _safe_json_loads(payload.get("constraints"), [])
            payload["process_trace"] = _safe_json_loads(payload.get("process_trace"), {})
            records.append(payload)
        return records


async def get_recent_scores(limit=200):
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT s.*, e.lane, e.prompt_family, e.status
            FROM scores s
            JOIN experiments e ON e.id = s.experiment_id
            WHERE s.scored_by = 'muse'
            ORDER BY s.id DESC
            LIMIT ?
            """,
            (limit,),
        )).fetchall()
        return [dict(row) for row in rows]


async def get_timeline(limit=120):
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT e.id, e.status, e.created_at, s.composite, e.lane, e.condition
            FROM experiments e
            LEFT JOIN scores s ON s.experiment_id = e.id AND s.scored_by = 'muse'
            ORDER BY e.id DESC
            LIMIT ?
            """,
            (limit,),
        )).fetchall()
        return [dict(row) for row in reversed(rows)]


async def get_best_scores():
    async with connect() as conn:
        row = await (await conn.execute(
            """
            SELECT novelty, surprise, value, elaboration, coherence
            FROM scores
            WHERE scored_by = 'muse'
            ORDER BY composite DESC, id DESC
            LIMIT 1
            """
        )).fetchone()
        return dict(row) if row else {key: None for key in ("novelty", "surprise", "value", "elaboration", "coherence")}


async def get_trends():
    scores = await get_recent_scores(limit=200)
    if not scores:
        return {
            "mean_composite": None,
            "median_composite": None,
            "early_mean": None,
            "recent_mean": None,
            "muse_critic_divergence": None,
            "muse_critic_pairs": 0,
            "lanes": [],
            "conditions": [],
        }
    composites = [row.get("composite") for row in scores if row.get("composite") is not None]
    recent = composites[:10]
    early = composites[-10:] if len(composites) >= 10 else composites
    lane_groups = {}
    for row in scores:
        lane_groups.setdefault(row.get("lane") or "creative", []).append(row)
    lanes = [
        {"lane": lane, "lane_mean": _mean(item.get("composite") for item in bucket), "lane_count": len(bucket)}
        for lane, bucket in lane_groups.items()
    ]
    return {
        "mean_composite": _mean(composites),
        "median_composite": sorted(composites)[len(composites) // 2] if composites else None,
        "early_mean": _mean(early),
        "recent_mean": _mean(recent),
        "muse_critic_divergence": None,
        "muse_critic_pairs": 0,
        "lanes": lanes,
        "conditions": [],
    }


async def upsert_policy_registry_entry(row):
    await init_db()
    async with connect() as conn:
        await conn.execute(
            """
            INSERT INTO policy_registry (
                lane, prompt_family, policy_key, recommended_value, approved_value,
                approval_status, operational_status, rationale, reviewer_note, source, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(lane, prompt_family, policy_key) DO UPDATE SET
                recommended_value = excluded.recommended_value,
                approved_value = excluded.approved_value,
                approval_status = excluded.approval_status,
                operational_status = excluded.operational_status,
                rationale = excluded.rationale,
                reviewer_note = excluded.reviewer_note,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                row.get("lane"),
                row.get("prompt_family"),
                row.get("policy_key"),
                row.get("recommended_value"),
                row.get("approved_value"),
                row.get("approval_status"),
                row.get("operational_status"),
                row.get("rationale"),
                row.get("reviewer_note"),
                row.get("source"),
            ),
        )
        await conn.commit()


async def get_policy_registry():
    async with connect() as conn:
        rows = await (await conn.execute("SELECT * FROM policy_registry ORDER BY updated_at DESC, id DESC")).fetchall()
        return [dict(row) for row in rows]


async def get_approved_policy_controls():
    rows = await get_policy_registry()
    controls = {}
    for row in rows:
        if row.get("policy_key") == "prompt_policy_default" and row.get("approval_status") == "approved" and row.get("approved_value"):
            controls[(row.get("lane"), row.get("prompt_family"))] = row
    return controls


async def list_reference_packs():
    async with connect() as conn:
        rows = await (await conn.execute(
            """
            SELECT id, lane, prompt_family, title, source_type, task_definition, live_examples,
                   failure_modes, expected_tradeoffs, constraint_patterns, paired_test_matrix,
                   notes, status, created_at, updated_at
            FROM reference_packs
            ORDER BY id DESC
            """
        )).fetchall()
        payloads = []
        for row in rows:
            payload = dict(row)
            for key in ("task_definition", "live_examples", "failure_modes", "expected_tradeoffs", "constraint_patterns", "paired_test_matrix"):
                payload[key] = _safe_json_loads(payload.get(key), payload.get(key))
            payloads.append(payload)
        return payloads


async def create_reference_pack(payload):
    async with connect() as conn:
        cur = await conn.execute(
            """
            INSERT INTO reference_packs (
                lane, prompt_family, title, source_type, task_definition, live_examples,
                failure_modes, expected_tradeoffs, constraint_patterns, paired_test_matrix, notes, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("lane", "creative"),
                payload.get("prompt_family", "general"),
                payload.get("title"),
                payload.get("source_type", "manual"),
                json.dumps(payload.get("task_definition")),
                json.dumps(payload.get("live_examples")),
                json.dumps(payload.get("failure_modes")),
                json.dumps(payload.get("expected_tradeoffs")),
                json.dumps(payload.get("constraint_patterns")),
                json.dumps(payload.get("paired_test_matrix")),
                payload.get("notes"),
                payload.get("status", "draft"),
            ),
        )
        await conn.commit()
        return cur.lastrowid


async def add_council_entry(payload):
    async with connect() as conn:
        cur = await conn.execute(
            "INSERT INTO council_history (payload) VALUES (?)",
            (json.dumps(payload),),
        )
        await conn.commit()
        return cur.lastrowid


async def get_council_history(limit=10):
    async with connect() as conn:
        rows = await (await conn.execute(
            "SELECT id, payload, created_at FROM council_history ORDER BY id DESC LIMIT ?",
            (limit,),
        )).fetchall()
        return [{"id": row["id"], "payload": _safe_json_loads(row["payload"], {}), "created_at": row["created_at"]} for row in rows]


async def build_state_payload():
    state = await get_state()
    best_scores = await get_best_scores()
    trends = await get_trends()
    return {"state": state, "best_scores": best_scores, "trends": trends}


async def get_analysis_payload():
    rows = await get_recent_scores(limit=200)
    policy_rows = await get_policy_registry()
    return {
        "balance_summary": {"headline": "Recovery mode: analytics are available again.", "lane_summaries": []},
        "learning_snapshot": {"headline": "Lab recovered.", "improved": "Core backend imports and storage are functioning again.", "regressed": "Historical advanced analytics were rebuilt conservatively.", "still_noisy": "Run a few new experiments to repopulate analysis views.", "next_move": "Start with a short batch and confirm the loop end-to-end."},
        "recommendations": {},
        "hypotheses": [],
        "creativity_balance": [],
        "paired_conditions": [],
        "business_creativity_tax": [],
        "champions": [],
        "policy_effects": _build_policy_effects([]),
        "policy_validation": _build_policy_validation_summary(policy_rows),
        "evaluator_diagnostics": {"headline": "Diagnostics repopulate as fresh scores arrive.", "warnings": []},
        "protocol_reliability": _build_protocol_reliability([]),
        "human_calibration": {"headline": "No human calibration reviews yet.", "lane_summaries": [], "priority": None},
        "constraint_verifier": {"headline": "No verifier-tracked runs yet.", "totals": {}, "families": []},
        "calibration_metrics": _build_calibration_metrics(rows, [], [], []),
        "disagreement_queue": {"headline": "No disagreement queue yet.", "rows": []},
        "policy_recommendations": _build_policy_recommendations([], [], policy_rows),
    }
