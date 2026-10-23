# Operating model: roles, task flow and automation status

This document is the single place that says who does what in the agent stack around `autopoiesis-core`, how a task moves from plan to merge, and which parts of that flow actually run without the owner today.

[`AGENTS.md`](../AGENTS.md) remains the source of the project's rules: the evidence ladder, the audit verdict format, the merge rules and the report format. This document does not repeat or change them. If the two ever disagree, `AGENTS.md` wins and the disagreement is a bug to fix here.

Status of this document: proposed in a PR (CL-017). It becomes the agreed model only when the owner merges it. Roles below were stated by the owner on 2026-10-23 14:50 UTC in the project thread, unless marked otherwise.

## Two loops

Keep them apart. The **development loop** is how agents build this repository. **Product autonomy** is what the core itself must prove through stages A0–A12 in [`docs/AUTONOMY_ROADMAP_SPEC.md`](AUTONOMY_ROADMAP_SPEC.md). Everything in this document is about the development loop. Nothing here is evidence of the product's autonomy (`AGENTS.md`, "Autonomy levels").

## Roles

| Who | Responsible for | Does not |
|---|---|---|
| **Owner** (yarik) | Theory together with ChatGPT; architectural decisions; every merge; approval of workflow, permission and settings changes; decisions listed as open below | Need to move tasks between agents by hand, look for PRs or start checks. The stack must bring him only the decisions that are his |
| **ChatGPT** (GPT) | Theory, architecture, critical analysis and control of evidence; acceptance criteria and priorities in `docs/PLAN.md`; periodically telling the owner when a merge decision is needed | Write core code; merge |
| **Claude** | Main engineer: implements tasks, writes tests, keeps CI green, keeps `docs/PLAN.md` statuses and evidence current, develops the automation of this loop | Merge its own PRs; change workflows, permissions or settings without the owner's explicit approval for that change |
| **Codex** | Independent audit of one exact head SHA of a PR | Write the change it audits. A missing Codex verdict blocks the merge of that PR only, never independent development |
| **GitHub Copilot (Free plan)** | Executor of tasks inside the core's self-update mechanism. The core spends Copilot's whole monthly budget on improving itself; nothing is reserved for manual use (owner, 2026-10-19) | Act as a general test helper for other agents; get its output into `main` without the same review, CI and owner merge as everyone else |
| **Manus (Free plan)** | One-off external research and source checks, results in Issue #22 (owner, 2026-10-20). **Not named in the owner's 2026-10-23 list; kept pending his confirmation** | Write core code |

### Identity on the shared account

