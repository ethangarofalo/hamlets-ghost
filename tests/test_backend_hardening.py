import asyncio
import os
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
        server._runner_task = None
        server._stop_event = asyncio.Event()

    async def asyncTearDown(self):
        if server._runner_task and not server._runner_task.done():
            server._runner_task.cancel()
            try:
                await server._runner_task
            except asyncio.CancelledError:
                pass
        server._runner_task = self.original_runner_task
        server._stop_event = self.original_stop_event

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

    async def test_database_connect_enforces_foreign_keys_and_busy_timeout(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        original_db_path = db.DB_PATH
        db.DB_PATH = str(Path(temp_dir.name) / "hardening.db")
        self.addCleanup(setattr, db, "DB_PATH", original_db_path)

        await db.init_db()

        async with db.connect() as conn:
            foreign_keys_cursor = await conn.execute("PRAGMA foreign_keys")
            busy_timeout_cursor = await conn.execute("PRAGMA busy_timeout")
            foreign_keys = await foreign_keys_cursor.fetchone()
            busy_timeout = await busy_timeout_cursor.fetchone()

        self.assertEqual(foreign_keys[0], 1)
        self.assertGreaterEqual(busy_timeout[0], 1000)


if __name__ == "__main__":
    unittest.main()
