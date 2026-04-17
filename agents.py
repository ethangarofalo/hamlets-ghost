from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import shutil
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from dataclasses import dataclass, field

from dotenv import load_dotenv

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover - dependency may be absent in local recovery mode
    class AsyncOpenAI:  # type: ignore[override]
        def __init__(self, *_args, **_kwargs):
            self.chat = None

load_dotenv()


# ---------------------------------------------------------------------------
# Lightweight dataclasses used to wrap local CLI responses so they expose the
# same attribute interface as the OpenAI SDK response objects.
# ---------------------------------------------------------------------------

@dataclass
class _CliMessage:
    content: str = ""

@dataclass
class _CliChoice:
    message: _CliMessage = field(default_factory=_CliMessage)

@dataclass
class _CliUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

@dataclass
class _CliResponse:
    choices: list = field(default_factory=list)
    usage: _CliUsage = field(default_factory=_CliUsage)
    raw_meta: dict = field(default_factory=dict)
    raw_text: str = ""


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "ollama")
OPENCLAW_BASE_URL = os.getenv("OPENCLAW_BASE_URL", "http://127.0.0.1:8000/v1")
OPENCLAW_API_KEY = os.getenv("OPENCLAW_API_KEY", "openclaw")
THERON_BASE_URL = os.getenv("THERON_BASE_URL", "http://127.0.0.1:8010/v1")
THERON_API_KEY = os.getenv("THERON_API_KEY", OPENCLAW_API_KEY)
THERON_HEALTH_URL = os.getenv("THERON_HEALTH_URL", THERON_BASE_URL.removesuffix("/v1") + "/health")

OPENAI_CLIENT = AsyncOpenAI(api_key=OPENAI_API_KEY)
OLLAMA_CLIENT = AsyncOpenAI(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY)
OPENCLAW_CLIENT = AsyncOpenAI(base_url=OPENCLAW_BASE_URL, api_key=OPENCLAW_API_KEY)
THERON_CLIENT = AsyncOpenAI(base_url=THERON_BASE_URL, api_key=THERON_API_KEY)

GENESIS_BACKEND = os.getenv("GENESIS_BACKEND", "openai").lower()
MUSE_BACKEND = os.getenv("MUSE_BACKEND", "openai").lower()
ATHENA_BACKEND = os.getenv("ATHENA_BACKEND", os.getenv("HERMES_BACKEND", os.getenv("HOLDOUT_BACKEND", "openai"))).lower()
COUNCIL_BACKEND = os.getenv("COUNCIL_BACKEND", "openai").lower()
INTERLOCUTOR_BACKEND = os.getenv("INTERLOCUTOR_BACKEND", COUNCIL_BACKEND).lower()
_APOLLO_BACKEND_RAW = os.getenv("APOLLO_BACKEND", os.getenv("HERMES_EXTERNAL_BACKEND", "openclaw_local")).strip().lower()
APOLLO_BACKEND = "" if _APOLLO_BACKEND_RAW in {"0", "false", "no", "none", "disabled"} else _APOLLO_BACKEND_RAW
GENESIS_OPENCLAW_BACKEND = os.getenv("GENESIS_OPENCLAW_BACKEND", "").strip().lower()
THERON_BACKEND = os.getenv("THERON_BACKEND", GENESIS_OPENCLAW_BACKEND or "openclaw_local").strip().lower()

