# Operating model: roles, task flow and automation status

This document is the single place that says who does what in the agent stack around `autopoiesis-core`, how a task moves from plan to merge, and which parts of that flow actually run without the owner today.

[`AGENTS.md`](../AGENTS.md) remains the source of the project's rules: the evidence ladder, the audit verdict format, the merge rules and the report format. This document does not repeat or change them. If the two ever disagree, `AGENTS.md` wins and the disagreement is a bug to fix here.

Status of this document: proposed in a PR (CL-017). It becomes the agreed model only when the owner merges it. The target architecture below was fixed by the owner on 2026-10-23 (14:50 and 15:17 UTC) in the project thread, unless marked otherwise.

## Not part of the stack

DeepSeek, Perplexity and Manus are excluded (owner, 2026-10-23). They are not to be brought back into instructions, `AGENTS.md`, workflows, scripts, configurations or automation plans. Manus's conventions (`MN-`, `manus/`, `agent:manus`) are retired; past posts and labels stay as history. Remaining traces in other repositories are listed for removal by the repository clean-up, not here.

## Two loops

Keep them apart. The **development loop** is how agents build this repository. **Product autonomy** is what the core itself must prove through stages A0–A12 in [`docs/AUTONOMY_ROADMAP_SPEC.md`](AUTONOMY_ROADMAP_SPEC.md). Everything in this document is about the development loop. Nothing here is evidence of the product's autonomy (`AGENTS.md`, "Autonomy levels").

## Roles

