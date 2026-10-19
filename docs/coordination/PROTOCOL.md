# GPT ↔ Claude coordination protocol

Status: proposed in PR; not active policy until reviewed and merged.

## Purpose

Coordinate work on this repository when GPT and Claude operate on separate schedules, including a possible 10-minute polling interval. Scheduling is not itself synchronization. Synchronization requires fresh GitHub evidence, explicit task ownership, isolated branches, and a durable handoff.

## Source-of-truth hierarchy

1. Live GitHub repository state: exact refs/SHAs, PR base/head, workflow runs and artifacts.
2. Merged repository policy and this protocol, once accepted.
3. Open PR diffs and review comments for proposed changes.
4. `docs/coordination/STATE.md`, `DECISIONS.md`, and `LOG.md` as navigation and handoff.
5. Agent reports, old chat summaries, and prior checkpoints as unverified pointers only.

If sources conflict, stop and record the discrepancy. Never infer current state from an old SHA or report.

## Ten-minute cycle contract

Every scheduled run should be a bounded reconciliation cycle, not an instruction to make a code change every ten minutes:

1. Fetch live default-branch SHA, active branches, open PRs, exact PR head/base SHAs, and all relevant workflow runs.
2. Read the latest coordination state and the most recent meaningful log entry.
3. Detect whether another agent already owns the task or is modifying overlapping files/dependencies.
4. If no safe, unclaimed task exists, perform a read-only audit and report `NO_CHANGE`; do not invent work.
5. Choose at most one bounded task with satisfied dependencies. Prefer review, tests, and diagnostics before implementation.
6. Work on a dedicated branch and PR. Never write directly to `main`, force-push, merge or close PRs automatically.
7. Before writing, re-check the branch head. If it moved unexpectedly, stop and reconcile rather than overwrite.
8. Record a meaningful handoff only when state changed, a decision is needed, a blocker appeared, or evidence was obtained. Do not create heartbeat commits or repetitive comments.
9. Finish with BEFORE → ACTION → AFTER → RESULT → PROVEN / NOT PROVEN → REJECTED DIRECTIONS → NEXT SEQ.

## Task ownership and concurrency

- One agent owns one bounded task at a time.
- The task claim must include agent, task ID, target PR/branch, exact starting SHA, files in scope, and acceptance criteria.
- GPT and Claude must not edit the same branch or overlapping files concurrently.
- Before starting work, inspect recent commits, PR updates, and the live handoff for an existing claim.
- A claim is stale only after checking GitHub activity and asking for/reconciling the latest available result; elapsed time alone does not prove that work stopped.
- If a shared mutable issue/board is later configured, use it for short-lived claims and handoffs. Until then, use PR descriptions/comments and this versioned record; never pretend a coordination lock exists when it does not.

## Evidence requirements

For every substantive claim record:
- repository and exact ref/SHA;
- PR URL and exact base/head SHA, if applicable;
- command/test or workflow name;
- workflow run ID, conclusion, and run head SHA;
- artifact URL/hash where relevant;
- what the evidence proves and what it does not prove.

Evidence ladder: DESIGN → IMPLEMENTED → REACHABLE → RUNTIME → PERSISTED → AUDITED → CI_PROVEN. Evidence at one SHA does not prove a different SHA. Unit/synthetic PASS does not prove production runtime or autonomy.

## Permissions and stop conditions

Stop and report when:
- the exact SHA or relevant CI result cannot be retrieved;
- a PR's base/head or dependency chain is unclear;
- two agents have overlapping active work;
- state is malformed, stale, contradictory, or untrusted;
- a change affects workflow permissions, repository settings, schema/migrations, runtime execution, or authority boundaries without explicit owner approval.

Never auto-merge, auto-close, force-push, delete data, weaken checks, or commit generated runtime files such as `RESULTS.json` and `TASK_QUEUE.json`.

## Ten-minute schedule recommendation

Use a 10-minute schedule primarily for **read-only reconciliation**. Permit implementation only when the task is explicitly claimed, bounded, and has no overlapping owner. A scheduler must avoid overlapping runs (concurrency group / no parallel instances), use a finite timeout, and avoid posting duplicate reports. A frequent poll is not proof of successful execution and should not create a new commit when nothing changed.

## Activation

This protocol becomes operational only after review and merge of the PR containing it, and after the scheduler is configured to read it. Until then, it is a proposal, not an enforced repository rule.
