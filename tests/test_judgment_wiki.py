import json
import tempfile
import unittest
from pathlib import Path

import database as db
import judgment_wiki


class JudgmentWikiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test_judgment_wiki.db")
        self.wiki_root = Path(self.temp_dir.name) / "wiki"
        self.taxonomy_root = Path(self.temp_dir.name) / "taxonomy"
        self.calibration_root = Path(self.temp_dir.name) / "calibration"
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db._db_initialized = False
        await db.init_db()

    async def asyncTearDown(self):
        db.DB_PATH = self.original_db_path
        db._db_initialized = False
        self.temp_dir.cleanup()

    def _compile_kwargs(self):
        return {
            "output_dir": self.wiki_root,
            "taxonomy_dir": self.taxonomy_root,
            "calibration_dir": self.calibration_root,
        }

    async def _create_reviewed_packet(
        self,
        base_task,
        packet_id,
        *,
        reason_tags=None,
        reason_tag_attribution=None,
        reason_tag_evidence=None,
        preferred="theron",
        genesis_backend="openai",
        genesis_model="gpt-4.1-mini",
        theron_backend="openclaw_local",
        theron_model="openclaw/latest",
    ):
        """Helper: create a two-member packet with scores and a human review."""
        genesis_id = await db.create_experiment(
            {**base_task, "packet_id": packet_id, "packet_role_id": "genesis", "packet_primary": True},
            status="promoted",
        )
        theron_id = await db.create_experiment(
            {**base_task, "packet_id": packet_id, "packet_role_id": "theron", "packet_primary": False},
            status="promoted",
        )
        role_routing = {
            "genesis": {"backend": genesis_backend, "model": genesis_model},
            "theron": {"backend": theron_backend, "model": theron_model},
        }
        await db.insert_artifact(
            genesis_id,
            f"Genesis artifact ({packet_id})",
            source_context={
                "generator_role_id": "genesis",
                "generator_provider": genesis_backend,
                "role_routing": role_routing,
            },
        )
        await db.insert_artifact(
            theron_id,
            f"Theron artifact ({packet_id})",
            source_context={
                "generator_role_id": "theron",
                "generator_provider": theron_backend,
                "role_routing": role_routing,
            },
        )
        for exp_id in (genesis_id, theron_id):
            composite = 8.4 if exp_id == theron_id else 7.8
            await db.insert_score(exp_id, "muse", {"composite": composite})
            await db.insert_score(exp_id, "athena", {"composite": composite - 0.2})
            await db.insert_score(exp_id, "apollo", {"composite": composite - 0.5})
        await db.finalize_experiment(genesis_id, status="promoted", promotion_status="shadow")
        await db.finalize_experiment(theron_id, status="promoted", promotion_status="shadow")
        preferred_id = theron_id if preferred == "theron" else genesis_id
        normalized_attribution = {
            "winner": list((reason_tag_attribution or {}).get("winner") or []),
            "loser": list((reason_tag_attribution or {}).get("loser") or []),
            "both": list((reason_tag_attribution or {}).get("both") or []),
            "unattributed": list((reason_tag_attribution or {}).get("unattributed") or []),
        }
        if reason_tags and not any(normalized_attribution.values()):
            normalized_attribution["winner"] = list(reason_tags)
        flattened_reason_tags = []
        for key in ("winner", "loser", "both", "unattributed"):
            for tag in normalized_attribution[key]:
                if tag not in flattened_reason_tags:
                    flattened_reason_tags.append(tag)
        await db.save_comparison_review(
            packet_id,
            preferred_experiment_id=preferred_id,
            rationale="Test review.",
            reviewer="ethan",
            review_channel="test",
            metadata={
                "reason_tags": flattened_reason_tags,
                "reason_tag_attribution": normalized_attribution,
                "reason_tag_evidence": list(reason_tag_evidence or []),
            },
        )
        return genesis_id, theron_id

    async def test_compile_wiki_creates_all_outputs(self):
        base_task = {
            "lane": "creative",
            "track": "paired_external",
            "prompt": "Write a prayer from the perspective of a dying programming language.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_off",
            "generation_protocol": "theron_paired_native",
        }
        await self._create_reviewed_packet(base_task, "packet_wiki_test", reason_tags=["real_pathos", "symbolic_pressure"])
        await self._create_reviewed_packet(base_task, "packet_wiki_test_two", reason_tags=["real_pathos", "symbolic_pressure"])
        await self._create_reviewed_packet(base_task, "packet_wiki_test_three", reason_tags=["real_pathos", "symbolic_pressure"])
        await db.add_council_entry({
            "summary": "Theron continues to carry the emotional center in personification.",
            "strongest_finding": "Human review keeps rewarding real pathos over safer coherence.",
            "research_memo": "The lab should keep pressure on personification prompts that create judge disagreement.",
            "recommendation": "Run another personification batch with business contrast.",
            "evaluator_trust_assessment": "Muse is currently too coherence-biased here.",
            "prompt_diagnosis_recommendations": [
                {"title": "Make audience explicit", "action": "Name the actual recipient before drafting."}
            ],
            "evaluator_education_recommendations": [
                {"title": "Teach recurrence conditionally", "action": "Compare repetition in speeches against letters."}
            ],
            "contrast_set_candidates": [
                {"title": "Speech vs resignation note", "why_now": "The same device should be judged differently by audience and occasion."}
            ],
        })

        result = await judgment_wiki.compile_wiki(**self._compile_kwargs())

        self.assertEqual(result["packets"], 3)
        self.assertEqual(result["reviews"], 3)

        # Core wiki pages
        self.assertTrue((self.wiki_root / "packets" / "packet_wiki_test.md").exists())
        self.assertTrue((self.wiki_root / "models" / "theron.md").exists())
        self.assertTrue((self.wiki_root / "evaluators" / "apollo.md").exists())
        self.assertTrue((self.wiki_root / "lessons" / "personification-theron.md").exists())
        self.assertTrue((self.wiki_root / "memos").exists())
        self.assertTrue((self.wiki_root / "lint" / "latest.md").exists())
        self.assertTrue(any((self.wiki_root / "weekly").iterdir()))

        # No taxonomy or calibration inside wiki
        self.assertFalse((self.wiki_root / "taxonomy").exists())
        self.assertFalse((self.wiki_root / "calibration").exists())

        # Emergent concept page
        concept_page = self.wiki_root / "concepts" / "real-pathos.md"
        self.assertTrue(concept_page.exists())
        concept_text = concept_page.read_text()
        self.assertIn("real pathos", concept_text)
        self.assertIn("emergent", concept_text)

        # Provenance/status split on seeded concept
        antithetical_text = (self.wiki_root / "concepts" / "antithetical-formula.md").read_text()
        self.assertIn("provenance: seeded", antithetical_text)
        self.assertIn("status: tentative", antithetical_text)

        # Provenance/status split on emergent concept
        self.assertIn("provenance: emergent", concept_text)
        # Status should be epistemic, not provenance
        self.assertNotIn("status: emergent", concept_text)
        self.assertTrue(
            "status: human-confirmed" in concept_text
            or "status: emerging" in concept_text
            or "status: repeated" in concept_text
        )

        # Seeded concept pages
        self.assertTrue((self.wiki_root / "concepts" / "showing-not-telling.md").exists())
        self.assertIn("quality-signal", (self.wiki_root / "concepts" / "showing-not-telling.md").read_text())
        self.assertTrue((self.wiki_root / "concepts" / "keyword-presence-bias.md").exists())
        self.assertIn("evaluator-failure", (self.wiki_root / "concepts" / "keyword-presence-bias.md").read_text())

        # Packet page content
        packet_text = (self.wiki_root / "packets" / "packet_wiki_test.md").read_text()
        self.assertIn("Artifact A", packet_text)
        self.assertIn("Theron artifact", packet_text)

        # Evaluator page includes failure modes
        evaluator_text = (self.wiki_root / "evaluators" / "apollo.md").read_text()
        self.assertIn("Known Failure Modes", evaluator_text)
        self.assertIn("Keyword Presence Bias", evaluator_text)
        self.assertIn("Contradictions Under Review", evaluator_text)
        self.assertIn("Refinement History", evaluator_text)

        # Lesson page with refinement history and related concepts
        lesson_text = (self.wiki_root / "lessons" / "personification-theron.md").read_text()
        self.assertIn("favoring Theron", lesson_text)
        self.assertIn("Refinement History", lesson_text)
        self.assertIn("Related Concepts", lesson_text)
        self.assertIn("Contradictions", lesson_text)
        self.assertIn("supporting packet(s)", lesson_text)

        # Family page with anti-patterns and quality signals
        family_text = (self.wiki_root / "families" / "personification.md").read_text()
        self.assertIn("Anti-Patterns Observed", family_text)
        self.assertIn("Quality Signals Observed", family_text)
        self.assertIn("Explicit Contradictions", family_text)

        # Memo and lint pages
        memo_files = list((self.wiki_root / "memos").glob("*.md"))
        self.assertTrue(memo_files)
        memo_text = memo_files[0].read_text()
        self.assertIn("Research Memo", memo_text)
        self.assertIn("Prompt Diagnosis Refinements", memo_text)
        self.assertIn("Evaluator Curriculum Refinements", memo_text)
        self.assertIn("Contrast Set Candidates", memo_text)
        lint_text = (self.wiki_root / "lint" / "latest.md").read_text()
        self.assertIn("Judgment Wiki Lint", lint_text)
        self.assertIn("Council Memo Coverage", lint_text)

        # Index
        index_text = (self.wiki_root / "index.md").read_text()
        self.assertIn("taste memory entries", index_text)
        self.assertIn("Anti-Patterns", index_text)
        self.assertIn("Quality Signals", index_text)
        self.assertIn("Evaluator Failure Modes", index_text)
        self.assertIn("Filed Memos", index_text)
        self.assertIn("Lint", index_text)

        # Taxonomy JSON at top-level taxonomy/
        taxonomy_path = self.taxonomy_root / "compiled_taxonomy.json"
        self.assertTrue(taxonomy_path.exists())
        taxonomy = json.loads(taxonomy_path.read_text())
        self.assertIn("promoted", taxonomy)
        self.assertIn("merged", taxonomy)
        self.assertIn("emergent", taxonomy)
        self.assertIn("seeded", taxonomy)
        self.assertIn("promotion_criteria", taxonomy)
        self.assertEqual(taxonomy["summary"]["seeded"], 17)
        emergent_tags = [e["tag"] for e in taxonomy["emergent"]]
        self.assertIn("real_pathos", emergent_tags)

        # Calibration at top-level calibration/
        calibration_index = self.calibration_root / "index.md"
        self.assertTrue(calibration_index.exists())
        calibration_text = calibration_index.read_text()
        self.assertIn("Evaluator Calibration", calibration_text)
        self.assertIn("Muse", calibration_text)

    async def test_refinement_history_accumulates_across_compiles(self):
        """Refinement history should preserve entries from previous compilations."""
        base_task = {
            "lane": "creative",
            "track": "paired_external",
            "prompt": "Test prompt.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_off",
            "generation_protocol": "theron_paired_native",
        }
        await self._create_reviewed_packet(base_task, "pkt_1", reason_tags=["tag_a"])

        # First compile
        await judgment_wiki.compile_wiki(**self._compile_kwargs())
        lesson_path = self.wiki_root / "lessons" / "personification-theron.md"
        evaluator_path = self.wiki_root / "evaluators" / "muse.md"
        self.assertTrue(lesson_path.exists())
        self.assertTrue(evaluator_path.exists())
        text1 = lesson_path.read_text()
        evaluator_text_1 = evaluator_path.read_text()
        history_section = text1.split("## Refinement History")[1]
        evaluator_history_1 = evaluator_text_1.split("## Refinement History")[1]
        entries_1 = [line.strip() for line in history_section.strip().splitlines() if line.strip().startswith("- ")]
        evaluator_entries_1 = [line.strip() for line in evaluator_history_1.strip().splitlines() if line.strip().startswith("- ")]
        self.assertEqual(len(entries_1), 1)
        self.assertEqual(len(evaluator_entries_1), 1)

        # Add another packet and recompile
        await self._create_reviewed_packet(base_task, "pkt_2", reason_tags=["tag_a"])
        await judgment_wiki.compile_wiki(**self._compile_kwargs())
        text2 = lesson_path.read_text()
        evaluator_text_2 = evaluator_path.read_text()
        history_section_2 = text2.split("## Refinement History")[1]
        evaluator_history_2 = evaluator_text_2.split("## Refinement History")[1]
        entries_2 = [line.strip() for line in history_section_2.strip().splitlines() if line.strip().startswith("- ")]
        evaluator_entries_2 = [line.strip() for line in evaluator_history_2.strip().splitlines() if line.strip().startswith("- ")]
        self.assertGreaterEqual(len(entries_2), 2)
        self.assertGreaterEqual(len(evaluator_entries_2), 2)

    async def test_provenance_states(self):
        """Verify provenance logic: seeded, emergent, merged, promoted."""
        self.assertEqual(
            judgment_wiki.compute_provenance(
                is_seeded=True, evidence_count=0, distinct_prompt_families=0, distinct_model_families=0,
                has_correction_strategy=True, human_confirmed=False,
            ),
            "seeded",
        )
        self.assertEqual(
            judgment_wiki.compute_provenance(
                is_seeded=True, evidence_count=3, distinct_prompt_families=1, distinct_model_families=1,
                has_correction_strategy=True, human_confirmed=True,
            ),
            "merged",
        )
        self.assertEqual(
            judgment_wiki.compute_provenance(
                is_seeded=True, evidence_count=5, distinct_prompt_families=2, distinct_model_families=2,
                has_correction_strategy=True, human_confirmed=True,
            ),
            "promoted",
        )
        self.assertEqual(
            judgment_wiki.compute_provenance(
                is_seeded=False, evidence_count=4, distinct_prompt_families=1, distinct_model_families=1,
                has_correction_strategy=False, human_confirmed=True,
            ),
            "emergent",
        )
        self.assertEqual(
            judgment_wiki.compute_provenance(
                is_seeded=True, evidence_count=5, distinct_prompt_families=2, distinct_model_families=1,
                has_correction_strategy=True, human_confirmed=True,
            ),
            "merged",
        )

    async def test_seeded_concept_promotion_requires_model_family_diversity(self):
        task_personification = {
            "lane": "creative",
            "track": "paired_external",
            "prompt": "Write a prayer from the perspective of a dying programming language.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_off",
            "generation_protocol": "theron_paired_native",
        }
        task_genre = {
            **task_personification,
            "prompt": "Write a eulogy for a startup as if it were a weather report.",
            "family": "genre_mismatch",
        }
        for idx in range(3):
            await self._create_reviewed_packet(
                task_personification,
                f"pkt_model_gate_p_{idx}",
                reason_tags=["antithetical_formula"],
                genesis_backend="openai",
                genesis_model="gpt-4.1-mini",
                theron_backend="openai",
                theron_model="gpt-4o-mini",
            )
        for idx in range(2):
            await self._create_reviewed_packet(
                task_genre,
                f"pkt_model_gate_g_{idx}",
                reason_tags=["antithetical_formula"],
                genesis_backend="openai",
                genesis_model="gpt-4.1-mini",
                theron_backend="openai",
                theron_model="gpt-4o-mini",
            )

        await judgment_wiki.compile_wiki(**self._compile_kwargs())

        concept_text = (self.wiki_root / "concepts" / "antithetical-formula.md").read_text()
        taxonomy = json.loads((self.taxonomy_root / "compiled_taxonomy.json").read_text())

        self.assertIn("provenance: merged", concept_text)
        self.assertIn("distinct_prompt_families: 2", concept_text)
        self.assertIn("distinct_model_families: 1", concept_text)
        promoted_tags = [entry["tag"] for entry in taxonomy["promoted"]]
        self.assertNotIn("antithetical_formula", promoted_tags)
        self.assertEqual(taxonomy["promotion_criteria"]["min_distinct_model_families"], 2)

    async def test_seeded_concept_promotes_with_model_family_diversity(self):
        task_personification = {
            "lane": "creative",
            "track": "paired_external",
            "prompt": "Write a prayer from the perspective of a dying programming language.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_off",
            "generation_protocol": "theron_paired_native",
        }
        task_genre = {
            **task_personification,
            "prompt": "Write a eulogy for a startup as if it were a weather report.",
            "family": "genre_mismatch",
        }
        for idx in range(3):
            await self._create_reviewed_packet(
                task_personification,
                f"pkt_model_promote_p_{idx}",
                reason_tags=["antithetical_formula"],
            )
        for idx in range(2):
            await self._create_reviewed_packet(
                task_genre,
                f"pkt_model_promote_g_{idx}",
                reason_tags=["antithetical_formula"],
            )

        await judgment_wiki.compile_wiki(**self._compile_kwargs())

        concept_text = (self.wiki_root / "concepts" / "antithetical-formula.md").read_text()
        taxonomy = json.loads((self.taxonomy_root / "compiled_taxonomy.json").read_text())

        self.assertIn("provenance: promoted", concept_text)
        self.assertIn("distinct_prompt_families: 2", concept_text)
        self.assertIn("distinct_model_families: 2", concept_text)
        promoted_tags = [entry["tag"] for entry in taxonomy["promoted"]]
        self.assertIn("antithetical_formula", promoted_tags)

    async def test_shared_tags_do_not_count_as_decisive_concept_evidence(self):
        base_task = {
            "lane": "creative",
            "track": "paired_external",
            "prompt": "Write a prayer from the perspective of a dying programming language.",
            "family": "personification",
            "constraints": [],
            "condition": "critique_off",
            "generation_protocol": "theron_paired_native",
        }
        for idx in range(3):
            await self._create_reviewed_packet(
                {**base_task, "prompt": f"{base_task['prompt']} #{idx}"},
                f"packet_attribution_test_{idx}",
                reason_tag_attribution={
                    "winner": ["real_pathos"],
                    "loser": ["generic_reassurance"],
                    "both": ["specific_detail"],
                },
                reason_tag_evidence=[
                    {"tag": "real_pathos", "target": "winner", "excerpt": "I kept praying in a syntax nobody still spoke."},
                    {"tag": "generic_reassurance", "target": "loser", "excerpt": "We understand your frustration and appreciate your patience."},
                    {"tag": "specific_detail", "target": "both", "excerpt": "Both artifacts named the failed export job at 3:17 AM."},
                ],
            )

        await judgment_wiki.compile_wiki(**self._compile_kwargs())

        lesson_text = (self.wiki_root / "lessons" / "personification-theron.md").read_text()
        real_pathos_text = (self.wiki_root / "concepts" / "real-pathos.md").read_text()
        generic_reassurance_text = (self.wiki_root / "concepts" / "generic-reassurance.md").read_text()
        specific_detail_text = (self.wiki_root / "concepts" / "specific-detail.md").read_text()
        packet_text = (self.wiki_root / "packets" / "packet_attribution_test_0.md").read_text()

        self.assertIn("real pathos", lesson_text)
        self.assertNotIn("specific detail", lesson_text)
        self.assertIn("evidence_count: 3", real_pathos_text)
        self.assertIn("evidence_count: 3", generic_reassurance_text)
        self.assertIn("evidence_count: 0", specific_detail_text)
        self.assertIn("winner tags: real_pathos", packet_text)
        self.assertIn("loser tags: generic_reassurance", packet_text)
        self.assertIn("shared tags: specific_detail", packet_text)
        self.assertIn("winner / real pathos", packet_text)
        self.assertIn("loser / generic reassurance", packet_text)
        self.assertIn("kept praying in a syntax nobody still spoke", real_pathos_text.lower())


if __name__ == "__main__":
    unittest.main()
