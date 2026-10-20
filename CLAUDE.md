# CLAUDE.md

Read and follow [`AGENTS.md`](AGENTS.md). It is the single source of project rules, evidence requirements and the report format.

Quick reference:
- Tests: `python -m unittest discover -s tests -v`; runner: `python run_tasks.py`.
- Standard library only. Never skip or weaken a test, invariant or CI gate.
- Every state claim names an exact SHA, plus the CI run id where relevant. Evidence is not authority.
- Do not merge your own PR. Workflow, permission and settings changes need the owner's explicit approval.
