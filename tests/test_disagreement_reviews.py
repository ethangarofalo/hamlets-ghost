import tempfile
import unittest
from pathlib import Path

import database as db


class DisagreementReviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_disagreement.db")
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        await db.init_db()

        base_task = {
            "lane": "creative",
            "track": "paired",
            "prompt": "Write a prayer from the perspective of a dying programming language.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_off",
            "generation_protocol": "paired_native",
            "packet_id": "packet_test_disagreement",
        }
        self.exp_a = await db.create_experiment({**base_task, "packet_role_id": "genesis", "packet_primary": True}, status="promoted")
        self.exp_b = await db.create_experiment({**base_task, "packet_role_id": "theron", "packet_primary": False}, status="promoted")
        await db.insert_artifact(self.exp_a, "Genesis artifact")
        await db.insert_artifact(self.exp_b, "Theron artifact")
        await db.insert_score(self.exp_a, "muse", {"composite": 8.2})
        await db.insert_score(self.exp_b, "muse", {"composite": 7.8})
        await db.insert_score(self.exp_a, "athena", {"composite": 8.1})
        await db.insert_score(self.exp_b, "athena", {"composite": 7.6})
        await db.insert_score(self.exp_a, "apollo", {"composite": 7.4})
        await db.insert_score(self.exp_b, "apollo", {"composite": 8.3})
        await db.finalize_experiment(self.exp_a, status="promoted", promotion_status="shadow")
        await db.finalize_experiment(self.exp_b, status="promoted", promotion_status="shadow")

    async def asyncTearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    async def test_list_disagreement_packets_detects_split_panel(self):
        rows = await db.list_disagreement_packets(limit=5, unresolved_only=True, recent_limit=20)

        self.assertEqual(len(rows), 1)
        packet = rows[0]
        self.assertEqual(packet["packet_id"], "packet_test_disagreement")
        judge_winners = {row["judge"]: row["winner_experiment_id"] for row in packet["judge_preferences"]}
        self.assertEqual(judge_winners["muse"], self.exp_a)
        self.assertEqual(judge_winners["athena"], self.exp_a)
        self.assertEqual(judge_winners["apollo"], self.exp_b)

    async def test_save_comparison_review_removes_packet_from_unresolved_queue(self):
        review = await db.save_comparison_review(
            "packet_test_disagreement",
            preferred_experiment_id=self.exp_b,
            rationale="Theron had more pathos.",
            reviewer="ethan",
            review_channel="telegram",
        )

        self.assertEqual(review["preferred_experiment_id"], self.exp_b)
        rows = await db.list_disagreement_packets(limit=5, unresolved_only=True, recent_limit=20)
        self.assertEqual(rows, [])

    async def test_save_comparison_review_normalizes_reason_tag_attribution(self):
        review = await db.save_comparison_review(
            "packet_test_disagreement",
            preferred_experiment_id=self.exp_b,
            rationale="Theron had more pathos and Genesis was generic.",
            reviewer="ethan",
            review_channel="telegram",
            metadata={
                "reason_tag_attribution": {
                    "winner": ["real_pathos"],
                    "loser": ["generic_reassurance"],
                    "both": ["specific_detail"],
                },
                "reason_tag_evidence": [
                    {"tag": "real_pathos", "target": "winner", "excerpt": "I kept praying in a syntax nobody still spoke."},
                    {"tag": "generic_reassurance", "target": "loser", "excerpt": "We value your feedback and appreciate your patience."},
                ],
            },
        )

        self.assertEqual(review["metadata"]["reason_tag_attribution"]["winner"], ["real_pathos"])
        self.assertEqual(review["metadata"]["reason_tag_attribution"]["loser"], ["generic_reassurance"])
        self.assertEqual(review["metadata"]["reason_tag_attribution"]["both"], ["specific_detail"])
        self.assertEqual(
            review["metadata"]["reason_tags"],
            ["real_pathos", "generic_reassurance", "specific_detail"],
        )
        self.assertEqual(
            review["metadata"]["reason_tag_evidence"][0],
            {"tag": "real_pathos", "target": "winner", "excerpt": "I kept praying in a syntax nobody still spoke."},
        )

    async def test_revisit_later_review_stays_in_queue(self):
        await db.save_comparison_review(
            "packet_test_disagreement",
            preferred_experiment_id=self.exp_b,
            rationale="Leaning Theron, but I want to revisit it.",
            reviewer="ethan",
            review_channel="telegram",
            metadata={
                "review_confidence": "coin_flip",
                "review_decision_state": "revisit_later",
            },
        )

        rows = await db.list_disagreement_packets(limit=5, unresolved_only=True, recent_limit=20)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["human_review"]["metadata"]["review_decision_state"], "revisit_later")

    async def test_generator_feedback_bundle_uses_attributed_wins_and_losses(self):
        await db.save_comparison_review(
            "packet_test_disagreement",
            preferred_experiment_id=self.exp_b,
            rationale="Theron had more pathos and Genesis fell back into generic reassurance.",
            reviewer="ethan",
            review_channel="telegram",
            metadata={
                "reason_tag_attribution": {
                    "winner": ["real_pathos"],
                    "loser": ["generic_reassurance"],
                },
                "reason_tag_evidence": [
                    {"tag": "real_pathos", "target": "winner", "excerpt": "I kept praying in a syntax nobody still spoke."},
                    {"tag": "generic_reassurance", "target": "loser", "excerpt": "We value your feedback and appreciate your patience."},
                ],
            },
        )

        genesis_feedback = await db.get_generator_feedback_for_task(
            "genesis",
            family="personification",
            lane="creative",
        )
        theron_feedback = await db.get_generator_feedback_for_task(
            "theron",
            family="personification",
            lane="creative",
        )

        self.assertEqual(genesis_feedback["scope_applied"], "family_lane")
        self.assertEqual(genesis_feedback["losses"], 1)
        self.assertEqual(genesis_feedback["top_flaws"], ["generic_reassurance"])
        self.assertIn("generic_reassurance", genesis_feedback["prior_feedback"])
        self.assertEqual(theron_feedback["wins"], 1)
        self.assertEqual(theron_feedback["top_strengths"], ["real_pathos"])
        self.assertIn("real_pathos", theron_feedback["prior_feedback"])

    async def test_save_comparison_review_allows_nonpreferred_verdict_without_winner(self):
        review = await db.save_comparison_review(
            "packet_test_disagreement",
            preferred_experiment_id=None,
            rationale="Both artifacts are weak in different ways.",
            reviewer="ethan",
            review_channel="telegram",
            metadata={
                "review_verdict": "both_bad",
                "review_confidence": "tentative",
                "reason_tag_attribution": {
                    "both": ["hedged_profundity"],
                },
            },
        )

        self.assertIsNone(review["preferred_experiment_id"])
        self.assertEqual(review["metadata"]["review_verdict"], "both_bad")
        self.assertEqual(review["metadata"]["reason_tag_attribution"]["both"], ["hedged_profundity"])

    async def test_same_writer_distinctiveness_adds_voice_collapse_tag(self):
        review = await db.save_comparison_review(
            "packet_test_disagreement",
            preferred_experiment_id=None,
            rationale="Both outputs feel like the same author solving the prompt twice.",
            reviewer="ethan",
            review_channel="telegram",
            metadata={
                "review_verdict": "tie",
                "review_confidence": "tentative",
                "pair_distinctiveness": "same_writer",
            },
        )

        self.assertEqual(review["metadata"]["pair_distinctiveness"], "same_writer")
        self.assertIn("voice_collapse", review["metadata"]["reason_tag_attribution"]["both"])
        self.assertIn("voice_collapse", review["metadata"]["reason_tags"])

    async def test_changed_mind_is_preserved_as_revision_history(self):
        await db.save_comparison_review(
            "packet_test_disagreement",
            preferred_experiment_id=self.exp_b,
            rationale="Initial lean toward Theron.",
            reviewer="ethan",
            review_channel="telegram",
            metadata={"review_confidence": "tentative"},
        )

        review = await db.save_comparison_review(
            "packet_test_disagreement",
            preferred_experiment_id=self.exp_a,
            rationale="On reread, Genesis is stronger.",
            reviewer="ethan",
            review_channel="telegram",
            metadata={"review_confidence": "certain"},
        )

        history = review["metadata"]["review_revision_history"]
        self.assertEqual(review["preferred_experiment_id"], self.exp_a)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["preferred_experiment_id"], self.exp_b)
        self.assertEqual(review["metadata"]["review_reversal_count"], 1)

    async def test_blind_rereview_candidates_include_old_reviews(self):
        await db.save_comparison_review(
            "packet_test_disagreement",
            preferred_experiment_id=self.exp_b,
            rationale="Theron had more pathos.",
            reviewer="ethan",
            review_channel="telegram",
            metadata={"review_confidence": "coin_flip"},
        )
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE comparison_reviews SET updated_at = '2000-01-01 00:00:00' WHERE packet_id = ?",
                ("packet_test_disagreement",),
            )
            await conn.commit()

        candidates = await db.list_blind_rereview_candidates(limit=5, epoch=db.CURRENT_EXPERIMENT_EPOCH)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["packet_id"], "packet_test_disagreement")
        self.assertEqual(candidates[0]["review_confidence"], "coin_flip")

    async def test_heuristic_same_prompt_cluster_does_not_enter_disagreement_queue(self):
        base_task = {
            "lane": "creative",
            "track": "open_ended",
            "prompt": "Create a voice that feels older than religion but younger than software.",
            "family": "unconstrained_generation",
            "constraints": [],
            "condition": "critique_on",
            "generation_protocol": "socratic",
        }
        exp_c = await db.create_experiment(base_task, status="promoted")
        exp_d = await db.create_experiment(base_task, status="promoted")
        await db.insert_artifact(exp_c, "Artifact C")
        await db.insert_artifact(exp_d, "Artifact D")
        await db.insert_score(exp_c, "muse", {"composite": 8.0})
        await db.insert_score(exp_d, "muse", {"composite": 7.9})
        await db.insert_score(exp_c, "athena", {"composite": 7.5})
        await db.insert_score(exp_d, "athena", {"composite": 8.0})
        await db.insert_score(exp_c, "apollo", {"composite": 7.9})
        await db.insert_score(exp_d, "apollo", {"composite": 7.7})
        await db.finalize_experiment(exp_c, status="promoted", promotion_status="shadow")
        await db.finalize_experiment(exp_d, status="promoted", promotion_status="shadow")

        rows = await db.list_disagreement_packets(limit=10, unresolved_only=True, recent_limit=50)

        packet_ids = {row["packet_id"] for row in rows}
        self.assertNotIn("pkt_db87fb6c63_1", packet_ids)

    async def test_get_disagreement_packet_returns_consensus_explicit_pair(self):
        base_task = {
            "lane": "creative",
            "track": "paired",
            "prompt": "Write a voice older than religion but younger than software.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_off",
            "generation_protocol": "paired_native",
            "packet_id": "packet_consensus_pair",
        }
        exp_c = await db.create_experiment({**base_task, "packet_role_id": "genesis", "packet_primary": True}, status="promoted")
        exp_d = await db.create_experiment({**base_task, "packet_role_id": "theron", "packet_primary": False}, status="promoted")
        await db.insert_artifact(exp_c, "Consensus Genesis artifact")
        await db.insert_artifact(exp_d, "Consensus Theron artifact")
        await db.insert_score(exp_c, "muse", {"composite": 8.1})
        await db.insert_score(exp_d, "muse", {"composite": 7.7})
        await db.insert_score(exp_c, "athena", {"composite": 8.0})
        await db.insert_score(exp_d, "athena", {"composite": 7.6})
        await db.insert_score(exp_c, "apollo", {"composite": 8.2})
        await db.insert_score(exp_d, "apollo", {"composite": 7.5})
        await db.finalize_experiment(exp_c, status="promoted", promotion_status="shadow")
        await db.finalize_experiment(exp_d, status="promoted", promotion_status="shadow")

        packet = await db.get_disagreement_packet("packet_consensus_pair")

        self.assertIsNotNone(packet)
        self.assertFalse(packet["has_noticeable_disagreement"])
        self.assertEqual(len(packet["members"]), 2)

    async def test_list_disagreement_packets_can_include_consensus_pairs(self):
        base_task = {
            "lane": "creative",
            "track": "paired",
            "prompt": "Write a hymn to rust from the perspective of a shipyard crane.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_off",
            "generation_protocol": "paired_native",
            "packet_id": "packet_consensus_queue",
        }
        exp_c = await db.create_experiment({**base_task, "packet_role_id": "genesis", "packet_primary": True}, status="promoted")
        exp_d = await db.create_experiment({**base_task, "packet_role_id": "theron", "packet_primary": False}, status="promoted")
        await db.insert_artifact(exp_c, "Consensus queue Genesis artifact")
        await db.insert_artifact(exp_d, "Consensus queue Theron artifact")
        await db.insert_score(exp_c, "muse", {"composite": 8.1})
        await db.insert_score(exp_d, "muse", {"composite": 7.8})
        await db.insert_score(exp_c, "athena", {"composite": 8.0})
        await db.insert_score(exp_d, "athena", {"composite": 7.7})
        await db.insert_score(exp_c, "apollo", {"composite": 8.2})
        await db.insert_score(exp_d, "apollo", {"composite": 7.6})
        await db.finalize_experiment(exp_c, status="promoted", promotion_status="shadow")
        await db.finalize_experiment(exp_d, status="promoted", promotion_status="shadow")

        rows = await db.list_disagreement_packets(limit=10, unresolved_only=True, include_consensus=True, recent_limit=50)

        packet_ids = {row["packet_id"] for row in rows}
        self.assertIn("packet_consensus_queue", packet_ids)

    async def test_incomplete_explicit_pair_stays_out_of_review_queue(self):
        base_task = {
            "lane": "creative",
            "track": "paired",
            "prompt": "Write a manifesto for patience in the voice of a subway announcement system.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_on",
            "generation_protocol": "paired_native",
            "packet_id": "packet_incomplete_pair",
        }
        exp_c = await db.create_experiment({**base_task, "packet_role_id": "genesis", "packet_primary": True}, status="promoted")
        await db.insert_artifact(exp_c, "Genesis-only artifact")
        await db.insert_score(exp_c, "muse", {"composite": 8.0})
        await db.insert_score(exp_c, "athena", {"composite": 7.8})
        await db.insert_score(exp_c, "apollo", {"composite": 7.9})
        await db.finalize_experiment(exp_c, status="promoted", promotion_status="shadow")

        rows = await db.list_disagreement_packets(limit=10, unresolved_only=True, include_consensus=True, recent_limit=50)

        packet_ids = {row["packet_id"] for row in rows}
        self.assertNotIn("packet_incomplete_pair", packet_ids)

    async def test_list_assembling_packets_surfaces_incomplete_explicit_pair(self):
        base_task = {
            "lane": "creative",
            "track": "paired",
            "prompt": "Write a manifesto for patience in the voice of a subway announcement system.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_on",
            "generation_protocol": "paired_native",
            "packet_id": "packet_assembling_pair",
        }
        exp_c = await db.create_experiment({**base_task, "packet_role_id": "genesis", "packet_primary": True}, status="promoted")
        await db.insert_artifact(exp_c, "Genesis-only artifact")
        await db.insert_score(exp_c, "muse", {"composite": 8.0})
        await db.insert_score(exp_c, "athena", {"composite": 7.8})
        await db.insert_score(exp_c, "apollo", {"composite": 7.9})
        await db.finalize_experiment(exp_c, status="promoted", promotion_status="shadow")

        rows = await db.list_assembling_packets(limit=10, recent_limit=50)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["packet_id"], "packet_assembling_pair")
        self.assertEqual(rows[0]["assembly_stage"], "awaiting_pair_member")
        self.assertFalse(rows[0]["has_complete_panel"])
        self.assertEqual(rows[0]["assembly_health"], "active")

    async def test_list_assembling_packets_marks_old_incomplete_pairs_as_stalled(self):
        base_task = {
            "lane": "creative",
            "track": "paired",
            "prompt": "Write a manifesto for patience in the voice of a subway announcement system.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_on",
            "generation_protocol": "paired_native",
            "packet_id": "packet_stalled_pair",
        }
        exp_c = await db.create_experiment({**base_task, "packet_role_id": "genesis", "packet_primary": True}, status="promoted")
        await db.insert_artifact(exp_c, "Genesis-only artifact")
        await db.insert_score(exp_c, "muse", {"composite": 8.0})
        await db.finalize_experiment(exp_c, status="promoted", promotion_status="shadow")
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE experiments SET created_at = '2000-01-01 00:00:00' WHERE packet_id = ?",
                ("packet_stalled_pair",),
            )
            await conn.commit()

        rows = await db.list_assembling_packets(limit=10, recent_limit=50)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["packet_id"], "packet_stalled_pair")
        self.assertEqual(rows[0]["assembly_health"], "stalled")

    async def test_discarded_packet_resolution_removes_stalled_packet_from_queue(self):
        base_task = {
            "lane": "creative",
            "track": "paired",
            "prompt": "Write a manifesto for patience in the voice of a subway announcement system.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_on",
            "generation_protocol": "paired_native",
            "packet_id": "packet_discardable_stalled_pair",
        }
        exp_c = await db.create_experiment({**base_task, "packet_role_id": "genesis", "packet_primary": True}, status="running")
        await db.insert_artifact(exp_c, "Genesis-only artifact")
        await db.insert_score(exp_c, "muse", {"composite": 8.0})
        await db.finalize_experiment(exp_c, status="running", promotion_status="candidate")
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE experiments SET created_at = '2000-01-01 00:00:00' WHERE packet_id = ?",
                ("packet_discardable_stalled_pair",),
            )
            await conn.commit()

        before = await db.list_assembling_packets(limit=10, recent_limit=50)
        self.assertEqual(before[0]["packet_id"], "packet_discardable_stalled_pair")

        resolution = await db.save_packet_resolution(
            "packet_discardable_stalled_pair",
            resolution="discarded_failure",
            rationale="Packet stalled and should not linger in the live queue.",
            reviewer="ethan",
            metadata={"source": "test"},
        )

        self.assertEqual(resolution["resolution"], "discarded_failure")
        after = await db.list_assembling_packets(limit=10, recent_limit=50)
        packet_ids = {row["packet_id"] for row in after}
        self.assertNotIn("packet_discardable_stalled_pair", packet_ids)
        graveyard = await db.list_packet_resolutions(limit=10)
        self.assertEqual(graveyard[0]["packet_id"], "packet_discardable_stalled_pair")
        self.assertEqual(graveyard[0]["resolution"], "discarded_failure")
        record = await db.get_experiment_by_id(exp_c)
        self.assertEqual(record["status"], "error")

    async def test_primary_panel_ready_packet_enters_review_queue_without_apollo(self):
        base_task = {
            "lane": "creative",
            "track": "paired",
            "prompt": "Write a psalm from an exhausted battery to the night-shift nurse who keeps asking for one more hour.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_on",
            "generation_protocol": "paired_native",
            "packet_id": "packet_primary_ready_pair",
        }
        exp_c = await db.create_experiment({**base_task, "packet_role_id": "genesis", "packet_primary": True}, status="promoted")
        exp_d = await db.create_experiment({**base_task, "packet_role_id": "theron", "packet_primary": False}, status="promoted")
        await db.insert_artifact(exp_c, "Genesis artifact")
        await db.insert_artifact(exp_d, "Theron artifact")
        await db.insert_score(exp_c, "muse", {"composite": 8.0})
        await db.insert_score(exp_d, "muse", {"composite": 8.2})
        await db.insert_score(exp_c, "athena", {"composite": 7.9})
        await db.insert_score(exp_d, "athena", {"composite": 7.8})
        await db.finalize_experiment(exp_c, status="promoted", promotion_status="shadow")
        await db.finalize_experiment(exp_d, status="promoted", promotion_status="shadow")

        rows = await db.list_disagreement_packets(limit=10, unresolved_only=True, include_consensus=True, recent_limit=50)
        packet_ids = {row["packet_id"] for row in rows}

        self.assertIn("packet_primary_ready_pair", packet_ids)
        packet = next(row for row in rows if row["packet_id"] == "packet_primary_ready_pair")
        self.assertTrue(packet["has_review_ready_panel"])
        self.assertFalse(packet["has_complete_panel"])
        self.assertEqual(packet["missing_judges"], ["apollo"])

        assembling = await db.list_assembling_packets(limit=10, recent_limit=50)
        assembling_ids = {row["packet_id"] for row in assembling}
        self.assertNotIn("packet_primary_ready_pair", assembling_ids)

    async def test_new_experiments_default_to_current_epoch(self):
        record = await db.get_experiment_by_id(self.exp_a)
        self.assertEqual(record["epoch"], db.CURRENT_EXPERIMENT_EPOCH)

    async def test_init_db_backfills_missing_epoch_as_legacy(self):
        await db.finalize_experiment(self.exp_a, status="promoted", promotion_status="shadow")
        async with db.connect() as conn:
            await conn.execute("UPDATE experiments SET epoch = NULL WHERE id = ?", (self.exp_a,))
            await conn.commit()

        db._db_initialized = False
        db._initialized_db_path = None
        await db.init_db()

        record = await db.get_experiment_by_id(self.exp_a)
        self.assertEqual(record["epoch"], db.LEGACY_EXPERIMENT_EPOCH)

    async def test_init_db_backfills_council_diagnosis_actions_as_prompt_rules(self):
        async with db.connect() as conn:
            await conn.execute(
                """
                INSERT INTO council_actions (
                    action_type, title, status, lane, prompt_family, payload
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "prompt_diagnosis_refinement",
                    "Make audience explicit",
                    "adopted",
                    "creative",
                    "personification",
                    '{"action": "Name the actual recipient before drafting."}',
                ),
            )
            await conn.commit()

        db._db_initialized = False
        db._initialized_db_path = None
        await db.init_db()

        rules = await db.list_prompt_rules(limit=5)
        self.assertEqual(rules[0]["rule_key"], "diagnosis::make_audience_explicit")
        self.assertEqual(rules[0]["status"], "candidate")
        self.assertEqual(rules[0]["scope_claim"], "family_specific")
        self.assertEqual(rules[0]["payload"]["council_action_id"], 1)

    async def test_comparison_review_backfills_rule_evidence_human_signal_uniformly(self):
        slice_row = await db.record_rule_evidence_slice({
            "rule_key": "diagnosis::make_audience_explicit",
            "title": "Make audience explicit",
            "scope_claim": "family_specific",
            "rule_type": "audience_grounding",
            "rule_text": "Name the actual recipient before drafting.",
            "lane": "creative",
            "prompt_family": "personification",
            "model_family": "genesis",
            "experiment_type": "raw_vs_compiled",
            "packet_id": "packet_test_disagreement",
            "experiment_id": self.exp_b,
            "compared_experiment_id": self.exp_a,
            "human_signal": "unreviewed",
            "evaluator_signal": "helped",
        })
        self.assertEqual(slice_row["human_signal"], "unreviewed")

        await db.save_comparison_review(
            "packet_test_disagreement",
            preferred_experiment_id=self.exp_b,
            rationale="The compiled side understood the audience better.",
            metadata={"review_verdict": "preferred"},
        )

        rows = await db.list_rule_evidence_slices(limit=5)
        self.assertEqual(rows[0]["human_signal"], "helped")
        self.assertEqual(rows[0]["human_signal_attribution_method"], "uniform")

    async def test_both_bad_review_backfills_rule_evidence_as_mixed(self):
        await db.record_rule_evidence_slice({
            "rule_key": "diagnosis::make_audience_explicit",
            "title": "Make audience explicit",
            "scope_claim": "family_specific",
            "rule_type": "audience_grounding",
            "rule_text": "Name the actual recipient before drafting.",
            "lane": "creative",
            "prompt_family": "personification",
            "model_family": "genesis",
            "experiment_type": "raw_vs_compiled",
            "packet_id": "packet_test_disagreement",
            "experiment_id": self.exp_b,
            "compared_experiment_id": self.exp_a,
            "human_signal": "unreviewed",
            "evaluator_signal": "helped",
        })

        await db.save_comparison_review(
            "packet_test_disagreement",
            preferred_experiment_id=None,
            rationale="Both outputs failed despite the compiler.",
            metadata={"review_verdict": "both_bad"},
        )

        rows = await db.list_rule_evidence_slices(limit=5)
        self.assertEqual(rows[0]["human_signal"], "mixed")

    async def test_rule_promotion_proposals_stay_dry_run_but_recommend_candidate_promotion(self):
        await db.record_rule_evidence_slice({
            "rule_key": "diagnosis::make_audience_explicit",
            "title": "Make audience explicit",
            "scope_claim": "family_specific",
            "rule_type": "audience_grounding",
            "rule_text": "Name the actual recipient before drafting.",
            "lane": "creative",
            "prompt_family": "personification",
            "model_family": "genesis",
            "experiment_type": "raw_vs_compiled",
            "packet_id": "packet_test_disagreement",
            "experiment_id": self.exp_b,
            "compared_experiment_id": self.exp_a,
            "human_signal": "helped",
            "evaluator_signal": "helped",
        })

        report = await db.compute_rule_promotion_proposals({
            "provisional_packets": 1,
            "provisional_families": 1,
        })

        proposal = report["proposals"][0]
        self.assertEqual(report["mode"], "dry_run")
        self.assertEqual(proposal["rule_key"], "diagnosis::make_audience_explicit")
        self.assertEqual(proposal["current_status"], "candidate")
        self.assertEqual(proposal["proposed_status"], "provisional")
        self.assertEqual(proposal["recommendation"], "promote")

        rules = await db.list_prompt_rules(limit=5)
        self.assertEqual(rules[0]["status"], "candidate")

    async def _record_characterization_slices(self, *, human_signals, evaluator_signal="helped"):
        for index, human_signal in enumerate(human_signals):
            await db.record_rule_evidence_slice({
                "rule_key": "diagnosis::make_audience_explicit",
                "title": "Make audience explicit",
                "scope_claim": "family_specific",
                "rule_type": "audience_grounding",
                "rule_text": "Name the actual recipient before drafting.",
                "lane": "creative",
                "prompt_family": "personification",
                "model_family": "genesis",
                "experiment_type": "raw_vs_compiled",
                "packet_id": f"packet_characterization_{index}",
                "human_signal": human_signal,
                "evaluator_signal": evaluator_signal,
            })

    async def test_rule_characterization_reports_aligned_when_panel_and_humans_agree(self):
        await self._record_characterization_slices(human_signals=["helped"] * 5)

        report = await db.compute_rule_promotion_proposals()

        proposal = report["proposals"][0]
        self.assertEqual(proposal["characterization"], "aligned")
        rules = await db.list_prompt_rules(limit=5)
        self.assertEqual(rules[0]["characterization"], "aligned")

    async def test_rule_characterization_reports_divergent_when_panel_and_humans_disagree(self):
        await self._record_characterization_slices(human_signals=["hurt", "hurt", "hurt", "hurt", "helped"])

        report = await db.compute_rule_promotion_proposals()

        self.assertEqual(report["proposals"][0]["characterization"], "divergent")

    async def test_rule_characterization_reports_llm_specific_when_humans_neutral(self):
        await self._record_characterization_slices(human_signals=["helped", "helped", "helped", "hurt", "hurt", "hurt"])

        report = await db.compute_rule_promotion_proposals()

        self.assertEqual(report["proposals"][0]["characterization"], "llm_specific")

    async def test_rule_characterization_reports_insufficient_data_below_human_threshold(self):
        await self._record_characterization_slices(human_signals=["helped", "hurt"])

        report = await db.compute_rule_promotion_proposals()

        self.assertEqual(report["proposals"][0]["characterization"], "insufficient_data")

    async def test_rule_promotion_suppresses_dual_constraint_fail_slice(self):
        async with db.connect() as conn:
            await conn.execute(
                "UPDATE experiments SET status = 'constraint_fail' WHERE id IN (?, ?)",
                (self.exp_a, self.exp_b),
            )
            await conn.commit()
        await db.record_rule_evidence_slice({
            "rule_key": "diagnosis::make_audience_explicit",
            "title": "Make audience explicit",
            "scope_claim": "family_specific",
            "rule_type": "audience_grounding",
            "rule_text": "Name the actual recipient before drafting.",
            "lane": "creative",
            "prompt_family": "personification",
            "model_family": "genesis",
            "experiment_type": "raw_vs_compiled",
            "packet_id": "packet_test_disagreement",
            "experiment_id": self.exp_b,
            "compared_experiment_id": self.exp_a,
            "human_signal": "unreviewed",
            "evaluator_signal": "helped",
        })

        report = await db.compute_rule_promotion_proposals({
            "provisional_packets": 1,
            "provisional_families": 1,
        })

        metrics = report["proposals"][0]["metrics"]
        self.assertEqual(metrics["total_slices"], 1)
        self.assertEqual(metrics["eligible_slices"], 0)
        self.assertEqual(metrics["suppressed_dual_constraint_fail"], 1)
        self.assertEqual(metrics["support_packets"], 0)
        self.assertEqual(metrics["evaluator_helped"], 0)
        self.assertEqual(report["proposals"][0]["recommendation"], "hold")

    async def test_rule_promotion_proposals_flag_active_rules_with_hurt_rate(self):
        rule = await db.record_rule_evidence_slice({
            "rule_key": "diagnosis::make_audience_explicit",
            "title": "Make audience explicit",
            "scope_claim": "family_specific",
            "rule_type": "audience_grounding",
            "rule_text": "Name the actual recipient before drafting.",
            "lane": "creative",
            "prompt_family": "personification",
            "model_family": "genesis",
            "experiment_type": "raw_vs_compiled",
            "packet_id": "packet_test_disagreement",
            "experiment_id": self.exp_b,
            "compared_experiment_id": self.exp_a,
            "human_signal": "hurt",
            "evaluator_signal": "hurt",
        })
        async with db.connect() as conn:
            await conn.execute("UPDATE prompt_rules SET status = 'active' WHERE id = ?", (rule["rule_id"],))
            await conn.commit()

        report = await db.compute_rule_promotion_proposals({
            "hurt_flag_min": 1,
            "hurt_flag_rate": 0.4,
        })

        proposal = report["proposals"][0]
        self.assertEqual(proposal["current_status"], "active")
        self.assertEqual(proposal["proposed_status"], "active")
        self.assertEqual(proposal["recommendation"], "watch")

    async def test_rule_promotion_proposals_flag_candidate_rules_with_hurt_rate(self):
        await db.record_rule_evidence_slice({
            "rule_key": "diagnosis::make_audience_explicit",
            "title": "Make audience explicit",
            "scope_claim": "family_specific",
            "rule_type": "audience_grounding",
            "rule_text": "Name the actual recipient before drafting.",
            "lane": "creative",
            "prompt_family": "personification",
            "model_family": "genesis",
            "experiment_type": "raw_vs_compiled",
            "packet_id": "packet_test_disagreement",
            "experiment_id": self.exp_b,
            "compared_experiment_id": self.exp_a,
            "human_signal": "hurt",
            "evaluator_signal": "hurt",
        })

        report = await db.compute_rule_promotion_proposals({
            "hurt_flag_min": 1,
            "hurt_flag_rate": 0.4,
        })

        proposal = report["proposals"][0]
        self.assertEqual(proposal["current_status"], "candidate")
        self.assertEqual(proposal["proposed_status"], "candidate")
        self.assertEqual(
            proposal["recommendation"],
            "watch",
            "candidate rules accumulating decisive negative human signal must be"
            " visible, not silently held",
        )


if __name__ == "__main__":
    unittest.main()
