# Hamlet's Ghost

Hamlet's Ghost is a local AI creativity lab for running, scoring, and studying structured experiments across creative and business tasks.

The lab is designed to answer a specific question:

> Which prompt policies, dialogue protocols, and agent configurations increase useful novelty without sacrificing constraint satisfaction, reliability, or human judgment?

This is not just a prompt playground. It is a research instrument with:
- a generation layer
- an evaluation layer
- promotion gates
- provenance and audit history
- human governance at the top

## Current Role Stack

- `GENESIS`: default internal generator
- `MUSE`: internal evaluator and continuity anchor
- `HERMES`: independent evaluator lane
- `human operator`: final calibration and governance authority

The lab is also being prepared for bounded external-agent participation:
- `Theron / OpenClaw`: external generation partner
- `external Hermes`: outside evaluator in staged trust mode

External agents are meant to increase creative tension and useful disagreement, not take uncontrolled ownership of the lab.

## What The Lab Does

The backend runs experiments on tasks in two lanes:
- `creative`
- `business`

Each task includes:
- a prompt
- constraints
- a prompt family
- a hypothesis

For each experiment, the lab:
1. selects a task
2. generates an artifact
3. scores it with evaluators
4. checks constraint satisfaction
5. records provenance, traces, and scores
6. decides whether to discard, keep, or promote

The long-form operating protocol lives in [program.md](/Users/ethangarofalo/creativity-lab/program.md).

## Repo Map

- [server.py](/Users/ethangarofalo/creativity-lab/server.py): FastAPI app, scheduler, experiment execution, API surface
- [agents.py](/Users/ethangarofalo/creativity-lab/agents.py): generation and evaluation role routing
- [database.py](/Users/ethangarofalo/creativity-lab/database.py): SQLite schema, persistence, analytics helpers
- [experiments.py](/Users/ethangarofalo/creativity-lab/experiments.py): task catalog, policy variants, scheduling logic
- [program.md](/Users/ethangarofalo/creativity-lab/program.md): research protocol and operating model
- [docs/backend-safety-protocol.md](/Users/ethangarofalo/creativity-lab/docs/backend-safety-protocol.md): required safety posture for backend work
- [docs/hermes-trust-model.md](/Users/ethangarofalo/creativity-lab/docs/hermes-trust-model.md): staged authority model for agents
- [docs/external-agent-rollout.md](/Users/ethangarofalo/creativity-lab/docs/external-agent-rollout.md): rollout plan for Theron/OpenClaw and external Hermes

## Running The Lab

Start the backend:

```bash
cd /Users/ethangarofalo/creativity-lab
./start.sh
```

Default host and port:
- `127.0.0.1:7777`

Useful API endpoints:
- `GET /api/state`
- `GET /api/history`
- `GET /api/analysis`
- `GET /api/artifact/{id}`
- `POST /api/start`
- `POST /api/stop`
- `POST /api/experiment/custom`
- `POST /api/experiment/external`

## Safety Before Speed

This lab was recovered after a backend corruption incident. Because of that, reversibility is part of the operating model.

Before risky backend changes:
- run preflight
- keep work scoped to one change family at a time
- checkpoint in git
- avoid broad rewrites of core modules

Run preflight with:

```bash
cd /Users/ethangarofalo/creativity-lab
bash scripts/preflight.sh
```

See [docs/2026-04-02-backend-recovery-incident.md](/Users/ethangarofalo/creativity-lab/docs/2026-04-02-backend-recovery-incident.md) for the incident record and [docs/backend-safety-protocol.md](/Users/ethangarofalo/creativity-lab/docs/backend-safety-protocol.md) for the live protocol.

## Theron's Place In The Lab

Theron is being integrated as a bounded external generation partner, not as an uncontrolled backend owner.

Current intended posture:
- read the repo
- understand the lab's aims and architecture
- participate first through bounded generation or proposal workflows
- earn broader authority through calibration and safe operation

For now, the cleanest manual bridge is:
1. build a Theron request packet
2. send it to Theron
3. bring the artifact back through the external experiment endpoint
4. let the local lab score and store it

Generate a Theron-ready packet with:

```bash
cd /Users/ethangarofalo/creativity-lab
./.venv/bin/python scripts/build_theron_packet.py --task-id c08
```

This keeps the lab core local while still allowing Theron to participate meaningfully.

## Working Agreement For Agents

If you are an agent reading this repo, assume:
- the source tree must remain recoverable
- human judgment is still the calibration anchor
- promotion logic, storage, and governance stay local unless explicitly widened
- ambition is welcome, but it must be paired with reversibility

The lab wants genuine disagreement, strong generations, and disciplined iteration.

## Status

The lab is currently:
- recovered
- under git
- test-backed
- running locally
- moving toward bounded multi-agent operation

That means it is ready for serious experimentation, but not for careless autonomy.
