# Copilot instructions

Follow the repository policy in [`AGENTS.md`](../AGENTS.md). It is the single source of project rules.

Key points:
- Python 3.12 standard library only. Tests: `python -m unittest discover -s tests -v`.
- One bounded change per PR. Add or update tests with every behaviour change. Never skip or weaken tests or CI.
- Do not edit `.github/workflows/`, permissions or settings without the owner's explicit approval.
- Report claims with exact commit SHAs and CI run ids. Passing tests are evidence, not authorization.