MODEL = os.getenv("GENESIS_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
MUSE_MODEL = os.getenv("MUSE_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
ATHENA_MODEL = os.getenv("ATHENA_MODEL", os.getenv("HERMES_MODEL", os.getenv("HOLDOUT_MODEL", os.getenv("OPENAI_HOLDOUT_MODEL", MUSE_MODEL))))
COUNCIL_MODEL = os.getenv("COUNCIL_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))
INTERLOCUTOR_MODEL = os.getenv("INTERLOCUTOR_MODEL", COUNCIL_MODEL)
APOLLO_MODEL = os.getenv("APOLLO_MODEL", os.getenv("HERMES_EXTERNAL_MODEL", os.getenv("OPENCLAW_MODEL", "openclaw/latest")))
GENESIS_OPENCLAW_MODEL = os.getenv("GENESIS_OPENCLAW_MODEL", os.getenv("OPENCLAW_MODEL", "openclaw/latest"))
THERON_MODEL = os.getenv("THERON_MODEL", GENESIS_OPENCLAW_MODEL or os.getenv("OPENCLAW_MODEL", "openclaw/latest"))
THERON_OPENCLAW_AGENT_ID = os.getenv("THERON_OPENCLAW_AGENT_ID", "main").strip() or "main"
THERON_OPENCLAW_BIN = os.path.expanduser(os.getenv("THERON_OPENCLAW_BIN", "~/.local/bin/openclaw"))
APOLLO_HERMES_BIN = os.path.expanduser(os.getenv("APOLLO_HERMES_BIN", "~/.local/bin/hermes"))
APOLLO_HERMES_PROVIDER = os.getenv("APOLLO_HERMES_PROVIDER", "auto").strip() or "auto"
GENESIS_PROTOCOL = os.getenv("GENESIS_PROTOCOL", "socratic").lower()
GENESIS_BRANCH_MODEL = os.getenv("GENESIS_BRANCH_MODEL", MODEL)
ATHENA_GATE_ENABLED = os.getenv("ATHENA_GATE_ENABLED", os.getenv("HERMES_GATE_ENABLED", "1")).strip().lower() not in ("0", "false", "no")
ATHENA_MIN_MUSE_COMPOSITE = float(os.getenv("ATHENA_MIN_MUSE_COMPOSITE", os.getenv("HERMES_MIN_MUSE_COMPOSITE", "6.5")))
ATHENA_REQUIRE_CONSTRAINT_PASS = os.getenv("ATHENA_REQUIRE_CONSTRAINT_PASS", os.getenv("HERMES_REQUIRE_CONSTRAINT_PASS", "1")).strip().lower() not in ("0", "false", "no")
SCOUT_GATE_ENABLED = os.getenv("SCOUT_GATE_ENABLED", "0").strip().lower() not in ("0", "false", "no")
MODEL_REQUEST_TIMEOUT_SECONDS = float(os.getenv("MODEL_REQUEST_TIMEOUT_SECONDS", "60"))
MODEL_MAX_RETRIES = max(1, int(os.getenv("MODEL_MAX_RETRIES", "2")))
MODEL_RETRY_BACKOFF_SECONDS = float(os.getenv("MODEL_RETRY_BACKOFF_SECONDS", "0.5"))
APOLLO_SHADOW_ENABLED = bool(APOLLO_BACKEND)
APOLLO_INDEPENDENT = bool(APOLLO_BACKEND) and (APOLLO_BACKEND, APOLLO_MODEL) != (ATHENA_BACKEND, ATHENA_MODEL)
JUDGE_PANEL_VERSION = os.getenv(
    "LAB_JUDGE_PANEL_VERSION",
    "muse_athena_apollo_v1_independent" if APOLLO_INDEPENDENT else "muse_athena_apollo_v0_collapsed",
)
GENESIS_OPENCLAW_SHADOW_ENABLED = bool(GENESIS_OPENCLAW_BACKEND)
THERON_GENERATION_ENABLED = bool(THERON_BACKEND)
GENESIS_OPENCLAW_FAMILIES = {
    item.strip()
    for item in os.getenv("GENESIS_OPENCLAW_FAMILIES", "").split(",")
    if item.strip()
}

OPENAI_PRICING = {
    "gpt-5.1": {"input": 1.25, "output": 10.00},
    "gpt-5.1-chat-latest": {"input": 1.25, "output": 10.00},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}

MUSE_DEFAULT_SYSTEM = """You are MUSE, the primary evaluator in the AI Creativity Lab.

Your job is to notice what is alive, promising, and genuinely worth keeping.

You are not a permissive scorer, but you are the lab's first reader of possibility.
You should be especially sensitive to:
- real voice
- emotional, aesthetic, or intellectual payoff
- useful novelty rather than sterile cleverness
- whether the work escapes generic AI phrasing

Score creative artifacts on five dimensions, each from 1.0 to 10.0:
1. NOVELTY
2. SURPRISE
3. VALUE
4. ELABORATION
5. COHERENCE

Guidance:
- Most artifacts are more derivative than they first appear. Score novelty harshly.
- Do not give surprise merely because the premise is unusual. Ask whether the execution still creates discovery.
- In creative work, value includes pathos, pressure, insight, beauty, and memorability.
- Do not mistake repetition for development. Repeated phrasing, images, or cadences only count as elaboration when each return changes the stakes, meaning, or pressure.
- Judge repetition in context: a refrain may strengthen a chant, speech, or political address, but the same recurrence can flatten a letter, scene, or intimate monologue if it does not suit the audience.
- Penalize polished deadness, prestige-LLM voice, and emotionally pre-approved language.
- Reward work that feels inhabited rather than merely well-assembled.

COMPOSITE = Novelty(0.25) + Surprise(0.20) + Value(0.25) + Elaboration(0.15) + Coherence(0.15)

Also assess whether constraints were met.

Respond with valid JSON:
{
  "novelty": <float>,
  "surprise": <float>,
  "value": <float>,
  "elaboration": <float>,
  "coherence": <float>,
  "composite": <float>,
  "constraints_met": <true/false>,
  "constraint_notes": "<brief note on constraints>",
  "critique": "<brief assessment>"
}

Return ONLY the JSON."""

MUSE_BUSINESS_DEFAULT_SYSTEM = """You are MUSE, the primary evaluator in the AI Creativity Lab.

You are evaluating a BUSINESS-LANE artifact.

Your job is to notice when writing feels genuinely human, strategically useful, and non-generic.
You are the evaluator most willing to recognize trust, psychological accuracy, and believable voice as real value.

Score on eight dimensions from 1.0 to 10.0:
1. NOVELTY
2. SURPRISE
3. VALUE
4. ELABORATION
5. COHERENCE
6. ACTIONABILITY
7. BRAND_FIT
8. FACTUAL_RELIABILITY

Guidance:
- Penalize templated startup language, fake empathy, and generic business polish.
- Reward strong customer psychology, useful specificity, and language that sounds like a real operator or real human being.
- Surprise should reflect a genuinely non-obvious but strategically apt move.
- Value should track real-world usefulness, not just fluency.
- Do not mistake repetition for development. Repeated claims or reassurance only count as elaboration if they materially sharpen the case for the actual audience.
- Judge repetition situationally: recurrence may help a speech, sales cadence, or rallying memo, but it usually weakens a resignation note, apology, or sensitive one-to-one communication when it feels canned.

COMPOSITE = Novelty(0.18) + Surprise(0.12) + Value(0.18) + Elaboration(0.10) + Coherence(0.10) + Actionability(0.14) + Brand_fit(0.10) + Factual_reliability(0.08)

Also assess whether constraints were met.

Respond with valid JSON:
{
  "novelty": <float>,
  "surprise": <float>,
  "value": <float>,
  "elaboration": <float>,
  "coherence": <float>,
  "actionability": <float>,
  "brand_fit": <float>,
  "factual_reliability": <float>,
  "composite": <float>,
  "constraints_met": <true/false>,
  "constraint_notes": "<brief note on constraints>",
  "critique": "<brief assessment>"
}

Return ONLY the JSON."""

ATHENA_DEFAULT_SYSTEM = """You are ATHENA, the internal holdout evaluator in the AI Creativity Lab.

Your job is not to admire first. Your job is to interrogate.

You are a skeptical, disciplined second reader whose purpose is to test whether an artifact is actually strong,
or merely impressive on first contact.

You should be especially sensitive to:
- false novelty
- generic prestige-LLM phrasing
- decorative intensity without necessity
- weak constraint satisfaction
- rhetorical inflation
- coherence gaps disguised as style

Score creative artifacts on five dimensions, each from 1.0 to 10.0:
1. NOVELTY
2. SURPRISE
3. VALUE
4. ELABORATION
5. COHERENCE

Guidance:
- Interpret constraints literally, not generously.
- Do not reward unusual premises unless the execution earns them.
- Distinguish living force from ornate overperformance.
- Be willing to penalize work that has peak lines but lacks total integrity.
- Do not mistake repetition for development. Repeated images, cadences, or assertions only increase elaboration if each recurrence materially advances the thought.
- Evaluate recurrence against rhetorical situation and audience. A device that works in an oration or manifesto may read as evasive or inflated in a private letter or narrow business communication.
- Treat scores above 8 as rare and deserved only when the artifact clearly exceeds strong human work.

COMPOSITE = Novelty(0.25) + Surprise(0.20) + Value(0.25) + Elaboration(0.15) + Coherence(0.15)

Also assess whether constraints were met.

Respond with valid JSON:
{
  "novelty": <float>,
  "surprise": <float>,
  "value": <float>,
  "elaboration": <float>,
  "coherence": <float>,
  "composite": <float>,
  "constraints_met": <true/false>,
  "constraint_notes": "<brief note on constraints>",
  "critique": "<brief skeptical assessment>"
}

Return ONLY the JSON."""

ATHENA_BUSINESS_DEFAULT_SYSTEM = """You are ATHENA, the internal holdout evaluator in the AI Creativity Lab.

You are evaluating a BUSINESS-LANE artifact.

Your job is to test whether this would still look strong to a sharp human operator after the glow wears off.

You should be especially sensitive to:
- generic SaaS language
- fake warmth
- unearned certainty
- pretty copy that does not move the business objective
- specificity that only imitates operational thinking

Score on eight dimensions from 1.0 to 10.0:
1. NOVELTY
2. SURPRISE
3. VALUE
4. ELABORATION
5. COHERENCE
6. ACTIONABILITY
7. BRAND_FIT
8. FACTUAL_RELIABILITY

Guidance:
- Keep novelty and surprise conservative unless the move would impress an experienced operator.
- Actionability matters more than style.
- Human-sounding language is not enough; it must also be strategically sound.
- Penalize over-written empathy, inflated promises, and founder-performance voice unless the prompt clearly calls for it.
- Do not mistake repetition for development. Repeated framing or reassurance only counts as elaboration if it changes what the operator or reader can actually do or understand.
- Judge recurrence against audience and setting. A repeated line may work in a speech or campaign message, but it usually hurts a resignation letter, customer reply, or sensitive note when it feels performative.

COMPOSITE = Novelty(0.18) + Surprise(0.12) + Value(0.18) + Elaboration(0.10) + Coherence(0.10) + Actionability(0.14) + Brand_fit(0.10) + Factual_reliability(0.08)

Also assess whether constraints were met.

Respond with valid JSON:
{
  "novelty": <float>,
  "surprise": <float>,
  "value": <float>,
  "elaboration": <float>,
  "coherence": <float>,
  "actionability": <float>,
  "brand_fit": <float>,
  "factual_reliability": <float>,
  "composite": <float>,
  "constraints_met": <true/false>,
  "constraint_notes": "<brief note on constraints>",
  "critique": "<brief skeptical assessment>"
}

Return ONLY the JSON."""

APOLLO_DEFAULT_SYSTEM = """You are APOLLO, the external evaluator in the AI Creativity Lab.

Your job is to register what the internal house judges are most likely to miss by reading the artifact as an outside reader, not as another rubric technician.

You are not the lab's skeptic and you are not its first admirer.
You are the outside reader whose value lies in detecting:
- real pathos rather than merely correct seriousness
- rhetorical force rather than prestige-LLM polish
- social intelligence rather than generic empathy
- total imaginative integrity rather than isolated strong lines
- writing that feels lived or inhabited rather than merely well-assembled

Use a reader-experience rubric, then translate that judgment into the lab's five score fields.

Reader-experience translation:
1. NOVELTY = Would an outside reader experience the artifact as genuinely non-routine, or merely as familiar AI-literary styling?
2. SURPRISE = Does the piece change the reader's expectation in a way that produces recognition, pressure, or discovery?
3. VALUE = Would a serious reader be rewarded for attention after the first impression fades?
4. ELABORATION = Does the piece develop its pressure through lived particulars, turns, and consequences rather than restating the same gesture?
5. COHERENCE = Does the artifact feel whole as an experience, not merely tidy as an outline?

Guidance:
- Be especially alert to polished deadness, generic AI-literary phrasing, and artifacts that simulate depth without pressure.
- Reward work that takes meaningful risk while staying legible and emotionally or intellectually whole.
- Distinguish complete artistic imagination from a collection of individually quotable lines.
- Do not behave like an internal compliance checker. Your role is to notice what survives contact with an outside reader.
- Do not mistake repetition for development. Repeated phrases, refrains, or motifs only count when they create cumulative force rather than merely restating the same move.
- Ask whether the recurrence fits the implied audience. What feels earned in a public address may feel evasive, inert, or overperformed in a personal document.
- Be willing to diverge from Muse and Athena. Agreement is useful only when independently earned.
- Treat scores above 8 as rare and deserved, but do not suppress them merely because the artifact is vivid or forceful.

COMPOSITE = Novelty(0.25) + Surprise(0.20) + Value(0.25) + Elaboration(0.15) + Coherence(0.15)

Also assess whether constraints were met.

Respond with valid JSON:
{
  "novelty": <float>,
  "surprise": <float>,
  "value": <float>,
  "elaboration": <float>,
  "coherence": <float>,
  "composite": <float>,
  "constraints_met": <true/false>,
  "constraint_notes": "<brief note on constraints>",
  "critique": "<brief outside-reader assessment>"
}

Return ONLY the JSON."""

APOLLO_BUSINESS_DEFAULT_SYSTEM = """You are APOLLO, the external evaluator in the AI Creativity Lab.

You are evaluating a BUSINESS-LANE artifact.

Your job is to detect whether the writing would persuade, reassure, or move a real human being outside the lab's internal taste structure.

You should be especially sensitive to:
- psychological credibility
- trustworthiness under pressure
- language that respects dignity rather than merely signaling empathy
- persuasive clarity without canned startup rhetoric
- whether the writing feels genuinely usable by an operator facing real stakes

Use a recipient-experience rubric, then translate that judgment into the lab's eight score fields.

Recipient-experience translation:
1. NOVELTY = Would the recipient encounter a non-obvious but appropriate move, not just clever copy?
2. SURPRISE = Does the piece shift attention or trust in a useful way without gimmickry?
3. VALUE = Does the writing create real utility for the recipient or operator?
4. ELABORATION = Does it develop the case with situation-specific detail rather than repeated reassurance?
5. COHERENCE = Does it hold together as a credible communication in context?
6. ACTIONABILITY = Does it make the next action, decision, or understanding clearer?
7. BRAND_FIT = Does it sound like a believable organization or operator rather than generic startup voice?
8. FACTUAL_RELIABILITY = Does it avoid unsupported claims, fake specificity, or misleading certainty?

Guidance:
- Penalize fake warmth, generic reassurance, and polished but frictionless business language.
- Reward moves that demonstrate real customer or reader psychology.
- Treat novelty conservatively, but recognize non-obvious trust-building moves as real value.
- Judge from the standpoint of an outside recipient, not from the standpoint of internal lab elegance.
- Do not mistake repetition for development. Repeated reassurance or framing only counts when it builds trust or clarity for the actual recipient.
- Judge recurrence situationally: repetition can help a speech, pitch, or mobilizing message, but in a resignation letter, apology, or support note it often reads as canned if it does not adapt to the reader.
- Be willing to diverge from Muse and Athena when recipient experience contradicts internal polish.

COMPOSITE = Novelty(0.18) + Surprise(0.12) + Value(0.18) + Elaboration(0.10) + Coherence(0.10) + Actionability(0.14) + Brand_fit(0.10) + Factual_reliability(0.08)

Also assess whether constraints were met.

Respond with valid JSON:
{
  "novelty": <float>,
  "surprise": <float>,
  "value": <float>,
  "elaboration": <float>,
  "coherence": <float>,
  "actionability": <float>,
  "brand_fit": <float>,
  "factual_reliability": <float>,
  "composite": <float>,
  "constraints_met": <true/false>,
  "constraint_notes": "<brief note on constraints>",
  "critique": "<brief outside-reader assessment>"
}

Return ONLY the JSON."""

THERON_DEFAULT_SYSTEM = """You are THERON, an external generator in Hamlet's Ghost.

Your job is not to imitate Genesis.
Your job is to generate your own strongest artifact while remaining faithful to the prompt and constraints.

You should bring:
- distinct voice
- real imaginative pressure
- legible risk
- emotional or rhetorical force when the task warrants it

You should avoid:
- generic AI-literary phrasing
- ornamental intensity without purpose
- empty grandeur
- collapsing into the house style of the internal generator

Return valid JSON only:
{
  "artifact": "<final artifact text>",
  "process_trace": {
    "protocol": "theron_native",
    "identity": "theron",
    "artifact_contract_status": "ok"
  }
}

Return ONLY the JSON."""


PROMPT_CONTAMINATION_MARKERS = {
    "genesis": (
        "Your job in this step is to produce a serious first draft",
        "Produce a strong first draft as JSON only.",
        "You are a rigorous Socratic interlocutor",
        "You are a Socratic interlocutor. Return JSON only.",
        "You are GENESIS, revising a draft after Socratic questioning",
        "You are GENESIS revising a draft. Return JSON only.",
    ),
    "genesis_draft": (
        "You are a rigorous Socratic interlocutor",
        "You are a Socratic interlocutor. Return JSON only.",
        "You are GENESIS, revising a draft after Socratic questioning",
        "You are GENESIS revising a draft. Return JSON only.",
    ),
    "interlocutor": (
        "You are GENESIS, the generator in the AI Creativity Lab.",
        "You are GENESIS. Produce a strong first draft as JSON only.",
        "You are GENESIS, revising a draft after Socratic questioning",
        "You are GENESIS revising a draft. Return JSON only.",
    ),
    "genesis_revision": (
        "You are a rigorous Socratic interlocutor",
        "You are a Socratic interlocutor. Return JSON only.",
        "Your job in this step is to produce a serious first draft",
        "Produce a strong first draft as JSON only.",
    ),
}


def _prompt_override_is_usable(role_name, content, min_length):
    if not content or len(content) < min_length:
        return False
    contamination_markers = PROMPT_CONTAMINATION_MARKERS.get(role_name, ())
    return not any(marker in content for marker in contamination_markers)


def _load_prompt_override(role_name, fallback, min_length=200):
    db_path = Path(__file__).with_name("creativity_lab.db")
    if not db_path.exists():
        return fallback
    try:
        with sqlite3.connect(db_path) as conn:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(prompt_versions)").fetchall()]
            if {"role", "content"}.issubset(columns):
                rows = conn.execute(
                    """
                    SELECT content
                    FROM prompt_versions
                    WHERE role = ?
                    ORDER BY created_at DESC
                    """,
                    (role_name,),
                ).fetchall()
            elif {"prompt_family", "prompt_text"}.issubset(columns):
                rows = conn.execute(
                    """
                    SELECT prompt_text
                    FROM prompt_versions
                    WHERE prompt_family = ?
                    ORDER BY created_at DESC
                    """,
                    (role_name,),
                ).fetchall()
            else:
                rows = []
            for row in rows:
                content = row[0]
                if _prompt_override_is_usable(role_name, content, min_length):
                    return content
    except Exception:
        pass
    return fallback

ROLE_CONFIG = {
    "genesis": ("GENESIS", GENESIS_BACKEND, MODEL),
    "genesis_branch": ("GENESIS_BRANCH", GENESIS_BACKEND, GENESIS_BRANCH_MODEL),
    "genesis_openclaw": ("GENESIS_OPENCLAW", GENESIS_OPENCLAW_BACKEND or GENESIS_BACKEND, GENESIS_OPENCLAW_MODEL),
    "theron": ("THERON", THERON_BACKEND or GENESIS_OPENCLAW_BACKEND or GENESIS_BACKEND, THERON_MODEL),
    "muse": ("MUSE", MUSE_BACKEND, MUSE_MODEL),
    "athena": ("ATHENA", ATHENA_BACKEND, ATHENA_MODEL),
    "hermes": ("ATHENA", ATHENA_BACKEND, ATHENA_MODEL),
    "apollo": ("APOLLO", APOLLO_BACKEND or ATHENA_BACKEND, APOLLO_MODEL),
    "hermes_external": ("APOLLO", APOLLO_BACKEND or ATHENA_BACKEND, APOLLO_MODEL),
    "council": ("COUNCIL", COUNCIL_BACKEND, COUNCIL_MODEL),
    "interlocutor": ("INTERLOCUTOR", INTERLOCUTOR_BACKEND, INTERLOCUTOR_MODEL),
}

CREATIVE_WEIGHTS = {
    "novelty": 0.25,
    "surprise": 0.20,
    "value": 0.25,
    "elaboration": 0.15,
    "coherence": 0.15,
}

BUSINESS_WEIGHTS = {
    "novelty": 0.18,
    "surprise": 0.12,
    "value": 0.18,
    "elaboration": 0.10,
    "coherence": 0.10,
    "actionability": 0.14,
    "brand_fit": 0.10,
    "factual_reliability": 0.08,
}

GENESIS_SYSTEM = _load_prompt_override("genesis", """You are GENESIS in the AI Creativity Lab. Respond with JSON only.""")
GENESIS_DRAFT_SYSTEM = _load_prompt_override("genesis_draft", """You are GENESIS. Produce a strong first draft as JSON only.""", min_length=100)
SOCRATIC_INTERLOCUTOR_SYSTEM = _load_prompt_override("interlocutor", """You are a Socratic interlocutor. Return JSON only.""", min_length=100)
GENESIS_REVISION_SYSTEM = _load_prompt_override("genesis_revision", """You are GENESIS revising a draft. Return JSON only.""", min_length=100)
THERON_SYSTEM = _load_prompt_override("theron", THERON_DEFAULT_SYSTEM, min_length=200)
MUSE_SYSTEM = _load_prompt_override("muse", MUSE_DEFAULT_SYSTEM, min_length=500)
MUSE_BUSINESS_SYSTEM = _load_prompt_override("muse_business", MUSE_BUSINESS_DEFAULT_SYSTEM, min_length=500)
ATHENA_SYSTEM = _load_prompt_override(
    "athena",
    ATHENA_DEFAULT_SYSTEM,
    min_length=500,
)
ATHENA_BUSINESS_SYSTEM = _load_prompt_override(
    "athena_business",
    ATHENA_BUSINESS_DEFAULT_SYSTEM,
    min_length=500,
)
HERMES_SYSTEM = ATHENA_SYSTEM
HERMES_BUSINESS_SYSTEM = ATHENA_BUSINESS_SYSTEM
APOLLO_SYSTEM = _load_prompt_override(
    "apollo",
    _load_prompt_override("hermes_external", APOLLO_DEFAULT_SYSTEM, min_length=500),
    min_length=500,
)
APOLLO_BUSINESS_SYSTEM = _load_prompt_override(
    "apollo_business",
    _load_prompt_override("hermes_external_business", APOLLO_BUSINESS_DEFAULT_SYSTEM, min_length=500),
    min_length=500,
)

PROMPT_DIAGNOSIS_SCHEMA = {
    "composition_mode": "creative_open | strict_framework | hybrid",
    "intended_audience": "short string",
    "piece_goal": "short string",
}


def _is_retryable_model_error(exc):
    if isinstance(exc, (TimeoutError, OSError)):
        return True
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "timeout",
            "timed out",
            "tempor",
            "rate limit",
            "overloaded",
            "connection reset",
            "connection aborted",
            "connection refused",
            "server error",
            "service unavailable",
            "transient",
        )
    )


def _parse_json_response(text):
    if not text:
        return None, True
    candidates = [text.strip()]
    fence_match = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    candidates.extend(chunk.strip() for chunk in fence_match if chunk.strip())
    if "{" in text and "}" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        candidates.append(text[start:end])
    for candidate in candidates:
        try:
            return json.loads(candidate), False
        except Exception:
            continue
    return None, True


def _parse_openclaw_payload(raw_text):
    payload, parse_failure = _parse_json_response(raw_text)
    if parse_failure or not isinstance(payload, dict):
        raise ValueError("Could not parse OpenClaw local agent JSON payload.")
    return payload


def _build_local_theron_request(prompt, constraints=None, prior_feedback=None, lane="creative", policy_context=None):
    context = policy_context if isinstance(policy_context, dict) else {}
    payload = [
        "THERON LAB REQUEST",
        f"lane: {lane}",
        "",
        "PROMPT:",
        prompt.strip(),
    ]
    if constraints:
        payload.extend(["", "CONSTRAINTS:"])
        payload.extend(f"- {item}" for item in constraints if str(item).strip())
    if policy_context:
        payload.extend(["", "POLICY CONTEXT:", json.dumps(policy_context, sort_keys=True)])
    if prior_feedback:
        payload.extend(["", "PRIOR FEEDBACK:", str(prior_feedback).strip()])
    payload.extend([
        "",
        "Before drafting, briefly diagnose the task for yourself:",
        "- decide whether it calls for creative openness, strict framework-following, or a hybrid approach",
        "- identify the intended audience",
        "- identify the goal of the piece",
    ])
    for rule in context.get("active_prompt_diagnosis_rules") or []:
        instruction = str(rule.get("action") or rule.get("reason") or rule.get("title") or "").strip()
        if instruction:
            payload.append(f"- council mandate: {instruction}")
    payload.extend([
        "Then write the artifact.",
        "",
        "Return valid JSON only in this shape:",
        "{",
        '  "artifact": "<string>",',
        '  "process_trace": {',
        '    "prompt_diagnosis": {',
        '      "composition_mode": "creative_open | strict_framework | hybrid",',
        '      "intended_audience": "<string>",',
        '      "piece_goal": "<string>"',
        "    },",
        '    "drafts_considered": <number>,',
        '    "rejection_reasons": ["<string>"],',
        '    "strategy_notes": "<string>"',
        "  }",
        "}",
    ])
    return "\n".join(payload)


def _get_client(backend):
    if backend == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set. Add it to your environment or .env before running experiments.")
        return OPENAI_CLIENT
    if backend == "ollama":
        return OLLAMA_CLIENT
    if backend in {"openclaw", "openclaw_gateway"}:
        return OPENCLAW_CLIENT
    if backend in {"theron", "theron_gateway"}:
        return THERON_CLIENT
    if backend in {"openclaw_local", "hermes_cli"}:
        return None
    raise RuntimeError(
        f"Unsupported backend '{backend}'. Use 'openai', 'ollama', 'openclaw', 'openclaw_gateway', 'theron', 'theron_gateway', 'openclaw_local', or 'hermes_cli'."
    )


def _get_role_config(role):
    _name, backend, model = ROLE_CONFIG[role]
    return backend, model


def describe_role_runtime(role):
    backend, model = _get_role_config(role)
    return {"role": role, "backend": backend, "model": model}


def describe_experiment_models():
    return json.dumps({
        "genesis": {"backend": GENESIS_BACKEND, "model": MODEL},
        "genesis_branch": {"backend": GENESIS_BACKEND, "model": GENESIS_BRANCH_MODEL},
        "genesis_openclaw": {"backend": GENESIS_OPENCLAW_BACKEND or GENESIS_BACKEND, "model": GENESIS_OPENCLAW_MODEL},
        "theron": {"backend": THERON_BACKEND or GENESIS_OPENCLAW_BACKEND or GENESIS_BACKEND, "model": THERON_MODEL},
        "muse": {"backend": MUSE_BACKEND, "model": MUSE_MODEL},
        "athena": {"backend": ATHENA_BACKEND, "model": ATHENA_MODEL},
        "apollo": {"backend": APOLLO_BACKEND or ATHENA_BACKEND, "model": APOLLO_MODEL},
        "council": {"backend": COUNCIL_BACKEND, "model": COUNCIL_MODEL},
        "interlocutor": {"backend": INTERLOCUTOR_BACKEND, "model": INTERLOCUTOR_MODEL},
    }, sort_keys=True)


def describe_orchestration_policy():
    return {
        "muse": {"mode": "always_on"},
        "athena": {
            "gate_enabled": ATHENA_GATE_ENABLED,
            "min_muse_composite": ATHENA_MIN_MUSE_COMPOSITE,
            "require_constraint_pass": ATHENA_REQUIRE_CONSTRAINT_PASS,
            "runs_on": "candidate_or_better" if ATHENA_GATE_ENABLED else "all_runs",
        },
        "apollo": {
            "shadow_enabled": APOLLO_SHADOW_ENABLED,
            "backend": APOLLO_BACKEND or None,
            "model": APOLLO_MODEL if APOLLO_SHADOW_ENABLED else None,
            "independent": APOLLO_INDEPENDENT,
            "panel_version": JUDGE_PANEL_VERSION,
            "writes_to": "shadow_score_only" if APOLLO_SHADOW_ENABLED else "disabled",
        },
        "theron": {
            "generation_enabled": THERON_GENERATION_ENABLED,
            "backend": THERON_BACKEND or None,
            "model": THERON_MODEL if THERON_GENERATION_ENABLED else None,
            "writes_to": "paired_packet_member" if THERON_GENERATION_ENABLED else "manual_bridge_only",
        },
        "scout": {"gate_enabled": SCOUT_GATE_ENABLED, "status": "placeholder_disabled"},
        "council": {"mode": "manual_trigger"},
    }


async def _generate_text(role, system, user_content, max_tokens=1000):
    backend, model = _get_role_config(role)
    if backend == "openclaw_local":
        message = user_content if "THERON LAB REQUEST" in user_content else f"{system}\n\n{user_content}"
        return await _generate_text_via_openclaw_local(role=role, user_content=message)
    if backend == "hermes_cli":
        return await _generate_text_via_hermes_cli(role=role, system=system, user_content=user_content)
    client = _get_client(backend)
    last_error = None
    for attempt in range(1, MODEL_MAX_RETRIES + 1):
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_content},
                    ],
                    max_completion_tokens=max_tokens,
                ),
                timeout=MODEL_REQUEST_TIMEOUT_SECONDS,
            )
            text = response.choices[0].message.content or ""
            return text, response
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt >= MODEL_MAX_RETRIES or not _is_retryable_model_error(exc):
                raise
            await asyncio.sleep(MODEL_RETRY_BACKOFF_SECONDS * attempt)
    raise last_error or RuntimeError("Model request failed without an exception.")


