# Walkthrough: Demo Rule Evidence

This walkthrough verifies the public Hamlet's Ghost exhibit without making live model calls. It seeds a small SQLite database from `data/fixtures/demo_rule_evidence.json`, then runs the same dry-run promotion script used by the live lab.

The point is not to prove the rule is good. The point is to show the instrument refusing to characterize a rule before decisive human evidence exists.

## What The Fixture Contains

The fixture creates one candidate rule:

`diagnosis::make_audience_explicit`

It then seeds four compiler-compare evidence slices:

- `evidence_compiler_customer_recovery_001`
- `evidence_compiler_internal_comms_002`
- `evidence_compiler_personification_003`
- `evidence_compiler_sales_copy_004`

Three slices are eligible for support and characterization math. One slice is intentionally suppressed because both compared outputs failed constraints. Human review is not seeded, so all human signals remain `unreviewed`.

## Run The Demo Bootstrap

From the repository root:

```bash
./.venv/bin/python scripts/bootstrap_demo.py --force
```

Expected output:

```text
Seeded demo database: demo_lab.db
Fixture: data/fixtures/demo_rule_evidence.json
Rule evidence slices: 4
Proposal: hold diagnosis::make_audience_explicit
Characterization: insufficient_data
Eligible slices: 3
Suppressed dual constraint-fail slices: 1
Decisive human reviews: 0
```

The counts should match exactly.

## Run The Promotion Dry-Run

Point the promotion script at the demo database:

```bash
LAB_DB_PATH=demo_lab.db ./.venv/bin/python scripts/promote_rules.py
```

Expected output:

```text
Prompt rule promotion dry-run
No statuses are changed by this script.

Thresholds:
  provisional_packets: 5
  provisional_families: 2
  active_packets: 15
  active_families: 3
  active_model_families: 2
  active_human_win_rate: 0.6
  active_human_decisive: 3
  hurt_flag_rate: 0.4
  hurt_flag_min: 5
  panel_preference_rate: 0.6
  characterization_min_human: 5

HOLD: diagnosis::make_audience_explicit (candidate -> candidate)
  title: Make Audience Explicit
  characterization: insufficient_data
  support: 2 packet(s), 2 prompt family/families, 0 model family/families
  suppressed: 1 dual constraint-fail slice(s)
  human: 0 helped, 0 hurt, 0 mixed, 3 unreviewed
  reasons: 2 prompt families
  missing: 3 more supporting packet(s)
```

## How To Read The Result

The panel evidence is not empty. Two eligible packets support the rule across two prompt families. That is enough to make the rule worth watching, but not enough to promote it.

The suppressed line matters:

```text
suppressed: 1 dual constraint-fail slice(s)
```

That slice is visible, but it does not inflate support. A comparison between two constraint failures is not evidence that the rule helped.

The characterization line matters more:

```text
characterization: insufficient_data
```

The rule has zero decisive human reviews. The system therefore refuses to label it `aligned`, `divergent`, `llm_specific`, `human_specific`, or `neutral`. This is the behavior described in `docs/ARCHITECTURE.md`: panel signal alone cannot characterize a rule.

In the dry-run output, `unreviewed` is the stored data value and "decisive human reviews" is the threshold concept. Here they describe the same underlying fact: no human review has yet supplied `helped` or `hurt` for the eligible slices.

## Resetting The Demo

Re-run the bootstrap with `--force` whenever you want a clean demo database:

```bash
./.venv/bin/python scripts/bootstrap_demo.py --force
```

For a temporary database instead of `demo_lab.db`:

```bash
./.venv/bin/python scripts/bootstrap_demo.py --db-path /tmp/hamlet-walkthrough-demo.db --force
LAB_DB_PATH=/tmp/hamlet-walkthrough-demo.db ./.venv/bin/python scripts/promote_rules.py
```

## No Live API Calls

This walkthrough does not require OpenAI, Anthropic, Hermes, OpenClaw, or any external model provider. It only exercises local SQLite setup, the rule-evidence schema, dual-fail suppression, and dry-run promotion reporting.
