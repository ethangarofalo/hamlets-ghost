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

        conn = sqlite3.connect(db_path)
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
        conn.close()

        fake_path = SimpleNamespace()
        fake_path.exists = lambda: True
        fake_path.with_name = lambda _name: db_path

        with patch.object(agents, "Path", return_value=fake_path):
            loaded = agents._load_prompt_override("genesis", "fallback", min_length=50)

        self.assertIn('"artifact"', loaded)
        self.assertNotIn("serious first draft", loaded)
        self.assertNotIn("rigorous Socratic interlocutor", loaded)


if __name__ == "__main__":
    unittest.main()