| Who | Responsible for | Does not |
|---|---|---|
| **Autopoiesis Core** (this repository's code) | The minimal kernel of evolution and self-update: the allowed cycle of changes, checking their results, and keeping confirmed state | Depend on an outside model as a hidden source of authority or as an outside selector of decisions |
| **GitHub Copilot (Free plan)** | The core's own self-update tool: carries out the development and self-update tasks the core's protocol provides for, on its own, within that protocol. The core spends Copilot's whole monthly budget on itself; nothing is reserved for manual use (owner, 2026-10-19) | Act as a test helper or a backup for Claude; bypass checks; get its output into `main` without the same CI, audit and owner merge as everyone else |
| **Claude (Pro)** | Main engineer: implements tasks, fixes code and CI, tests, prepares PRs and follows their review, keeps `docs/PLAN.md` statuses and evidence current, develops the automation of this loop, and continues engineering work on its own within the agreed authority | Merge; change `main` without the owner's explicit permission; change workflows, permissions or settings without his explicit approval for that change |
| **ChatGPT / GPT-Codex** | Architectural control and independent audit: checks architectural decisions, changes, the exact SHA, tests, CI and evidence of execution; publishes verifiable verdicts through a channel that actually works; theory together with the owner; tells the owner when a merge decision is due | Write the change it audits; treat an old audit as evidence for a new SHA. A missing verdict blocks the merge of that PR only, never independent development |
| **GitHub and GitHub Actions** | GitHub is the canonical state of code, tasks, PRs and history. Actions runs CI and automation | Count as working because a workflow exists: only run results prove it |
| **Owner** (yarik) | Theory with ChatGPT; architectural decisions; every merge; approval of workflow, permission and settings changes; the open decisions below | Move tasks between agents by hand, look for PRs or start checks. The stack brings him only the decisions that are his |

### Identity on the shared account

All agents use one GitHub account (owner's choice). They are told apart by:

- the first line `Agent: Claude|GPT|Copilot` of every post, and an `Agent:` commit trailer;
- task ID prefixes `CL-`, `GP-`, `CP-`; branch prefixes `claude/`, `gpt/`, `copilot/`; labels `agent:claude`, `agent:gpt`, `agent:copilot`;
- GitHub's `performed_via_github_app` on comments, which is the only one of these that is proof. Claude posts through app `1236702` (`claude`). GPT and Codex both post through app `1144995` (`chatgpt-codex-connector`); a Codex review comes from the bot account `chatgpt-codex-connector[bot]`.

The text marks identify an author. They grant no authority.

### GPT and Codex: what counts as a verdict

Today `AGENTS.md` counts a verdict only from an issue comment posted through app `1144995` that opens with the `Verdict:` block for the PR's current head. That covers GPT's verdicts. A Codex bot review (summary comment with `codex-review-state`) does **not** count yet: PR #35's plan item P2 (branch `claude/cl-015-codex-review-verdict`, `f27cc15`) proposes the rule and is not merged. Until it is, the owner's "Codex audits exact SHAs" role is carried by verdicts in the `AGENTS.md` format.

## Where things live

This table is the answer to "where is the project state". Each kind of state has exactly one home; no other registry is created for it.

| Thing | Where | Notes |
|---|---|---|
| Rules | `AGENTS.md` on `main` | Changes only through a reviewed PR the owner merges |
| Roles, task flow, automation status | this file | Status table updated with evidence, never in advance |
| Ordered task plan | `docs/PLAN.md` | PR #35, **not merged** as of `685c5a0`. Owner sets priorities, GPT adds criteria, Claude updates statuses and evidence. One permanent ID per task; a parallel direction (workstream) is a group of tasks there, not a separate register |
| Theory | `docs/theory/` | PR #37 (CL-016, branch `claude/project-thread-ofxc12`), not merged. This file does not duplicate it |
| Roadmap A0–A12 | `docs/AUTONOMY_ROADMAP_SPEC.md` on `main` | |
| Overall progress | header of `docs/PLAN.md` | Not written yet. Denominator: the 13 stages A0–A12. A stage counts only when its acceptance criteria are met on `main` with CI on the merge commit. Anything else is reported as `NOT MEASURED`, never as a guessed percentage |
| Link task ↔ theory | `Theory:` field of a task in `docs/PLAN.md` (CLM-/OQ- IDs); task ID in the row of `docs/theory/THEORY_TO_CODE.md` | Described, not filled: 0 tasks carry `Theory:` in `docs/PLAN.md` at `c70e7a7` (PR #35), and 0 THEORY_TO_CODE rows name a task ID at `69766f1` (PR #37). A described link is not a filled one |
| Claims, handoffs, live coordination | Issue #22 | Protocol in `docs/coordination/PROTOCOL.md`, PR #32, **not merged** |
| Audit verdicts | the PR they audit, as an issue comment | Format in `AGENTS.md`. A copy in a chat proves nothing |
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

While a PR waits for an audit, work that does not depend on it continues. The open PR limit is set only in `AGENTS.md` ("Open PR limit").

## The self-update cycle, stage by stage

Target cycle: Task Discovery → Claim → Execution → CI → Audit → Validation → Persistence → Human Merge. "Automated" means a stage runs without a person starting that action, with the evidence named; "agent" means an agent does it when it runs; "manual" means a person does it; "missing" means nothing implements it yet. Checked against `main` = `685c5a0`.

| Stage | Development loop today | Copilot today | Evidence or gap |
|---|---|---|---|
| Task Discovery | Agent: Claude reads `docs/PLAN.md` (PR #35, not merged), written by the owner and GPT | Missing: the dispatcher chooses one of two fixed modules (`executor.py`, `task_queue.py`) as a workflow input | Next-task selection inside the core is PR #34 (A4), not merged |
| Claim | Agent: claims in Issue #22 | Missing | Claim checker only on PR #32's branch |
| Execution | Agent: Claude in its sessions | Automated **within a run**: Copilot CLI writes one test file with read-only tools, under a credit cap set by the core | Runs 39356711683 and 39523564470, job "Copilot writes one test file" success. Each run was started by a manual `workflow_dispatch` |
| CI | Automated | Automated **within a run**: the core validates the patch scope (`copilot_writer.py`), then a job with no permissions and no network runs only the new test on a throwaway copy | `ci.yml` on every PR; verify job success in both Copilot runs |
| Audit | Agent: Codex on request (blocked by usage limit since 2026-10-23 09:30 UTC); GPT when the owner opens a session | Manual: GPT content review of the artifact | Run 39356711683's test REJECTED for duplication; run 39523564470 still waits |
| Validation | Agent: Claude recomputes labels with `audit_verdict.py` | Missing | The repository does not apply labels itself |
| Persistence | Manual: only a merge persists a change | Missing: the result is an artifact kept 7 days (artifact 12311398353 expires 2026-10-28); nothing is pushed, no branch or PR is opened | No path from a Copilot artifact to a commit exists |
| Human Merge | Manual, by design | Manual, by design | See "No automatic merge" |

### What Copilot can do on its own today

Once a run is started, Copilot writes one new test file and the core checks its scope and runs it in isolation, without anyone touching it. That is execution and a first check, at the RUNTIME level, for one task kind (a test file for one of two modules).

It cannot yet start itself, pick its own task, claim it, turn an accepted result into a branch or PR, or keep its result beyond the 7-day artifact. All three Copilot workflows are `workflow_dispatch` only. So Copilot is not yet a self-update tool that runs without a manual start of each run, and that must not be claimed until a run without a manual start is observed. Making it one needs, at least, a trigger the core owns (for example a schedule that asks the budget and the plan) and a bounded path from an accepted artifact to a PR. Both touch workflows, so each needs the owner's explicit approval.

### Distinctions that are never collapsed

- proposing a change ≠ executing it;
- execution ≠ a passed check;
- green CI ≠ an independent audit;
- a saved artifact ≠ a proven update of the core;
- an integration that exists ≠ proven autonomy;
- approval ≠ evidence of execution.

Copilot's independence means doing its provided tasks without a manual start of every action. It never means bypassing checks, unbounded authority or automatic merge.

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

- **Role of the human in the core (`OQ-009`, owner, 2026-10-23 14:55 UTC).** The human is not a mandatory selector of the core's inner research and learning loop. Internal selection of a candidate, research acceptance of a hypothesis and authority to change the system are separate operations; authority is never inferred from `ACCEPTED`, a passing test or an internal selector's choice. Autonomous research is not autonomous change of the core: core mutations stay behind a controlled-commit boundary with the owner's approval, and there is no automatic merge. The decision is recorded and linked to requirements in `docs/theory/OPEN_QUESTIONS.md` (PR #37); this file does not restate its reasoning. It is an architectural decision, not evidence that it is implemented. In the development loop described here, the owner's merge gate applies either way.

## Open questions for the owner

- **Codex verdicts.** Whether a Codex bot review counts as a verdict (plan item P2), which changes the review rules in `AGENTS.md`.

## Work protocol

Proposed (owner, 2026-10-23 15:38 UTC: "do not declare it final before my agreement"). It ties messages to the homes listed in "Where things live": **state lives on GitHub and in those files; a message carries only what changed, with exact references.** No message restates the whole project, the roles or the rules.

### Three status scales, never mixed

| Scale | Values | Used for | Defined in |
|---|---|---|---|
| Task status | `PROPOSED`, `READY`, `IN_PROGRESS`, `BLOCKED`, `IN_REVIEW`, `DONE`, `REJECTED` | a task in `docs/PLAN.md` | here and `docs/PLAN.md` |
| Evidence level | `DESIGN` … `CI_PROVEN`, always with an exact SHA | a claim that something works | `AGENTS.md` |
| Knowledge status | `OBSERVED` … `SUPERSEDED` | a theory claim (`CLM-`) | `docs/theory/INDEX.md` |

`pending-audit`, `blocked-review` and `ready-for-owner` are PR labels inside `IN_REVIEW`, not task statuses. Write `Verdict: ACCEPTED` or `CLM: ACCEPTED` in full; the bare word means different things on different scales.

### Messages

There are four message types: TASK, REPORT, VERDICT and STATE. STATE is not a separate format: it is REPORT in full mode.

**TASK** (owner or GPT → Claude). Claude adds it to `docs/PLAN.md` if it is not there.

```
TASK <ID> <one-line goal>
Accept: <checkable criteria>
Theory: <CLM-/OQ- IDs or none>
Depends: <task ID / PR or none>
Approved: <what the owner explicitly allowed, or none>
```

**REPORT** (Claude → owner or GPT). One line per task that changed, then the shared fields.

```
REPORT <UTC date> CYCLE <cycle ID>
<ID> <task status> <PR> <head SHA, 40 chars> CI <run id> <ok|fail> — <what changed, one line>
Tests: <command> — <passed/failed counts>
Proven: <claim — evidence>
Not proven: <claim — what is missing>
Defects: <open findings or failures, each with file/run, or none>
NEEDS_OWNER: <exact question, or merge PR#/SHA, or NONE>
NEXT: <ID — step — completion criterion>
```

The full BEFORE → ACTION → AFTER → RESULT report from `AGENTS.md` is written for a significant change only, in the PR body, not in chat. **STATE** (any party asks "state?"): a REPORT in full mode, with one line for every open task instead of only the changed ones, plus `Progress: <stages met>/13 A-stages, or NOT MEASURED>`. It is built from GitHub and `docs/PLAN.md`, not from memory.

**Machine fields from the earlier handoff format.** They are kept as REPORT fields, not as a separate record:

| Earlier field | REPORT field |
|---|---|
| `CYCLE_ID` | `CYCLE` (the tick or session that produced the report) |
| `STATE` | task status in each task line. This is the status of one task, not the STATE message: the message is a snapshot of the whole project, the field is one task's status. Automation must not treat them as one field |
| `VERIFIED` | `Proven` |
| `DEFECTS` | `Defects` |
| `TESTS` | `Tests` and the CI run in each task line |
| `REQUESTED_ACTION` | `NEEDS_OWNER` and `NEXT` | "Next" (Далее) means: continue the first `READY` task in `docs/PLAN.md`, within authority and the PR limit.

**Audit handoff with ChatGPT.** These two blocks are kept as they were agreed. ChatGPT has no proven unattended channel yet (see "Automation status"), so the owner may carry them. Every field names exact values. "unknown" is a valid answer; a guess is not.

**Owner → ChatGPT** (ask for an audit or a decision):

```
Agent: Owner → GPT
Task: <task ID and one-line goal>
PR: <number and URL>
head_sha: <40-character SHA>
CI: <run id> — <conclusion> on that head_sha
Claude reports — proven: <claims with evidence>
Claude reports — not proven: <claims and what is missing>
Ask: <audit this head | decide X | review plan Y>
Reply with: the GPT → Claude block below. A verdict goes on the PR as an issue comment in the AGENTS.md format.
```

**ChatGPT → Claude** (verdict, findings or instructions; posted in Issue #22 or the PR, or forwarded by the owner):

```
Agent: GPT
Task: <task ID>
PR: <number>
head_sha: <the exact SHA that was checked>
CI checked: <run id> — <conclusion>
Verdict: ACCEPTED | REJECTED | NO VERDICT (<reason>)
Proven: <claims with evidence>
Not proven: <claims and what is missing>
Findings: <numbered, each with file and line, or "none">
Owner decision needed: <none | the exact question>
Owner decision given: <none | the decision, with date and who>
Next SEQ: <one step, acceptance criteria, permissions it needs>
```

**VERDICT** (GPT/Codex → the PR): only the `AGENTS.md` format, as an issue comment on that PR. The GPT → Claude block reports a verdict; it does not replace it.

### Rules for these messages

- **Owner decisions.** "Owner decision given" and `Approved:` count only when the owner expressed the decision himself: his own message in the project thread, on the PR or in Issue #22, or his choice on a decision card. Silence, an agent's summary or inference, a label, green CI or an `ACCEPTED` verdict is never an owner decision.
- **Exact head.** A verdict, a CI result and a REPORT line are valid only for the `head_sha` they name. A block about another SHA than the PR's current head is stale and changes nothing. After a new head: CI runs again on it; a new verdict for the new head is required (`AGENTS.md`); the auditor may limit the review to `git diff <audited SHA>..<new head>` but must name the new head; any claim of RUNTIME or PERSISTED is observed again if the change touches that path.
- **Independent check.** A REPORT is the executor's account, not independent confirmation. Every SHA and run id in it can be checked directly: `https://api.github.com/repos/Autopoiesis-Intelligence/autopoiesis-core/actions/runs/<run id>` shows `head_sha` and `conclusion`.

### What exists and what is only described

Checked against GitHub on 2026-10-23 (`main` = `4f730e7`). The text of this file is not evidence that anything runs; each row changes only with a new GitHub observation.

| Part | State |
|---|---|
| Evidence ladder, report format, verdict format, PR limit, no merge by agents | Implemented as rules on `main` (`AGENTS.md`) |
| Audit label computation (`audit_verdict.py`) | Implemented on `main`; applied by an agent, not by the repository |
| Task register and statuses | Described: `docs/PLAN.md`, PR #35 not merged; its status set predates the scale above (`IN_REVIEW` covers both) |
| Roles and this protocol | Described: this file, no PR yet (PR limit) |
| Theory base | Described: PR #37 not merged |
| Claims and their checker | Described: PR #32 not merged |
| `Theory:` links, progress header | Not written |
| REPORT built automatically from GitHub | Not implemented |
| ChatGPT sending TASK or verdicts without the owner | NOT PROVEN |

## Keeping this file current

Claude updates the status table in the same PR as the change that produces new evidence, or in a small docs PR after an observation, always with the SHA, run id or comment id. A role changes only by the owner's decision, recorded here with its date.