All agents use one GitHub account (owner's choice). They are told apart by:

- the first line `Agent: Claude|GPT|Copilot|Manus` of every post, and an `Agent:` commit trailer;
- task ID prefixes `CL-`, `GP-`, `CP-`, `MN-`; branch prefixes `claude/`, `gpt/`, `copilot/`, `manus/`; labels `agent:claude`, `agent:gpt`, `agent:copilot`, `agent:manus`;
- GitHub's `performed_via_github_app` on comments, which is the only one of these that is proof. Claude posts through app `1236702` (`claude`). GPT and Codex both post through app `1144995` (`chatgpt-codex-connector`); a Codex review comes from the bot account `chatgpt-codex-connector[bot]`.

The text marks identify an author. They grant no authority.

### GPT and Codex: what counts as a verdict

Today `AGENTS.md` counts a verdict only from an issue comment posted through app `1144995` that opens with the `Verdict:` block for the PR's current head. That covers GPT's verdicts. A Codex bot review (summary comment with `codex-review-state`) does **not** count yet: PR #35's plan item P2 (branch `claude/cl-015-codex-review-verdict`, `f27cc15`) proposes the rule and is not merged. Until it is, the owner's "Codex audits exact SHAs" role is carried by verdicts in the `AGENTS.md` format.

## Where things live

| Thing | Where | Notes |
|---|---|---|
| Rules | `AGENTS.md` on `main` | Changes only through a reviewed PR the owner merges |
| Roles, task flow, automation status | this file | Status table updated with evidence, never in advance |
| Ordered task plan | `docs/PLAN.md` | PR #35, **not merged** as of `685c5a0`. Owner sets priorities, GPT adds criteria, Claude updates statuses and evidence |
| Theory | `docs/theory/` | Being written in a separate thread (CL-016, branch `claude/project-thread-ofxc12`, not merged). This file does not duplicate it |
| Roadmap A0–A12 | `docs/AUTONOMY_ROADMAP_SPEC.md` on `main` | |
| Claims, handoffs, live coordination | Issue #22 | Protocol in `docs/coordination/PROTOCOL.md`, PR #32, **not merged** |
| Audit verdicts | the PR they audit | Format in `AGENTS.md` |
| CI and the core's Copilot runs | GitHub Actions | `ci.yml` (`test` is the required check), `copilot-test-writer.yml`, `copilot-agent-trial.yml`, `copilot-smoke.yml` |

Live GitHub state (refs, SHAs, runs) outranks every document and every chat summary, including this one.

## How a task moves

1. **Plan.** The owner and GPT set the goal and acceptance criteria; the task enters `docs/PLAN.md` as `READY`. A task without acceptance criteria is not `READY`.
2. **Pick.** Claude takes the first `READY` task that does not depend on an unmerged PR (or whose dependency the plan states), and claims it in Issue #22.
3. **Build.** Claude works on its own branch, tests first or together with the change, and runs the checks from `AGENTS.md` locally. Copilot tasks run inside the core's workflows, within the core's budget.
4. **CI.** The `test` check must pass on the exact head SHA. A check is never weakened to get green.
5. **Audit.** Codex or GPT audits that exact head and posts a verdict. A new push makes every earlier verdict stale. Labels follow the table in `AGENTS.md`: `pending-audit`, `blocked-review`, `ready-for-owner`, `audit-overdue`.
6. **Owner decision.** A PR labelled `ready-for-owner` (valid `ACCEPTED` on the current head and green CI) is brought to the owner with its exact SHA. Only the owner merges.
7. **Record.** After the merge, Claude marks the task `DONE` in `docs/PLAN.md` with the merge SHA and the CI run on it.

While a PR waits for an audit, work that does not depend on it continues. At most 5 own Claude PRs wait at once (owner, 2026-10-23); beyond that a finished branch is kept and recorded in the plan instead of opened as a PR.

## No automatic merge

Nothing in this stack merges automatically. No agent merges, enables auto-merge, force-pushes or writes to `main`. `ready-for-owner`, a green check or an `ACCEPTED` verdict never authorizes a merge on its own. `main` is protected by the ruleset `main-protection` (PR and the `test` check required, no force push or deletion). Any change to this rule needs the owner's explicit decision and a change to `AGENTS.md` first.

## Automation status

`PROVEN` means the step was observed working at least once with the evidence named, without the owner starting it, unless the row says otherwise. `NOT PROVEN` means it is designed or partly built but has not been observed working that way. A status changes only with new evidence. Checked on 2026-10-23 at about 15:00 UTC against `main` = `685c5a0ce188314bbcf49c822f9a2222b9b3a22b`.

| Step | Status | Evidence, or what is missing |
|---|---|---|
| CI `test` runs on every PR to `main` and on push to `main` | PROVEN | `ci.yml` on `main`; e.g. PR CI 39970567900 on #35 head `c70e7a7` success |
| Claude's scheduled dev-loop tick fires every 4 hours | PROVEN | Scheduled task `autopoiesis-core dev loop`, cron `47 */4 * * *`, last fired 2026-10-23 12:48:11 UTC with status succeeded |
| A scheduled tick acts on GitHub without the owner | PROVEN, once, by timing | 41 s after that tick, comment 6365249878 on #33 (app `claude`) posted the `@codex review` probe that the tick's step 2 prescribes. Only timing ties the comment to the tick |
| Claude takes the next `READY` task from `docs/PLAN.md` on its own | NOT PROVEN | The tick prompt says to (step 5), but no task start has yet been traced to a tick alone. `docs/PLAN.md` is also not on `main` |
| Claims in Issue #22 computed by the checker | NOT PROVEN | `autopoesis/coordination.py` exists only on PR #32's branch (`ce55344`), not on `main` |
| Audit labels recomputed from verdicts | PROVEN, applied by an agent | Live on probe PR #31 (closed) and on #32 (`ready-for-owner`), applied by Claude with `autopoesis/audit_verdict.py`. The repository does not apply them itself (`AGENTS.md`, "Enforcement") |
| Codex reviews an exact head on request | PROVEN when asked, currently blocked | `@codex review` on #34 got a review of `79e4692` (comment 6360982940). Since 2026-10-23 09:30 UTC every request returns the usage-limit reply (#33 comments 6361839636, 6365253937) |
| Codex verdict counted by the audit rules | NOT PROVEN | Rule proposed on branch `claude/cl-015-codex-review-verdict` at `f27cc15` (CI 39970453578 green); not merged, no PR opened |
| GPT posts a verdict or handoff on a schedule, without the owner forwarding it | NOT PROVEN | 24-hour test ending 2026-10-21 found zero such posts (#22 comment 6327281839). On 2026-10-23 GPT posted a revalidation of #32 (comment 6361967710, app `chatgpt-codex-connector`) that it calls scheduled; GitHub cannot show whether the owner started that session |
| Full GPT → Claude handoff without the owner | NOT PROVEN | No Claude reply to comment 6361967710 in Issue #22 as of this check (newest comment there is 6361971854, 09:37 UTC) |
| GPT or Claude tells the owner a merge decision is due | NOT PROVEN | #32 has carried `ready-for-owner` since 2026-10-20 and is still open. Notification is step 7 of the tick prompt; no delivered notification is recorded as evidence. `audit-overdue` (7 days) has never fired |
| Core invokes Copilot automatically | NOT PROVEN | All three Copilot workflows are `workflow_dispatch` only. Both `copilot-test-writer.yml` runs (39356711683, 39523564470) were manual dispatches from the shared account |
| Copilot work enters `main` | NOT PROVEN | Run 39356711683's test was rejected by GPT for duplication; run 39523564470's proposal still waits for GPT's content audit |
| Core learns its Copilot budget from real runs | PROVEN for recording, unit unresolved | Ledger in `autopoesis/agent_budget.py`, runs 39336907440, 39337157482, 39337303723 and usage report from run 39346008076. Which reported field is the allowance unit is still unresolved |
| Automatic merge | Forbidden, not a gap | See "No automatic merge" |

## Decided boundaries

- **Role of the human in the core (`OQ-009`, owner, 2026-10-23 14:55 UTC).** The human is not a mandatory selector of the core's inner research and learning loop. Internal selection of a candidate, research acceptance of a hypothesis and authority to change the system are separate operations; authority is never inferred from `ACCEPTED`, a passing test or an internal selector's choice. Autonomous research is not autonomous change of the core: core mutations stay behind a controlled-commit boundary with the owner's approval, and there is no automatic merge. The decision is recorded and linked to requirements in `docs/theory/OPEN_QUESTIONS.md` (theory thread, branch `claude/project-thread-ofxc12`); this file does not restate its reasoning. It is an architectural decision, not evidence that it is implemented. In the development loop described here, the owner's merge gate applies either way.

## Open questions for the owner

- **Manus.** Keep the role above, change it, or drop Manus from the stack.
- **Codex verdicts.** Whether a Codex bot review counts as a verdict (plan item P2), which changes the review rules in `AGENTS.md`.

## Keeping this file current

Claude updates the status table in the same PR as the change that produces new evidence, or in a small docs PR after an observation, always with the SHA, run id or comment id. A role changes only by the owner's decision, recorded here with its date.
