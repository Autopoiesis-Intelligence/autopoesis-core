# Work plan

The standing, ordered plan for autopoiesis-core. The owner sets priorities. GPT adds strategy and acceptance criteria. Claude takes the first unblocked `READY` task without waiting for a "next" command, records evidence here and in Issue #22, and marks contradictions instead of silently working around them. Only the owner merges; nothing here authorizes auto-merge or changes to `main`, workflows, permissions or settings.

## How to use

- **Statuses:** `READY` (can start), `BLOCKED` (names its blocker), `IN_REVIEW` (PR open, waiting for audit or merge), `DONE` (merged, with merge SHA and CI run).
- **Every task has:** goal, acceptance criteria, dependencies, and the evidence that will count. A task without acceptance criteria is not `READY`.
- **Dependencies:** a task may start on a branch built on an unmerged PR only if that is listed under *Depends on*. If the base PR changes after audit, the dependent PR is rebuilt on the new base and audited again.
- **Limit:** at most 5 own PRs waiting at once (owner decision, 2026-10-23).
- **Evidence:** a verdict counts only per `AGENTS.md` ("Review and audit"): an issue comment through the Codex app that names the PR and the exact head SHA. Green CI, a bot reaction or a chat message is not approval.
- **Editing:** GPT and the owner edit priorities and add tasks; Claude updates statuses and evidence. Disagreements go to Issue #22, not into silent edits.

## Current blockers

| Blocker | Unblocks | Who |
|---|---|---|
| Codex verdict on #33 at `9c4f60f0d08f4aa279be2793e22d8c72a6ecde75` | merge of #33 | GPT/Codex, then owner |
| Codex verdict on #34 at `79e469250036adf8125e7f6f6242ad7b940c2627` | merge of #34 | GPT/Codex, then owner |
| Unknown whether Codex automatic PR review is available for this repository | P2 | owner checks Codex settings |

## Tasks

### P0 — A3 closed task lifecycle — `IN_REVIEW` (PR #33)
- **Goal:** only legal transitions; DONE only after a PASS for the item's own source since its latest IN_PROGRESS; no unchecked status writer.
- **Evidence so far:** CI 39924317283; seed run 39924328639 and restore run 39924378188 at `9c4f60f`. Codex REQUEST_CHANGES on `0833384` is addressed in `74c3126`; the Codex P1 on `74c3126` (stale verifier, comment 6360484055) is addressed in `9c4f60f` by binding evidence to the attempt.
- **Remaining:** Codex verdict on `9c4f60f`; owner merge; CI on the merge commit.

### P0 — A4 deterministic next-task selection — `IN_REVIEW` (PR #34)
- **Depends on:** #33.
- **Evidence so far:** CI 39924500783 at `79e4692` (contains #33 `9c4f60f`), including an 8-process concurrent-selection test.
- **Remaining:** Codex verdict; after #33 merges, update the branch onto `main`, re-run CI, and get a verdict on the new head; owner merge.

### P1 — A9 task leases and recovery of stuck tasks — `IN_REVIEW` (PR #36, chained)
- **Depends on:** #34 (and therefore #33). Built on the #34 branch; if #33/#34 change, A9 is rebuilt.
- **Evidence so far:** at `08f1525` (contains #34 `79e4692`): PR CI 39924792696, seed 39924784538, restore 39924872876. Evidence binds source, attempt and lease token.
- **Remaining:** Codex verdict on `08f1525`; owner confirmation of the ci.yml probe lines; merge after #34.
- **Design and test scenarios:** `/mnt/project-files/reviews/autonomous-stack/A9_LEASE_PLAN_2026-10-23.md`, summarized here.
- **Acceptance:**
  1. The lease owner, token and expiry are persisted, validated by `load_queue`, and survive restore.
  2. Acquire, renew, advance, verification and recovery run under the one queue lock.
  3. Two executors never hold unexpired leases at the same time.
  4. After expiry the old owner cannot renew, record evidence or write DONE with its stale token, even before recovery runs.
  5. Recovery returns expired items to OPEN with a `LEASE_EXPIRED` history event. With nothing expired, recovery leaves the file byte-identical.
  6. DONE still requires a fresh PASS for the item's source, recorded under the current lease.
  7. One test kills an executor process mid-task, lets the lease expire, starts a new executor, and shows the old one is refused.
- **Not proven by A9:** an unattended loop (A10/A11).

### P2 — Count automatic Codex reviews as verdicts — `BLOCKED` (owner checks Codex settings)
- **Observed (2026-10-23):** PRs #20–#34 have no review from a Codex bot account. Every Codex post so far is an issue comment by the shared account with `performed_via_github_app = chatgpt-codex-connector`. Reviews are not read by `audit_verdict`.
- **If automatic review is confirmed:** a separate PR extends `audit_verdict` to accept a review only from the Codex bot identity whose `commit_id` equals the head SHA and whose body carries the `Verdict:` block. Any other review stays ignored. This changes the review rules in `AGENTS.md`, so it needs the owner's approval before merge.

### P3 — Coordination protocol and claim checker — `IN_REVIEW` (PR #32)
- **Evidence:** GPT ACCEPTED at `ce55344c091d7eb7b5b6e7ffb688918c630807e9` (comment 6302030182); CI 39501106634.
- **Remaining:** owner merge; then the scheduled loop reads the protocol from `main`.

### Backlog (not READY until acceptance criteria are written)
- A10 bounded orchestration: one scheduled run that recovers, selects, executes, verifies and records, with budgets and a disable switch.
- A Copilot test proposal for `autopoesis/task_queue.py` (run 39523564470) still awaits GPT's content audit.
