from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:
    from telethon import TelegramClient
    from telethon.sessions import StringSession
except Exception:  # pragma: no cover - optional dependency during local setup
    TelegramClient = None
    StringSession = None


load_dotenv()

THERON_GATEWAY_MODE = os.getenv("THERON_GATEWAY_MODE", "mock").strip().lower()
THERON_BOT_NAME = os.getenv("THERON_BOT_NAME", "Theron")
THERON_GATEWAY_MODEL = os.getenv("THERON_GATEWAY_MODEL", "theron/latest")
THERON_GATEWAY_VERSION = "0.1.0"
THERON_TELEGRAM_API_ID = os.getenv("THERON_TELEGRAM_API_ID", "").strip()
THERON_TELEGRAM_API_HASH = os.getenv("THERON_TELEGRAM_API_HASH", "").strip()
THERON_TELEGRAM_SESSION_STRING = os.getenv("THERON_TELEGRAM_SESSION_STRING", "").strip()
THERON_TELEGRAM_SESSION_FILE = os.getenv("THERON_TELEGRAM_SESSION_FILE", "").strip()
THERON_TELEGRAM_TIMEOUT_SECONDS = int(os.getenv("THERON_TELEGRAM_TIMEOUT_SECONDS", "90"))


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = Field(default=THERON_GATEWAY_MODEL)
    messages: list[ChatMessage]
    max_completion_tokens: int | None = Field(default=1000)
    temperature: float | None = None


class _Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    candidates = [text.strip()]
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        candidates.append(text[start:end].strip())
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except Exception:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _coerce_gateway_payload(payload: dict[str, Any]) -> dict[str, Any]:
    artifact = payload.get("artifact")
    if not isinstance(artifact, str) or not artifact.strip():
        raise ValueError("Theron payload must contain a non-empty artifact string.")
    process_trace = payload.get("process_trace")
    if process_trace is None:
        process_trace = {}
    if not isinstance(process_trace, dict):
        raise ValueError("process_trace must be an object when provided.")
    process_trace.setdefault("provider", "theron")
    process_trace.setdefault("transport", THERON_GATEWAY_MODE)
    process_trace.setdefault("gateway_version", THERON_GATEWAY_VERSION)
    return {
        "artifact": artifact.strip(),
        "process_trace": process_trace,
    }


def _extract_prompt_bundle(messages: list[ChatMessage]) -> dict[str, str]:
    system_parts = [msg.content.strip() for msg in messages if msg.role == "system" and msg.content.strip()]
    user_parts = [msg.content.strip() for msg in messages if msg.role == "user" and msg.content.strip()]
    return {
        "system": "\n\n".join(system_parts).strip(),
        "user": "\n\n".join(user_parts).strip(),
    }


def _build_mock_payload(prompt_bundle: dict[str, str]) -> dict[str, Any]:
    user_prompt = prompt_bundle.get("user") or "No user prompt was provided."
    clipped_prompt = user_prompt[:320].strip()
    artifact = (
        f"{THERON_BOT_NAME} mock artifact\n\n"
        f"Prompt excerpt:\n{clipped_prompt}\n\n"
        "This response came from the local Theron gateway scaffold running in mock mode."
    )
    return {
        "artifact": artifact,
        "process_trace": {
            "provider": "theron",
            "transport": "mock",
            "response_mode": "gateway_mock",
            "strategy_notes": "Mock response generated locally because Telegram transport is not enabled yet.",
            "drafts_considered": 1,
            "rejection_reasons": [],
        },
    }


def _build_telegram_request(prompt_bundle: dict[str, str]) -> str:
    system = prompt_bundle.get("system") or "Return valid JSON only."
    user = prompt_bundle.get("user") or ""
    return (
        "THERON LAB REQUEST\n"
        f"system_instruction:\n{system}\n\n"
        "Return valid JSON only in this shape:\n"
        "{\n"
        '  "artifact": "<string>",\n'
        '  "process_trace": {\n'
        '    "drafts_considered": <number>,\n'
        '    "rejection_reasons": ["<string>"],\n'
        '    "strategy_notes": "<string>"\n'
        "  }\n"
        "}\n\n"
        f"USER REQUEST:\n{user}"
    )


