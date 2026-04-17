# Hamlet's Ghost Judgment Wiki

This directory is the lab's living judgment memory.

The wiki is compiled from the structured data in the lab database. It is not the source of truth; it is the reflective layer that makes the lab's evolving beliefs inspectable.

V1 page types:
- packet outcome pages
- task family pages
- model voice pages
- evaluator pages
- lesson pages

The compiler entrypoint is:

```bash
cd hamlets-ghost
./.venv/bin/python scripts/compile_judgment_wiki.py
```

Generated pages are overwritten on each compile pass. Templates live in [templates](templates).
