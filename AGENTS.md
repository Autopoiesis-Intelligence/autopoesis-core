# AGENTS.md: rules for every agent working on this repository

This is the single policy file for humans and AI agents (Claude, GPT, Copilot, Manus and others). `CLAUDE.md` and `.github/copilot-instructions.md` only point here. Change the policy here, not in copies.

## What this repository is

`autopoiesis-core` restarts the Gnosis core. Its goal is to prove one minimal, closed, bounded self-development loop, stage by stage (A0–A12 in `docs/AUTONOMY_ROADMAP_SPEC.md`, introduced by PR #13). Capabilities from the older Gnosis repositories are added only after the stage that needs them is proven.

Product goal (owner decision, 2026-10-19): the system changes its own state and relations, Ψ=(X,R), within delegated authority. Code changes are one kind of change, not the goal itself. This is a goal, not a proven property.

## Non-negotiable rules

1. **Evidence is not authority.** A passing test, a hash or green CI never by itself authorizes a change to the core, a merge or a release.
2. **Goal ≠ implemented ≠ proven.** Use the evidence ladder for every claim and name the level:
   - `DESIGN`: documented;
   - `IMPLEMENTED`: code exists at an exact SHA;
   - `REACHABLE`: a runner or workflow path can invoke it;
   - `RUNTIME`: an execution was observed;
   - `PERSISTED`: it survives restart or restore;
   - `AUDITED`: negative cases were reviewed;
   - `CI_PROVEN`: relevant CI passed on the exact SHA.
3. **Exact SHAs.** Every claim about state names the commit SHA, plus the CI run id or artifact where relevant. Evidence from one SHA does not carry over to another, or from another repository.
4. **Fail closed.** Missing, malformed, stale, contradictory or unverifiable state or evidence stops the step. It never silently becomes an empty queue, a PASS or progress.
5. **No-op is not progress.** Synthetic fixtures are labelled synthetic. Progress means accepted, independently verified changes.
6. **Keep these distinct:** selection, verification, authorization, execution, commit and merge. One must never be inferred from another.
7. **Trusted core stays small:** Python 3.12 standard library only. No network calls, credentials or LLM calls inside the core. No arbitrary shell, `eval` or `exec` driven by task or queue data. Only the bounded task types in `run_tasks.py`.
8. **Never weaken a check to get green.** Never skip, disable or loosen a test, an invariant or a CI gate to make a run pass. Rejections and failures are kept as history.

## Autonomy levels

Each roadmap stage must state which level its acceptance criteria actually prove, and what remains unproven.

- **L1:** the system finds a problem on its own.
- **L2:** it proposes and checks a fix on its own.
- **L3:** it executes an authorized change on its own, in a bounded environment.
- **L4:** it governs its own development within pre-set authority, remaining verifiable, refusable and reversible.

Proving L1–L2 does not prove L3–L4. The agents' development loop (agents writing PRs) is not evidence of the product's autonomy.

## How to make a change

- Work on a branch and open a PR. `main` is protected by the ruleset `main-protection`: a PR and the `test` check are required, and force-push and deletion are blocked.
- Make one bounded change per PR. Tests come first or together with the change.
- Run the checks locally before pushing:
  ```bash
  python -m unittest discover -s tests -v
  python run_tasks.py
  ```
  Generated `RESULTS.json` and `TASK_QUEUE.json` are run artifacts. Do not commit them.
- Changes to `.github/workflows/`, permissions, secrets or repository settings need the owner's explicit approval for that change.
- Agents do not merge their own PRs. A merge needs green CI on the exact head **and** an independent review, meaning not the author agent.

## Report format

End each unit of work with:
- **BEFORE:** repo, branch, head and base SHA, relevant PRs and runs.
- **ACTION:** exact changes, files, commands and workflows run, and what was deliberately not done.
- **AFTER:** final SHA, diff or PR URL, test output, CI run id with its `head_sha` and conclusion.
- **RESULT:** separately, what is implemented, reachable, executed and persisted.
- **PROVEN / NOT PROVEN:** each claim with its evidence, or the reason evidence is missing.
- **REJECTED DIRECTIONS:** failed approaches and environment limits.
- **NEXT SEQ:** one next step, with acceptance criteria and the permissions it needs.

## Known naming quirk

The package directory is spelled `autopoesis/`, while the repository is `autopoiesis-core`. Renaming it is a separate, pending owner decision. Do not rename it as a side effect of other work.
