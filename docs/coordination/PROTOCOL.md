# Agent coordination protocol

Status: proposed in a PR; not active policy until reviewed and merged by the owner.

This file covers coordination only: who owns which task, how a claim is made, released or taken over, how a result is handed off, and when a PR is ready for the owner. Evidence rules, stop conditions, safety rules, the audit verdict format and the report format live in [`AGENTS.md`](../../AGENTS.md). They are not repeated here; if the two ever disagree, `AGENTS.md` wins.

## Where state lives

1. Live GitHub state is the source of truth: refs and SHAs, PR base and head, workflow runs and artifacts.
2. Issue [#22](https://github.com/Autopoiesis-Intelligence/autopoiesis-core/issues/22) is the live ledger for claims and handoffs. Every claim there is still checked against live GitHub state.
3. Audit verdicts live on the PR they audit (see `AGENTS.md`, "Review and audit").
4. `DECISIONS.md` records durable decisions. It changes only through a reviewed PR, so it never holds live state.

Agent reports, chat summaries and older checkpoints are pointers to check, not proof.

## Identity

All agents post through one GitHub account, so the comment author does not say which agent wrote it. Two signals do:

- The first line of every claim, handoff or verdict is `Agent: Claude|GPT|Copilot|Manus`.
- GitHub records the app that posted a comment in `performed_via_github_app`. This is the proof; the text line alone is not.

| Agent | App id | App slug | Task prefix |
|---|---|---|---|
| Claude | `1236702` | `claude` | `CL-` |
| GPT | `1144995` | `chatgpt-codex-connector` | `GP-` |
| Copilot | none known | none known | `CP-` |
| Manus | none known | none known | `MN-` |

Copilot and Manus have no verified app yet, so their claims are not counted. Until one is verified, Claude or GPT claims work on their behalf.

## Claims

A claim comment in #22 starts with this block:

```
Agent: <agent>
Task: <task ID>
Claim: OPEN | RELEASED | STALE
```

The details follow after a blank line: starting SHA, branch and PR, files in scope, acceptance criteria and dependencies.

Rules:
- An agent uses only task IDs with its own prefix for `OPEN` and `RELEASED`.
- A task ID is used once. After `RELEASED` or `STALE` it cannot be opened again; new work gets a new ID.
- An agent holds at most one `OPEN` claim at a time. Agents with separate claims work in parallel; they do not wait for each other.
- Before editing, an agent checks that no other open claim covers the same branch or files. If two claims overlap, both stop and reconcile in #22.
- `RELEASED` comes from the owner of the claim when the task is done or dropped.
- An owner keeps a long task alive with a new `OPEN` comment for the same task, or with a commit on its branch or an update to its PR.

`autopoesis/coordination.py` computes the claims from the comments. The exact command for a scheduled run is in `SCHEDULER_PROMPT.md`. Comments in older free-text formats are ignored and never converted.

## Stale claims

A claim expires when 24 hours pass with no activity: no new `OPEN` comment from its owner, no commit on its branch and no update to its PR.

- The checker sees only the activity it is given. Before marking a claim stale, the agent checks the claim's branch and PR on GitHub (commands in `SCHEDULER_PROMPT.md`).
- Only another agent may mark a claim stale, and only after it has expired. It posts `Claim: STALE` under the expired task's ID. A mark before expiry is rejected, so running work is never taken over.
- The agent taking over opens a new task under its own prefix and works on a new branch. It never pushes to the stale branch.
- The original owner can come back with a new task. The stale claim stays in the history.

## Handoff

A result is handed off with a comment in #22 that starts with `Agent:` and `Task:` and names the exact head SHA, the PR, and the CI run on that SHA. The report format is the one in `AGENTS.md`. A handoff that asks for an audit names the PR and SHA to audit.

## Ready for owner

A PR is ready for the owner only in the state `READY_FOR_OWNER` defined in `AGENTS.md`:
- there is a valid `Verdict: ACCEPTED` for the PR's current head SHA, posted by an authorized auditor app;
- CI is green on that same head.

The `ready-for-owner` label marks this state. A new push removes it. The owner is the only merge gate; a ready PR is still merged only by the owner.

## Cadence

Neither agent runs often enough for tight coordination, so nothing in this protocol depends on a fast schedule.

- Claude: a scheduled task every 4 hours, plus runs when the owner writes in the project thread or a subscribed PR changes. The scheduler allows at most hourly runs.
- GPT: runs when the owner opens a chat with it. GPT reported one daily scheduled automation (Issue #22, comment 6279556894). Whether that automation can read and write GitHub is not verified.
- A run that finds nothing new posts nothing. There are no heartbeat comments or commits.

## No deadlocks

- A missing audit blocks only the PR waiting for it and the tasks that depend on it. Other tasks continue.
- An audit pending for more than 7 days becomes `audit-overdue` and goes to the owner (see `AGENTS.md`).
- The owner can decide any PR at any time. The protocol never makes the owner wait for an agent.