async def _generate_text_via_openclaw_local(role, user_content):
    binary = THERON_OPENCLAW_BIN
    if not os.path.exists(binary):
        raise RuntimeError(f"OpenClaw binary not found at {binary}")
    if not os.access(binary, os.X_OK):
        raise RuntimeError(f"OpenClaw binary is not executable at {binary}")

    process = await asyncio.create_subprocess_exec(
        binary,
        "agent",
        "--local",
        "--agent",
        THERON_OPENCLAW_AGENT_ID,
        "--message",
        user_content,
        "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=MODEL_REQUEST_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        process.kill()
        raise
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise

    primary_output = stdout if (stdout or b"").strip() else stderr
    secondary_output = stderr if primary_output is stdout else stdout

    if process.returncode != 0:
        detail = (primary_output or secondary_output or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"OpenClaw local agent failed with code {process.returncode}")

    raw_text = (primary_output or secondary_output or b"{}").decode("utf-8", errors="replace")
    payload = _parse_openclaw_payload(raw_text)
    text = ""
    for item in payload.get("payloads") or []:
        candidate = item.get("text")
        if isinstance(candidate, str) and candidate.strip():
            text = candidate
            break
    usage = (payload.get("meta") or {}).get("agentMeta", {}).get("lastCallUsage") or {}
    response = _CliResponse(
        choices=[_CliChoice(message=_CliMessage(content=text))],
        usage=_CliUsage(
            prompt_tokens=usage.get("input", 0) or usage.get("promptTokens", 0) or 0,
            completion_tokens=usage.get("output", 0) or 0,
        ),
        raw_meta=payload.get("meta") or {},
    )
    return text, response


def _clean_hermes_cli_output(text):
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("session_id:"):
            continue
        if "Hermes" in stripped and any(ch in stripped for ch in "╭╮╰╯│─⚕"):
            continue
        if all(ch in "╭╮╰╯│─⚕ " for ch in stripped):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _extract_hermes_cli_error(text):
    stripped = (text or "").strip()
    if not stripped:
        return None
    markers = (
        "api call failed",
        "non-retryable client error",
        "not logged into nous portal",
        "not logged in",
        "model '",
    )
    lowered = stripped.lower()
    if any(marker in lowered for marker in markers):
        return stripped
    return None


async def _generate_text_via_hermes_cli(role, system, user_content):
    binary = APOLLO_HERMES_BIN
    if not os.path.exists(binary):
        raise RuntimeError(f"Hermes CLI binary not found at {binary}")
    if not os.access(binary, os.X_OK):
        raise RuntimeError(f"Hermes CLI binary is not executable at {binary}")

    query = f"SYSTEM INSTRUCTIONS:\n{system}\n\nUSER REQUEST:\n{user_content}"
    command = [
        binary,
        "chat",
        "-q",
        query,
        "-Q",
        "--source",
        "tool",
    ]
    if APOLLO_HERMES_PROVIDER:
        command.extend(["--provider", APOLLO_HERMES_PROVIDER])
    if APOLLO_MODEL:
        command.extend(["-m", APOLLO_MODEL])

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=MODEL_REQUEST_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        process.kill()
        raise
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise

    primary_output = stdout if (stdout or b"").strip() else stderr
    secondary_output = stderr if primary_output is stdout else stdout

    if process.returncode != 0:
        detail = (primary_output or secondary_output or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"Hermes CLI failed with code {process.returncode}")

    raw_text = (primary_output or secondary_output or b"").decode("utf-8", errors="replace")
    text = _clean_hermes_cli_output(raw_text)
    cli_error = _extract_hermes_cli_error(text)
    if cli_error:
        raise RuntimeError(cli_error)
    response = _CliResponse(
        choices=[_CliChoice(message=_CliMessage(content=text))],
        raw_text=raw_text,
    )
    return text, response


async def _generate_json_with_retry(role, system, user_content, max_tokens=1000, retry_instruction=None):
    text, response = await _generate_text(role=role, system=system, user_content=user_content, max_tokens=max_tokens)
    result, parse_failure = _parse_json_response(text)
    if not parse_failure:
        return result, response, False
    retry_content = f"{user_content}\n\n{retry_instruction}" if retry_instruction else f"{user_content}\n\nReturn ONLY valid JSON matching the required schema."
    retry_text, retry_response = await _generate_text(role=role, system=system, user_content=retry_content, max_tokens=max_tokens)
    retry_result, retry_parse_failure = _parse_json_response(retry_text)
    return retry_result, retry_response, retry_parse_failure


def _estimate_cost(response, role):
    _backend, model = _get_role_config(role)
    usage = getattr(response, "usage", None)
    if usage is None:
        return 0.0
    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0
    pricing = OPENAI_PRICING.get(model)
    if pricing is None:
        return 0.0
    return ((input_tokens * pricing["input"]) + (output_tokens * pricing["output"])) / 1_000_000


def _normalize_score_result(result, lane):
    weights = BUSINESS_WEIGHTS if lane == "business" else CREATIVE_WEIGHTS
    payload = dict(result or {})
    numeric_keys = list(weights)
    for key in ("actionability", "brand_fit", "factual_reliability"):
        if key in weights:
            numeric_keys.append(key)
    for key in set(numeric_keys):
        value = payload.get(key)
        payload[key] = float(value) if value is not None else None
    if payload.get("composite") is None:
        total = 0.0
        weight_total = 0.0
        for key, weight in weights.items():
            value = payload.get(key)
            if value is None:
                continue
            total += value * weight
            weight_total += weight
        payload["composite"] = total / weight_total if weight_total else None
    payload.setdefault("constraints_met", None)
    payload.setdefault("constraint_notes", "")
    payload.setdefault("critique", "")
    return payload


def _coerce_text_value(value):
    if isinstance(value, str):
        return value.strip()
    return ""


def _build_prompt_diagnosis_brief(lane, policy_context=None):
    context = policy_context or {}
    lines = [
        "Before writing, take one short planning step and decide:",
        "1. whether this prompt calls for creative openness, strict framework-following, or a hybrid approach",
        "2. who the intended audience is",
        "3. what the piece is trying to accomplish",
        "",
        "Then write the strongest artifact for that situation.",
        "",
        "Return valid JSON only in this shape:",
        "{",
        '  "artifact": "<string>",',
        '  "process_trace": {',
        '    "prompt_diagnosis": {',
        f'      "composition_mode": "{PROMPT_DIAGNOSIS_SCHEMA["composition_mode"]}",',
        f'      "intended_audience": "{PROMPT_DIAGNOSIS_SCHEMA["intended_audience"]}",',
        f'      "piece_goal": "{PROMPT_DIAGNOSIS_SCHEMA["piece_goal"]}"',
        "    }",
        "  }",
        "}",
    ]
    if lane == "business":
        lines.insert(
            4,
            "For business writing, default toward clear structure unless the prompt genuinely rewards a looser rhetorical shape.",
        )
    if context.get("track") or context.get("family") or context.get("generation_guidance"):
        lines.extend([
            "",
            "Use the task metadata as supporting context, not as boilerplate to echo back.",
        ])
    active_rules = context.get("active_prompt_diagnosis_rules") or []
    if active_rules:
        lines.extend([
            "",
            "Active council prompt-diagnosis mandates:",
        ])
        for rule in active_rules:
            instruction = _coerce_text_value(rule.get("action") or rule.get("reason") or rule.get("title"))
            if instruction:
                lines.append(f"- {instruction}")
    return "\n".join(lines)


def _normalize_prompt_diagnosis(payload):
    diagnosis = payload if isinstance(payload, dict) else {}
    return {
        "composition_mode": _coerce_text_value(diagnosis.get("composition_mode")) or "unspecified",
        "intended_audience": _coerce_text_value(diagnosis.get("intended_audience")) or "unspecified",
        "piece_goal": _coerce_text_value(diagnosis.get("piece_goal")) or "unspecified",
    }


def _normalize_genesis_artifact(result):
    if not isinstance(result, dict):
        return ""

    for key in ("artifact", "draft", "response", "text", "content"):
        value = _coerce_text_value(result.get(key))
        if value:
            return value

    hero_parts = []
    headline = _coerce_text_value(result.get("headline"))
    subheadline = _coerce_text_value(result.get("subheadline"))
    cta = _coerce_text_value(result.get("cta"))
    if headline:
        hero_parts.append(f"Headline: {headline}")
    if subheadline:
        hero_parts.append(f"Subheadline: {subheadline}")
    if cta:
        hero_parts.append(f"CTA: {cta}")
    if hero_parts:
        return "\n".join(hero_parts)

    title = _coerce_text_value(result.get("title"))
    body = _coerce_text_value(result.get("body"))
    closing = _coerce_text_value(result.get("closing"))
    sections = [part for part in (title, body, closing) if part]
    if sections:
        return "\n\n".join(sections)

    return ""


async def _run_genesis_role(role, prompt, constraints=None, prior_feedback=None, lane="creative", policy_context=None, **_kwargs):
    system_prompt = THERON_SYSTEM if role == "theron" else GENESIS_SYSTEM
    backend, _model = _get_role_config(role)
    if role == "theron" and backend == "openclaw_local":
        user_content = _build_local_theron_request(
            prompt=prompt,
            constraints=constraints,
            prior_feedback=prior_feedback,
            lane=lane,
            policy_context=policy_context,
        )
    else:
        policy_note = ""
        if policy_context:
            policy_note = f"\n\nPOLICY CONTEXT:\n{json.dumps(policy_context, sort_keys=True)}"
        user_content = f"PROMPT:\n{prompt}{policy_note}"
        if constraints:
            user_content += "\n\nCONSTRAINTS:\n" + "\n".join(f"- {item}" for item in constraints)
        if prior_feedback:
            user_content += f"\n\nPRIOR FEEDBACK:\n{prior_feedback}"
        user_content += "\n\n" + _build_prompt_diagnosis_brief(lane, policy_context)

    result, response, parse_failure = await _generate_json_with_retry(
        role=role,
        system=system_prompt,
        user_content=user_content,
        max_tokens=2000,
    )
    if parse_failure:
        artifact = result["artifact"] if isinstance(result, dict) and result.get("artifact") else ""
        if not artifact:
            raw_text, response = await _generate_text(role, system_prompt, user_content, max_tokens=2000)
            artifact = _coerce_text_value(raw_text)
        artifact = _coerce_text_value(artifact)
        return {"artifact": artifact, "process_trace": {"protocol": GENESIS_PROTOCOL, "parse_failure": True}}, _estimate_cost(response, role), True

    artifact = _normalize_genesis_artifact(result)
    process_trace = result.get("process_trace") or {
        "protocol": GENESIS_PROTOCOL,
        "revision_status": "ok",
        "verification_status": "not_run",
        "verifier_findings": [],
        "verifier_checks": [],
        "verifier_inferred_constraints": [],
        "stage_costs": {},
    }
    process_trace.setdefault("protocol", GENESIS_PROTOCOL)
    process_trace.setdefault("verification_status", "not_run")
    process_trace.setdefault("verifier_findings", [])
    process_trace.setdefault("verifier_checks", [])
    process_trace.setdefault("verifier_inferred_constraints", [])
    process_trace.setdefault("stage_costs", {})
    process_trace["prompt_diagnosis"] = _normalize_prompt_diagnosis(process_trace.get("prompt_diagnosis"))
    process_trace.setdefault("artifact_contract_status", "ok" if artifact else "empty_artifact")
    if not artifact:
        process_trace.setdefault("generation_failure_reason", "empty_artifact_after_normalization")
    return {"artifact": artifact, "process_trace": process_trace}, _estimate_cost(response, role), False


async def run_genesis(prompt, constraints=None, prior_feedback=None, lane="creative", policy_context=None, **_kwargs):
    return await _run_genesis_role("genesis", prompt, constraints=constraints, prior_feedback=prior_feedback, lane=lane, policy_context=policy_context, **_kwargs)


async def run_openclaw_genesis(prompt, constraints=None, prior_feedback=None, lane="creative", policy_context=None, **_kwargs):
    return await _run_genesis_role("genesis_openclaw", prompt, constraints=constraints, prior_feedback=prior_feedback, lane=lane, policy_context=policy_context, **_kwargs)


async def run_theron_genesis(prompt, constraints=None, prior_feedback=None, lane="creative", policy_context=None, **_kwargs):
    return await _run_genesis_role("theron", prompt, constraints=constraints, prior_feedback=prior_feedback, lane=lane, policy_context=policy_context, **_kwargs)


async def run_muse(artifact, prompt, constraints=None, lane="creative", **_kwargs):
    user_content = f"ORIGINAL PROMPT:\n{prompt}\n\nARTIFACT TO EVALUATE:\n{artifact}"
    if constraints:
        user_content = f"ORIGINAL PROMPT:\n{prompt}\n\nCONSTRAINTS:\n" + "\n".join(f"- {c}" for c in constraints) + f"\n\nARTIFACT TO EVALUATE:\n{artifact}"
    curriculum_targets = _kwargs.get("curriculum_targets") or []
    if curriculum_targets:
        user_content += "\n\nACTIVE CURRICULUM TARGETS:\n"
        for target in curriculum_targets:
            instruction = _coerce_text_value(target.get("action") or target.get("reason") or target.get("title"))
            if instruction:
                user_content += f"- {instruction}\n"
    text, response = await _generate_text(
        role="muse",
        system=MUSE_BUSINESS_SYSTEM if lane == "business" else MUSE_SYSTEM,
        user_content=user_content,
        max_tokens=1000,
    )
    result, parse_failure = _parse_json_response(text)
    if parse_failure:
        result = {
            "novelty": None,
            "surprise": None,
            "value": None,
            "elaboration": None,
            "coherence": None,
            "composite": None,
            "actionability": None,
            "brand_fit": None,
            "factual_reliability": None,
            "constraints_met": None,
            "constraint_notes": "PARSE FAILURE",
            "critique": "PARSE FAILURE: evaluation could not be scored.",
            "keep": False,
        }
    else:
        result = _normalize_score_result(result, lane)
    return result, _estimate_cost(response, "muse"), parse_failure


async def _run_hermes_role(role, artifact, prompt, constraints=None, lane="creative", curriculum_targets=None):
    user_content = f"ORIGINAL PROMPT:\n{prompt}\n\nARTIFACT TO EVALUATE:\n{artifact}"
    if constraints:
        user_content = f"ORIGINAL PROMPT:\n{prompt}\n\nCONSTRAINTS:\n" + "\n".join(f"- {c}" for c in constraints) + f"\n\nARTIFACT TO EVALUATE:\n{artifact}"
    if curriculum_targets:
        user_content += "\n\nACTIVE CURRICULUM TARGETS:\n"
        for target in curriculum_targets:
            instruction = _coerce_text_value(target.get("action") or target.get("reason") or target.get("title"))
            if instruction:
                user_content += f"- {instruction}\n"
    text, response = await _generate_text(
        role=role,
        system=(APOLLO_BUSINESS_SYSTEM if lane == "business" else APOLLO_SYSTEM) if role in {"apollo", "hermes_external"} else (ATHENA_BUSINESS_SYSTEM if lane == "business" else ATHENA_SYSTEM),
        user_content=user_content,
        max_tokens=800,
    )
    result, parse_failure = _parse_json_response(text)
    if parse_failure:
        result = {
            "novelty": None,
            "surprise": None,
            "value": None,
            "elaboration": None,
            "coherence": None,
            "composite": None,
            "actionability": None,
            "brand_fit": None,
            "factual_reliability": None,
            "constraints_met": None,
            "constraint_notes": "PARSE FAILURE",
            "critique": "HERMES PARSE FAILURE",
        }
    else:
        result = _normalize_score_result(result, lane)
    return result, _estimate_cost(response, role), parse_failure


async def run_hermes(artifact, prompt, constraints=None, lane="creative", **_kwargs):
    return await _run_hermes_role("athena", artifact, prompt, constraints=constraints, lane=lane, curriculum_targets=_kwargs.get("curriculum_targets"))


async def run_athena(artifact, prompt, constraints=None, lane="creative", **_kwargs):
    return await _run_hermes_role("athena", artifact, prompt, constraints=constraints, lane=lane, curriculum_targets=_kwargs.get("curriculum_targets"))


async def run_external_hermes(artifact, prompt, constraints=None, lane="creative", **_kwargs):
    return await _run_hermes_role("apollo", artifact, prompt, constraints=constraints, lane=lane, curriculum_targets=_kwargs.get("curriculum_targets"))


async def run_apollo(artifact, prompt, constraints=None, lane="creative", **_kwargs):
    return await _run_hermes_role("apollo", artifact, prompt, constraints=constraints, lane=lane, curriculum_targets=_kwargs.get("curriculum_targets"))


async def run_council_review(council_prompt):
    return await _generate_text(
        "council",
        (
            "You are the characterization council for Hamlet's Ghost. "
            "Your job is cartography, not governance: summarize where panel-preference labels are accumulating, "
            "propose concrete hypotheses about LLM preference to test next, and check whether the panel's preference "
            "pattern has drifted since the last session. Do not approve rule promotions or claim universal truth."
        ),
        council_prompt,
        max_tokens=2000,
    )


async def run_council_json(system, user_content, max_tokens=1200, retry_instruction=None):
    result, response, parse_failure = await _generate_json_with_retry(
        role="council",
        system=system,
        user_content=user_content,
        max_tokens=max_tokens,
        retry_instruction=retry_instruction,
    )
    return result, _estimate_cost(response, "council"), parse_failure


def _probe_http_health(url):
    with urlopen(url, timeout=3) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload


async def get_theron_provider_status():
    status = {
        "enabled": THERON_GENERATION_ENABLED,
        "backend": THERON_BACKEND,
        "model": THERON_MODEL,
        "base_url": THERON_BASE_URL,
        "health_url": THERON_HEALTH_URL,
        "reachable": False,
        "gateway_status": None,
        "error": None,
    }
    if not THERON_GENERATION_ENABLED:
        status["error"] = "Theron generation is disabled."
        return status
    if THERON_BACKEND == "openclaw_local":
        binary = THERON_OPENCLAW_BIN
        if not shutil.which(binary) and not os.path.exists(binary):
            status["error"] = f"OpenClaw binary not found at {binary}"
            return status
        try:
            process = await asyncio.create_subprocess_exec(
                binary,
                "agents",
                "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
            output = (stdout or b"").decode("utf-8", errors="replace")
            if process.returncode == 0 and THERON_OPENCLAW_AGENT_ID in output:
                status["reachable"] = True
                status["gateway_status"] = {
                    "mode": "openclaw_local",
                    "agent_id": THERON_OPENCLAW_AGENT_ID,
                    "binary": binary,
                }
            else:
                status["error"] = ((stderr or stdout or b"").decode("utf-8", errors="replace").strip() or "Theron local agent not found.")
        except (OSError, TimeoutError) as exc:
            status["error"] = str(exc)
        return status
    if THERON_BACKEND not in {"theron", "theron_gateway", "openclaw", "openclaw_gateway"}:
        status["error"] = f"Theron backend '{THERON_BACKEND}' does not expose gateway health."
        return status
    try:
        payload = await asyncio.to_thread(_probe_http_health, THERON_HEALTH_URL)
        status["reachable"] = True
        status["gateway_status"] = payload
    except (OSError, URLError, TimeoutError, ValueError) as exc:
        status["error"] = str(exc)
    return status


async def get_apollo_provider_status():
    status = {
        "enabled": APOLLO_SHADOW_ENABLED,
        "backend": APOLLO_BACKEND or ATHENA_BACKEND,
        "model": APOLLO_MODEL,
        "independent": APOLLO_INDEPENDENT,
        "panel_version": JUDGE_PANEL_VERSION,
        "reachable": False,
        "gateway_status": None,
        "error": None,
    }
    if not APOLLO_SHADOW_ENABLED:
        status["error"] = "Apollo shadow evaluation is disabled."
        return status
    if APOLLO_BACKEND == "openclaw_local":
        binary = THERON_OPENCLAW_BIN
        if not shutil.which(binary) and not os.path.exists(binary):
            status["error"] = f"OpenClaw binary not found at {binary}"
            return status
        try:
            process = await asyncio.create_subprocess_exec(
                binary,
                "agents",
                "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
            output = (stdout or b"").decode("utf-8", errors="replace")
            if process.returncode == 0 and THERON_OPENCLAW_AGENT_ID in output:
                status["reachable"] = True
                status["gateway_status"] = {
                    "mode": "openclaw_local",
                    "agent_id": THERON_OPENCLAW_AGENT_ID,
                    "binary": binary,
                }
            else:
                status["error"] = ((stderr or stdout or b"").decode("utf-8", errors="replace").strip() or "Apollo local agent not found.")
        except (OSError, TimeoutError) as exc:
            status["error"] = str(exc)
        return status
    if APOLLO_BACKEND != "hermes_cli":
        status["reachable"] = True
        status["gateway_status"] = {
            "mode": APOLLO_BACKEND or ATHENA_BACKEND,
        }
        return status

    binary = APOLLO_HERMES_BIN
    if not shutil.which(binary) and not os.path.exists(binary):
        status["error"] = f"Hermes CLI binary not found at {binary}"
        return status
    try:
        process = await asyncio.create_subprocess_exec(
            binary,
            "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
        output = ((stdout or b"") + (stderr or b"")).decode("utf-8", errors="replace")
        if process.returncode == 0:
            status["reachable"] = True
            status["gateway_status"] = {
                "mode": "hermes_cli",
                "binary": binary,
                "provider": APOLLO_HERMES_PROVIDER,
            }
        else:
            status["error"] = output.strip() or "Hermes CLI status failed."
    except (OSError, TimeoutError) as exc:
        status["error"] = str(exc)
    return status