def _telegram_ready() -> bool:
    if TelegramClient is None or StringSession is None:
        return False
    if not THERON_TELEGRAM_API_ID or not THERON_TELEGRAM_API_HASH:
        return False
    return bool(THERON_TELEGRAM_SESSION_STRING or THERON_TELEGRAM_SESSION_FILE)


def _build_telegram_session():
    if THERON_TELEGRAM_SESSION_STRING:
        return StringSession(THERON_TELEGRAM_SESSION_STRING)
    if THERON_TELEGRAM_SESSION_FILE:
        return THERON_TELEGRAM_SESSION_FILE
    raise RuntimeError("No Telegram session configured for Theron gateway.")


class TheronTransport:
    async def generate(self, prompt_bundle: dict[str, str]) -> dict[str, Any]:
        raise NotImplementedError


class MockTheronTransport(TheronTransport):
    async def generate(self, prompt_bundle: dict[str, str]) -> dict[str, Any]:
        return _build_mock_payload(prompt_bundle)


class TelegramTheronTransport(TheronTransport):
    def _build_client(self):
        if not _telegram_ready():
            raise RuntimeError(
                "Telegram transport is not configured. Set THERON_TELEGRAM_API_ID, "
                "THERON_TELEGRAM_API_HASH, and either THERON_TELEGRAM_SESSION_STRING "
                "or THERON_TELEGRAM_SESSION_FILE."
            )
        return TelegramClient(
            _build_telegram_session(),
            int(THERON_TELEGRAM_API_ID),
            THERON_TELEGRAM_API_HASH,
        )

    async def generate(self, prompt_bundle: dict[str, str]) -> dict[str, Any]:
        request_text = _build_telegram_request(prompt_bundle)
        async with self._build_client() as client:
            async with client.conversation(THERON_BOT_NAME, timeout=THERON_TELEGRAM_TIMEOUT_SECONDS) as conversation:
                await conversation.send_message(request_text)
                reply = await conversation.get_response()
        payload = _extract_json_object(getattr(reply, "raw_text", "") or getattr(reply, "text", "") or "")
        if payload is None:
            raise ValueError("Theron reply did not contain valid JSON.")
        return payload


def _get_transport() -> TheronTransport:
    if THERON_GATEWAY_MODE == "mock":
        return MockTheronTransport()
    if THERON_GATEWAY_MODE == "telegram":
        return TelegramTheronTransport()
    raise RuntimeError(f"Unsupported THERON_GATEWAY_MODE '{THERON_GATEWAY_MODE}'.")


app = FastAPI(title="Theron Gateway", version=THERON_GATEWAY_VERSION)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": THERON_GATEWAY_MODE,
        "bot_name": THERON_BOT_NAME,
        "model": THERON_GATEWAY_MODEL,
        "telegram_ready": _telegram_ready(),
    }


@app.post("/v1/chat/completions")
async def chat_completions(payload: ChatCompletionRequest) -> dict[str, Any]:
    prompt_bundle = _extract_prompt_bundle(payload.messages)
    if not prompt_bundle["user"]:
        raise HTTPException(status_code=400, detail="Theron gateway requires at least one user message.")

    started = time.time()
    transport = _get_transport()
    try:
        theron_payload = await transport.generate(prompt_bundle)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Theron transport failed: {exc}") from exc

    try:
        normalized = _coerce_gateway_payload(theron_payload)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    normalized["raw_meta"] = {
        "gateway_mode": THERON_GATEWAY_MODE,
        "latency_ms": int((time.time() - started) * 1000),
    }
    content = json.dumps(normalized)
    usage = _Usage(
        prompt_tokens=max(1, len(prompt_bundle["user"]) // 4),
        completion_tokens=max(1, len(content) // 4),
    )
    usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
    return {
        "id": f"chatcmpl-theron-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": payload.model or THERON_GATEWAY_MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": usage.model_dump(),
    }


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("THERON_GATEWAY_HOST", "127.0.0.1")
    port = int(os.getenv("THERON_GATEWAY_PORT", "8000"))
    uvicorn.run("scripts.theron_gateway:app", host=host, port=port, reload=False)
