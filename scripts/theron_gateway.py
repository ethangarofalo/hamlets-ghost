from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


load_dotenv()

THERON_GATEWAY_MODE = os.getenv("THERON_GATEWAY_MODE", "mock").strip().lower()
THERON_BOT_NAME = os.getenv("THERON_BOT_NAME", "Theron")
THERON_GATEWAY_MODEL = os.getenv("THERON_GATEWAY_MODEL", "theron/latest")
THERON_GATEWAY_VERSION = "0.1.0"


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


class TheronTransport:
    async def generate(self, prompt_bundle: dict[str, str]) -> dict[str, Any]:
        raise NotImplementedError


class MockTheronTransport(TheronTransport):
    async def generate(self, prompt_bundle: dict[str, str]) -> dict[str, Any]:
        return _build_mock_payload(prompt_bundle)


class TelegramTheronTransport(TheronTransport):
    async def generate(self, prompt_bundle: dict[str, str]) -> dict[str, Any]:
        raise NotImplementedError(
            "Telegram transport is not wired yet. Keep the gateway in mock mode until the Telegram bridge is implemented."
        )


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
        "telegram_ready": THERON_GATEWAY_MODE == "telegram" and False,
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
