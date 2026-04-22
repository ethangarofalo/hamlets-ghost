import asyncio
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("OPENAI_API_KEY", "test-key")

import agents
import database as db
import server


class BackendHardeningTests(unittest.IsolatedAsyncioTestCase):
    def test_get_client_supports_openclaw_aliases(self):
        self.assertIs(agents._get_client("openclaw"), agents.OPENCLAW_CLIENT)
        self.assertIs(agents._get_client("openclaw_gateway"), agents.OPENCLAW_CLIENT)

    def test_get_client_supports_theron_aliases(self):
        self.assertIs(agents._get_client("theron"), agents.THERON_CLIENT)
        self.assertIs(agents._get_client("theron_gateway"), agents.THERON_CLIENT)
        self.assertIsNone(agents._get_client("openclaw_local"))
        self.assertIsNone(agents._get_client("hermes_cli"))

    def test_describe_experiment_models_reports_openclaw_backend(self):
        original_role_config = agents.ROLE_CONFIG.copy()
        self.addCleanup(setattr, agents, "ROLE_CONFIG", original_role_config)
        agents.ROLE_CONFIG = {
            **agents.ROLE_CONFIG,
            "athena": ("ATHENA", "openclaw", "openclaw/latest"),
        }
        original_athena_backend = agents.ATHENA_BACKEND
        original_athena_model = agents.ATHENA_MODEL
        self.addCleanup(setattr, agents, "ATHENA_BACKEND", original_athena_backend)
        self.addCleanup(setattr, agents, "ATHENA_MODEL", original_athena_model)
        agents.ATHENA_BACKEND = "openclaw"
        agents.ATHENA_MODEL = "openclaw/latest"

        payload = agents.describe_experiment_models()

        self.assertIn('"backend": "openclaw"', payload)
        self.assertIn('"model": "openclaw/latest"', payload)

    def test_muse_and_athena_defaults_have_distinct_personalities(self):
        self.assertIn("first reader of possibility", agents.MUSE_DEFAULT_SYSTEM)
        self.assertIn("Your job is to interrogate", agents.ATHENA_DEFAULT_SYSTEM)
        self.assertNotEqual(agents.MUSE_DEFAULT_SYSTEM, agents.ATHENA_DEFAULT_SYSTEM)

    def test_apollo_default_system_is_distinct_from_athena(self):
        self.assertIn("outside reader", agents.APOLLO_DEFAULT_SYSTEM)
        self.assertIn("reader-experience rubric", agents.APOLLO_DEFAULT_SYSTEM)
        self.assertIn("recipient-experience rubric", agents.APOLLO_BUSINESS_DEFAULT_SYSTEM)
        self.assertIn("outside recipient", agents.APOLLO_BUSINESS_DEFAULT_SYSTEM)
        self.assertNotEqual(agents.APOLLO_DEFAULT_SYSTEM, agents.ATHENA_DEFAULT_SYSTEM)
        self.assertNotEqual(agents.APOLLO_BUSINESS_DEFAULT_SYSTEM, agents.ATHENA_BUSINESS_DEFAULT_SYSTEM)

    def test_apollo_defaults_to_independent_panel(self):
        self.assertTrue(agents.APOLLO_SHADOW_ENABLED)
        self.assertTrue(agents.APOLLO_INDEPENDENT)
        self.assertNotEqual((agents.APOLLO_BACKEND, agents.APOLLO_MODEL), (agents.ATHENA_BACKEND, agents.ATHENA_MODEL))
        self.assertEqual(agents.JUDGE_PANEL_VERSION, "muse_athena_apollo_v1_independent")

    def test_theron_default_system_is_distinct_from_genesis(self):
        self.assertIn("You are THERON", agents.THERON_DEFAULT_SYSTEM)
        self.assertIn("not to imitate Genesis", agents.THERON_DEFAULT_SYSTEM)
        self.assertNotEqual(agents.THERON_SYSTEM, agents.GENESIS_SYSTEM)

    async def test_get_theron_provider_status_reports_health_when_reachable(self):
        with patch.object(agents, "THERON_GENERATION_ENABLED", True), \
             patch.object(agents, "THERON_BACKEND", "theron_gateway"), \
             patch.object(agents, "THERON_MODEL", "theron/latest"), \
             patch.object(agents, "THERON_BASE_URL", "http://127.0.0.1:8000/v1"), \
             patch.object(agents, "THERON_HEALTH_URL", "http://127.0.0.1:8000/health"), \
             patch.object(agents, "_probe_http_health", return_value={"status": "ok", "mode": "telegram"}):
            payload = await agents.get_theron_provider_status()

        self.assertTrue(payload["reachable"])
        self.assertEqual(payload["gateway_status"]["mode"], "telegram")

    async def test_get_theron_provider_status_reports_error_when_unreachable(self):
        with patch.object(agents, "THERON_GENERATION_ENABLED", True), \
             patch.object(agents, "THERON_BACKEND", "theron_gateway"), \
             patch.object(agents, "THERON_MODEL", "theron/latest"), \
             patch.object(agents, "THERON_BASE_URL", "http://127.0.0.1:8000/v1"), \
             patch.object(agents, "THERON_HEALTH_URL", "http://127.0.0.1:8000/health"), \
             patch.object(agents, "_probe_http_health", side_effect=OSError("connection refused")):
            payload = await agents.get_theron_provider_status()

        self.assertFalse(payload["reachable"])
        self.assertIn("connection refused", payload["error"])

    async def test_get_theron_provider_status_reports_local_openclaw_agent(self):
        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(b"Agents:\n- main (default)\n", b"")),
        )

        with patch.object(agents, "THERON_GENERATION_ENABLED", True), \
             patch.object(agents, "THERON_BACKEND", "openclaw_local"), \
             patch.object(agents, "THERON_OPENCLAW_AGENT_ID", "main"), \
             patch.object(agents, "THERON_OPENCLAW_BIN", "/tmp/openclaw"), \
             patch.object(agents, "os") as mock_os, \
             patch.object(agents.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)):
            mock_os.path.exists.return_value = True
            payload = await agents.get_theron_provider_status()

        self.assertTrue(payload["reachable"])
        self.assertEqual(payload["gateway_status"]["mode"], "openclaw_local")

    async def test_get_apollo_provider_status_reports_local_hermes_cli(self):
        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(b"Hermes OK\n", b"")),
        )

        with patch.object(agents, "APOLLO_SHADOW_ENABLED", True), \
             patch.object(agents, "APOLLO_BACKEND", "hermes_cli"), \
             patch.object(agents, "APOLLO_MODEL", "nous/hermes-3"), \
             patch.object(agents, "APOLLO_HERMES_PROVIDER", "nous"), \
             patch.object(agents, "APOLLO_HERMES_BIN", "/tmp/hermes"), \
             patch.object(agents, "os") as mock_os, \
             patch.object(agents.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)):
            mock_os.path.exists.return_value = True
            payload = await agents.get_apollo_provider_status()

        self.assertTrue(payload["reachable"])
        self.assertEqual(payload["gateway_status"]["mode"], "hermes_cli")

    async def test_get_apollo_provider_status_reports_local_openclaw_agent(self):
        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(b"Agents:\n- main (default)\n", b"")),
        )

        with patch.object(agents, "APOLLO_SHADOW_ENABLED", True), \
             patch.object(agents, "APOLLO_BACKEND", "openclaw_local"), \
             patch.object(agents, "APOLLO_MODEL", "openclaw/latest"), \
             patch.object(agents, "THERON_OPENCLAW_AGENT_ID", "main"), \
             patch.object(agents, "THERON_OPENCLAW_BIN", "/tmp/openclaw"), \
             patch.object(agents, "os") as mock_os, \
             patch.object(agents.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)):
            mock_os.path.exists.return_value = True
            payload = await agents.get_apollo_provider_status()

        self.assertTrue(payload["reachable"])
        self.assertTrue(payload["independent"])
        self.assertEqual(payload["gateway_status"]["mode"], "openclaw_local")

    async def test_generate_text_via_hermes_cli_strips_session_wrapper(self):
        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(
                b"\n\xe2\x95\xad\xe2\x94\x80 \xe2\x9a\x95 Hermes \xe2\x94\x80\xe2\x95\xae\nREADY\n\nsession_id: abc123\n",
                b"",
            )),
        )

        with patch.object(agents, "APOLLO_HERMES_BIN", "/tmp/hermes"), \
             patch.object(agents.os.path, "exists", return_value=True), \
             patch.object(agents.os, "access", return_value=True), \
             patch.object(agents, "APOLLO_HERMES_PROVIDER", "auto"), \
             patch.object(agents, "APOLLO_MODEL", "nous/hermes-3"), \
             patch.object(agents.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)):
            text, response = await agents._generate_text_via_hermes_cli("apollo", "system", "user")

        self.assertEqual(text, "READY")
        self.assertIn("session_id:", response.raw_text)

    async def test_generate_text_via_hermes_cli_raises_on_provider_error_banner(self):
        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(
                b"\xe2\x9a\xa0\xef\xb8\x8f  API call failed (attempt 1/3): NotFoundError [HTTP 404]\n"
                b"   \xf0\x9f\x94\x8c Provider: nous  Model: nous/hermes-3\n"
                b"   \xf0\x9f\x8c\x90 Endpoint: https://inference-api.nousresearch.com/v1\n"
                b"   \xf0\x9f\x93\x9d Error: HTTP 404: Model 'nous/hermes-3' not found.\n"
                b"\xe2\x9d\x8c Non-retryable client error (HTTP 404). Aborting.\n"
                b"session_id: abc123\n",
                b"",
            )),
        )

        with patch.object(agents, "APOLLO_HERMES_BIN", "/tmp/hermes"), \
             patch.object(agents.os.path, "exists", return_value=True), \
             patch.object(agents.os, "access", return_value=True), \
             patch.object(agents, "APOLLO_HERMES_PROVIDER", "nous"), \
             patch.object(agents, "APOLLO_MODEL", "nous/hermes-3"), \
             patch.object(agents.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)):
            with self.assertRaises(RuntimeError) as ctx:
                await agents._generate_text_via_hermes_cli("apollo", "system", "user")

        self.assertIn("Model 'nous/hermes-3' not found", str(ctx.exception))

    async def test_generate_text_via_openclaw_local_parses_payload_text(self):
        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(
                b'{"payloads":[{"text":"READY"}],"meta":{"agentMeta":{"lastCallUsage":{"input":12,"output":3}}}}',
                b"",
            )),
        )

        with patch.object(agents, "THERON_OPENCLAW_BIN", "/tmp/openclaw"), \
             patch.object(agents, "THERON_OPENCLAW_AGENT_ID", "main"), \
             patch.object(agents.os.path, "exists", return_value=True), \
             patch.object(agents.os, "access", return_value=True), \
             patch.object(agents.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)):
            text, response = await agents._generate_text_via_openclaw_local("theron", "say ready")

        self.assertEqual(text, "READY")
        self.assertEqual(response.usage.prompt_tokens, 12)
        self.assertEqual(response.usage.completion_tokens, 3)

    async def test_generate_text_via_openclaw_local_falls_back_to_stderr_payload(self):
        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(
                b"",
                b'{"payloads":[{"text":"READY"}],"meta":{"agentMeta":{"lastCallUsage":{"input":9,"output":2}}}}',
            )),
        )

        with patch.object(agents, "THERON_OPENCLAW_BIN", "/tmp/openclaw"), \
             patch.object(agents, "THERON_OPENCLAW_AGENT_ID", "main"), \
             patch.object(agents.os.path, "exists", return_value=True), \
             patch.object(agents.os, "access", return_value=True), \
             patch.object(agents.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)):
            text, response = await agents._generate_text_via_openclaw_local("theron", "say ready")

        self.assertEqual(text, "READY")
        self.assertEqual(response.usage.prompt_tokens, 9)
        self.assertEqual(response.usage.completion_tokens, 2)

    async def test_generate_text_via_openclaw_local_extracts_json_from_noisy_output(self):
        process = SimpleNamespace(
            returncode=0,
            communicate=AsyncMock(return_value=(
                b"warning: transport resumed\n"
                b'{"payloads":[{"text":"READY"}],"meta":{"agentMeta":{"lastCallUsage":{"input":7,"output":1}}}}\n'
                b"session_id: abc123\n",
                b"",
            )),
        )

        with patch.object(agents, "THERON_OPENCLAW_BIN", "/tmp/openclaw"), \
             patch.object(agents, "THERON_OPENCLAW_AGENT_ID", "main"), \
             patch.object(agents.os.path, "exists", return_value=True), \
             patch.object(agents.os, "access", return_value=True), \
             patch.object(agents.asyncio, "create_subprocess_exec", AsyncMock(return_value=process)):
            text, response = await agents._generate_text_via_openclaw_local("theron", "say ready")

        self.assertEqual(text, "READY")
        self.assertEqual(response.usage.prompt_tokens, 7)
        self.assertEqual(response.usage.completion_tokens, 1)

    async def asyncSetUp(self):
        self.original_runner_task = server._runner_task
        self.original_stop_event = server._stop_event
        self.original_runner_transition_lock = server._runner_transition_lock
        server._runner_task = None
        server._stop_event = asyncio.Event()
        server._runner_transition_lock = asyncio.Lock()

    async def asyncTearDown(self):
        if server._runner_task and not server._runner_task.done():
            server._runner_task.cancel()
            try:
                await server._runner_task
            except asyncio.CancelledError:
                pass
        server._runner_task = self.original_runner_task
        server._stop_event = self.original_stop_event
        server._runner_transition_lock = self.original_runner_transition_lock

    async def test_stop_waits_for_runner_completion(self):
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"

        async def fake_runner():
            await server._stop_event.wait()
            await asyncio.sleep(0.05)

        server._runner_task = asyncio.create_task(fake_runner())

        with patch.object(server.db, "update_state", AsyncMock()):
            response = await server.stop_lab(x_admin_token="secret-token")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(server._runner_task.done(), "stop should wait for the runner task to finish")

    async def test_start_refuses_second_live_runner(self):
        os.environ["LAB_ADMIN_TOKEN"] = "secret-token"

        async def fake_runner():
            await server._stop_event.wait()

        server._runner_task = asyncio.create_task(fake_runner())

        response = await server.start_lab(payload={"n_experiments": 1}, x_admin_token="secret-token")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.body, b'{"status":"already_running"}')

    async def test_generate_text_retries_transient_failures(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="hello world"))]
        )
        create = AsyncMock(side_effect=[RuntimeError("transient failure"), response])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        with patch.object(agents, "_get_role_config", return_value=("openai", "demo-model")), patch.object(agents, "_get_client", return_value=client):
            text, raw_response = await agents._generate_text(
                role="genesis",
                system="system",
                user_content="user",
                max_tokens=64,
            )

        self.assertEqual(text, "hello world")
        self.assertIs(raw_response, response)
        self.assertEqual(create.await_count, 2, "transient provider failures should be retried")

    async def test_generate_text_propagates_cancellation_without_retry(self):
        create = AsyncMock(side_effect=asyncio.CancelledError())
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        with patch.object(agents, "_get_role_config", return_value=("openai", "demo-model")), patch.object(agents, "_get_client", return_value=client):
            with self.assertRaises(asyncio.CancelledError):
                await agents._generate_text(
                    role="genesis",
                    system="system",
                    user_content="user",
                    max_tokens=64,
                )

        self.assertEqual(create.await_count, 1, "cancellation should stop immediately without retrying")

    async def test_database_connect_enforces_foreign_keys_busy_timeout_and_wal(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        original_db_path = db.DB_PATH
        db.DB_PATH = str(Path(temp_dir.name) / "hardening.db")
        self.addCleanup(setattr, db, "DB_PATH", original_db_path)

        await db.init_db()

        async with db.connect() as conn:
            foreign_keys_cursor = await conn.execute("PRAGMA foreign_keys")
            busy_timeout_cursor = await conn.execute("PRAGMA busy_timeout")
            journal_mode_cursor = await conn.execute("PRAGMA journal_mode")
            foreign_keys = await foreign_keys_cursor.fetchone()
            busy_timeout = await busy_timeout_cursor.fetchone()
            journal_mode = await journal_mode_cursor.fetchone()

        self.assertEqual(foreign_keys[0], 1)
        self.assertGreaterEqual(busy_timeout[0], 1000)
        self.assertEqual(str(journal_mode[0]).lower(), "wal")

    def test_load_prompt_override_skips_contaminated_genesis_prompt(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        db_path = Path(temp_dir.name) / "creativity_lab.db"

        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE prompt_versions (role TEXT, content TEXT, created_at TEXT)")
            conn.execute(
                "INSERT INTO prompt_versions (role, content, created_at) VALUES (?, ?, ?)",
                (
                    "genesis",
                    "You are GENESIS, a creative generator in the AI Creativity Lab.\n\n"
                    "You must respond with valid JSON in this exact format:\n"
                    "{\"artifact\": \"...\"}\n\n"
                    "You are GENESIS, the generator in the AI Creativity Lab.\n"
                    "Your job in this step is to produce a serious first draft, not a finished artifact.\n"
                    "You are a rigorous Socratic interlocutor in the AI Creativity Lab.\n"
                    "You are GENESIS, revising a draft after Socratic questioning.\n",
                    "2026-04-02 13:21:45",
                ),
            )
            conn.execute(
                "INSERT INTO prompt_versions (role, content, created_at) VALUES (?, ?, ?)",
                (
                    "genesis",
                    "You are GENESIS, a creative generator in the AI Creativity Lab.\n\n"
                    "Your role is to produce creative artifacts in response to prompts with constraints.\n\n"
                    "You must respond with valid JSON in this exact format:\n"
                    "{\"artifact\": \"...\", \"process_trace\": {\"strategy_notes\": \"...\"}}\n",
                    "2026-04-01 13:07:20",
                ),
            )
            conn.commit()

        fake_path = SimpleNamespace()
        fake_path.exists = lambda: True
        fake_path.with_name = lambda _name: db_path

        with patch.object(agents, "Path", return_value=fake_path):
            loaded = agents._load_prompt_override("genesis", "fallback", min_length=50)

        self.assertIn('"artifact"', loaded)
        self.assertNotIn("serious first draft", loaded)
        self.assertNotIn("rigorous Socratic interlocutor", loaded)

    def test_normalize_genesis_artifact_supports_structured_hero_fields(self):
        artifact = agents._normalize_genesis_artifact(
            {
                "headline": "Hire for performance",
                "subheadline": "Stop rewarding interviews over actual execution.",
                "cta": "See better candidates",
            }
        )

        self.assertEqual(
            artifact,
            "Headline: Hire for performance\n"
            "Subheadline: Stop rewarding interviews over actual execution.\n"
            "CTA: See better candidates",
        )

    async def test_execute_experiment_marks_blank_artifact_invalid_before_scoring(self):
        task = {
            "prompt": "Test prompt",
            "lane": "business",
            "track": "constrained",
            "constraints": ["headline under 10 words"],
        }

        create_experiment = AsyncMock(return_value=321)
        update_state = AsyncMock()
        insert_artifact = AsyncMock()
        update_artifact_process_trace = AsyncMock()
        finalize_experiment = AsyncMock()
        get_state = AsyncMock(
            return_value={
                "total_experiments": 10,
                "kept": 4,
                "discarded": 2,
                "promoted": 1,
                "best_score": 7.5,
                "total_cost": 0.4,
            }
        )

        with patch.object(server, "_resolve_policy_control", AsyncMock(return_value=task)), \
             patch.object(server.db, "create_experiment", create_experiment), \
             patch.object(server.db, "update_state", update_state), \
             patch.object(server.db, "insert_artifact", insert_artifact), \
             patch.object(server.db, "update_artifact_process_trace", update_artifact_process_trace), \
             patch.object(server.db, "finalize_experiment", finalize_experiment), \
             patch.object(server.db, "get_generator_feedback_for_task", AsyncMock(return_value={})), \
             patch.object(server.db, "get_state", get_state), \
             patch.object(server.agents, "run_genesis", AsyncMock(return_value=({"artifact": "   ", "process_trace": {}}, 0.12, False))), \
             patch.object(server.agents, "run_muse", AsyncMock()) as run_muse, \
             patch.object(server.agents, "run_hermes", AsyncMock()) as run_hermes:
            result = await server._execute_experiment(task, iteration=1, consecutive_discards=0)

        self.assertEqual(result["status"], "invalid")
        self.assertFalse(result["keep"])
        self.assertEqual(result["artifact"], "   ")
        run_muse.assert_not_awaited()
        run_hermes.assert_not_awaited()

        process_trace = update_artifact_process_trace.await_args.args[1]
        self.assertEqual(process_trace["artifact_contract_status"], "empty_artifact")
        self.assertEqual(process_trace["generation_failure_reason"], "empty_artifact_from_genesis")
        self.assertEqual(process_trace["orchestration"]["final_outcome"]["reason"], "generation_failure_empty_artifact")

        finalize_kwargs = finalize_experiment.await_args.kwargs
        self.assertEqual(finalize_kwargs["status"], "invalid")
        self.assertTrue(finalize_kwargs["parse_failure"])


if __name__ == "__main__":
    unittest.main()
