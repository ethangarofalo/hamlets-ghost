# Local Setup

This document is for someone who wants to run Hamlet's Ghost locally beyond the fixture-based walkthrough. If you only want to verify the public claims without live model calls, start with `docs/WALKTHROUGH.md`; that path uses a seeded SQLite database and does not require OpenAI, Anthropic, Hermes, OpenClaw, or any external provider.

## Prerequisites

Hamlet's Ghost was developed and freshly tested on macOS. Linux should work because the runtime is Python, SQLite, and browser-side JavaScript, but it has not been validated from a clean clone. Windows is not currently a supported target.

You need:

- Python 3.11 or newer; the current local test environment uses Python 3.14.
- Node.js for `node --check static/app.js` in preflight.
- SQLite, included with Python on normal installs.
- Enough disk space for the virtual environment, local SQLite database, and generated wiki files. A few hundred MB is comfortable for the public demo.

The public demo path has been tested from a fresh temporary virtual environment. Full live operation depends on provider credentials and any local external-agent tools you choose to enable.

## Installation

From a fresh clone:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Then edit `.env` before running live experiments. Do not commit `.env`.

Start the local server with:

```bash
./start.sh
```

By default the app binds to `127.0.0.1:7777`.

## Environment Variables

`OPENAI_API_KEY`: required for the default live configuration because Genesis, Muse, Athena, the council, and the interlocutor default to the `openai` backend. Apollo does not use this key when `APOLLO_BACKEND=hermes_cli`; in that mode Apollo calls `APOLLO_HERMES_BIN`.

`LAB_ADMIN_TOKEN`: required for write endpoints in the local dashboard/API. Generate a long random value. `ADMIN_API_TOKEN` is a legacy alias.

`LAB_HOST` and `PORT`: local server bind settings. Defaults are `127.0.0.1` and `7777`.

`LAB_DB_PATH`: optional SQLite database path. Leave blank for `creativity_lab.db`; set it for demo or isolated runs.

`MODEL_REQUEST_TIMEOUT_SECONDS`, `MODEL_MAX_RETRIES`, `MODEL_RETRY_BACKOFF_SECONDS`: request timeout and retry controls for model calls and CLI-backed calls.

`LAB_CURRENT_EPOCH`, `LAB_LEGACY_EPOCH`, `LAB_JUDGE_PANEL_VERSION`, `LAB_ASSEMBLING_STALE_MINUTES`: labeling and bookkeeping knobs. Most users should not change them.

`OPENAI_MODEL`, `OPENAI_HOLDOUT_MODEL`, `GENESIS_MODEL`, `MUSE_MODEL`, `ATHENA_MODEL`, `COUNCIL_MODEL`, `INTERLOCUTOR_MODEL`: model choices for OpenAI-backed roles.

`GENESIS_BACKEND`, `MUSE_BACKEND`, `ATHENA_BACKEND`, `COUNCIL_BACKEND`, `INTERLOCUTOR_BACKEND`: backend choices for core roles. Supported backend names include `openai`, `ollama`, `openclaw`, `openclaw_gateway`, `theron`, `theron_gateway`, `openclaw_local`, and `hermes_cli`, though not every role has been validated on every backend.

`APOLLO_BACKEND`: optional external evaluator backend. Set `APOLLO_BACKEND=hermes_cli` to route Apollo through the Hermes CLI rather than the OpenAI API. Set `APOLLO_HERMES_BIN` to the executable path and `APOLLO_HERMES_PROVIDER` to the provider name Hermes should use.

`THERON_BACKEND`, `THERON_MODEL`, `THERON_OPENCLAW_AGENT_ID`, `THERON_OPENCLAW_BIN`, `THERON_BASE_URL`, `THERON_API_KEY`, `THERON_HEALTH_URL`: Theron external-generator configuration.

`THERON_GATEWAY_*` and `THERON_TELEGRAM_*`: optional gateway/Telegram relay settings. Leave blank unless you are explicitly operating the gateway.

`HUMAN_REVIEW_CHANNEL` and `HUMAN_REVIEW_TARGET`: optional human-review relay settings.

`FORCED_ATHENA_*`: deterministic testing/debug knobs. Leave blank for normal use.

## Cost Warning

**Live experiments spend real money.** With the default `gpt-4.1-mini` pricing table in `agents.py`, a typical short compiler-compare packet is roughly cents, not dollars, because it runs two generations and multiple evaluator calls at low per-token prices. Treat that as an estimate, not a guarantee: long prompts, retries, parse failures, larger model choices, or external providers can change the bill quickly.

The current code prices `gpt-4.1-mini` at $0.40 per million input tokens and $1.60 per million output tokens. A rough 25,000 input-token and 10,000 output-token packet across generation and scoring would cost about $0.03 in model calls. Running enough packets to reach a single `aligned` or `divergent` characterization requires supporting packet evidence plus at least five decisive human reviews; model-call cost is likely under $1 at default small-model settings, while human review time is the real bottleneck. If you switch to larger models, multiply accordingly.

## Configuration Surfaces

Use `LAB_ADMIN_TOKEN` for local write protection. Use `LAB_HOST` and `PORT` for binding. Use `LAB_DB_PATH` for an isolated SQLite database. Use `MODEL_REQUEST_TIMEOUT_SECONDS` and retry variables when providers hang or rate-limit. Runtime logs currently go to the terminal or whatever process manager starts the server.

## Verification

Run the full local gate:

```bash
./scripts/preflight.sh
```

Then run the no-API demo:

```bash
./.venv/bin/python scripts/bootstrap_demo.py --force
LAB_DB_PATH=demo_lab.db ./.venv/bin/python scripts/promote_rules.py
```

The exact expected output is documented in `docs/WALKTHROUGH.md`.

## Beyond The Demo

The live compiler-compare route is `POST /api/experiment/compiler-compare`, implemented in `server.py`. It creates paired raw and compiled prompt variants, scores both, records rule evidence, and exposes promotion proposals through `/api/rules/promotions`. Prefer the fixture walkthrough first; only run live packets once credentials, admin token, and cost expectations are explicit.

The browser UI calls the same endpoints. For scripted runs, send `X-Admin-Token` with the value from `LAB_ADMIN_TOKEN` when calling write routes.

## Troubleshooting

Missing `OPENAI_API_KEY` with an OpenAI-backed role raises an explicit runtime error before model calls complete. Either provide the key or move that role to a configured non-OpenAI backend.

If the server port is already in use, change `PORT` in `.env` or stop the process occupying the port.

SQLite is fine for local single-operator work. If multiple processes write heavily at once, locking can appear; use one server process for normal operation and reserve Postgres migration for higher experiment volume.
