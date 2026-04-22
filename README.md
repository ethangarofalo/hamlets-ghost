# Hamlet's Ghost

*What do model panels prefer when multiple answers look plausible, and where do those preferences diverge from human judgment?*

Hamlet's Ghost is a local comparative-judgment lab for studying LLM aesthetic preference. It generates rival artifacts, asks a Muse/Athena/Apollo evaluator panel to judge them, and routes meaningful Apollo-vs-panel disagreements to a human operator. The public status of each major claim is tracked in [docs/implementation-status.md](docs/implementation-status.md); read that ledger as the backstop for everything this README says.

The lab is early, test-backed, and intentionally modest about what is real. The disagreement workflow, provider separation, artifact auth gate, and demo evidence path are implemented. The prompt compiler, seeded taxonomy, cross-family rule promotion, and generator distinctiveness work are prototypes unless and until earned evidence says otherwise.

![Compiler Learning UI strip: one rule under watch, insufficient_data characterization, HOLD recommendation, 2 prompt families, 1 suppressed dual constraint-fail slice, 3 unreviewed.](docs/images/compiler-learning-strip.png)

## Quickstart

```bash
git clone <repo-url> hamlets-ghost
cd hamlets-ghost
python3 -m venv .venv && ./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
./start.sh demo
```

Demo mode uses synthetic fixture data and bootstraps `demo_lab.db` on first run. Live model calls require provider credentials in `.env`.

## What This Is

The lab's basic loop is prompt in, rival outputs out, evaluator votes recorded, and human review used as the characterization reference when the machine panel disagrees. Apollo is now the outside auditor lane: it runs through Hermes/GPT-5.4 by default, while Theron is the OpenClaw/Opus generator lane.

The longer-term direction is a prompt compiler: a traced system that proposes prompt transformations, tests them against rival outputs, and only promotes rules when panel behavior and human review have been separated cleanly. That compiler is not yet a learned product. It is currently a prototype harness with evidence plumbing.

## What's Implemented, What Isn't

See [docs/implementation-status.md](docs/implementation-status.md) for the claim-by-claim ledger.

- Implemented: independent Apollo evaluator lane; Apollo-centered disagreement queue; admin-token protection on `/api/artifact/{id}`; demo fixture walkthrough.
- Prototype: prompt compiler traces; cross-family rule promotion; seeded anti-pattern taxonomy; Genesis/Theron distinctiveness.
- Aspirational: five-advisor council governance protocol; dashboard calibration rates such as `constraint_recovery_rate` and `critique_help_rate`.

## Architecture

The backend is a FastAPI app backed by SQLite. Experiments move through generator roles, evaluator roles, review queues, and wiki/taxonomy surfaces: Genesis/Theron generate, Muse/Athena/Apollo judge, human review characterizes disagreements, and the reflective wiki preserves seeded concept pages, each labeled `seeded` until lab evidence corroborates them. The operational code lives mostly in [server.py](server.py), [agents.py](agents.py), [database.py](database.py), and [judgment_wiki.py](judgment_wiki.py).

## Read Next

- [program.md](program.md) - detailed research protocol and operating model.
- [docs/implementation-status.md](docs/implementation-status.md) - implemented/prototype/aspirational ledger.
- [docs/2026-04-02-recalibration-and-apollo-audit-plan.md](docs/2026-04-02-recalibration-and-apollo-audit-plan.md) - early Apollo recalibration and audit plan.
- [docs/DECISIONS.md](docs/DECISIONS.md) - load-bearing decision log.
- [wiki/](wiki/) - reflective memory; concept pages are labeled seeded, not earned.

## License

Apache-2.0. See [LICENSE](LICENSE).
