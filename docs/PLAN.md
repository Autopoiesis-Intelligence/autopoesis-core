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
| Codex verdict on #33 at current HEAD `a83711f5e749fc63c4e7480ada697fb8e8134063` | merge of #33 | GPT/Codex, then owner |
| Codex verdict on #34 at current HEAD `f3c84b2e003932acdf29647ac9dfd600735f0598` | merge of #34 | GPT/Codex, then owner |
| `@codex review` requested on current heads #33–#37; no current-head verdict confirmed yet | close audit blockers | GPT/Codex; verify receipts by exact SHA |
| Five own PRs already waiting (limit 5) | opening the P2 PR | owner merges or raises the limit |

## Tasks

### P0 — A3 closed task lifecycle — `IN_REVIEW` (PR #33)
- **Goal:** only legal transitions; DONE only after a PASS for the item's own source since its latest IN_PROGRESS; no unchecked status writer.
- **Evidence so far:** at `8952df5`: PR CI 39931369279, seed 39931361330, restore 39931975513. Codex findings fixed since `74c3126`: stale verifier (attempt binding), PASS bound to the tested code revision, history edges replayed against the table on load, attempt counter checked against history, attempt type.
- **Remaining:** a Codex verdict on current HEAD `a83711f5e749fc63c4e7480ada697fb8e8134063`; owner merge; CI on the merge commit.

### P0 — A4 deterministic next-task selection — `IN_REVIEW` (PR #34)
- **Depends on:** #33.
- **Evidence so far:** at `480533b` (contains #33 `8952df5`): PR CI 39932079992. Codex found no major issues on `79e4692`; its P2 on `88e6671` (malformed priority) is fixed in `d9151ef`.
- **Remaining:** a Codex verdict on current HEAD `f3c84b2e003932acdf29647ac9dfd600735f0598`; after #33 merges, update the branch onto `main`, re-run CI, and get a verdict on the new head; owner merge.

### P1 — A9 task leases and recovery of stuck tasks — `IN_REVIEW` (PR #36, chained)
- **Depends on:** #34 (and therefore #33). Built on the #34 branch; if #33/#34 change, A9 is rebuilt.
- **Evidence so far:** at `4787a13` (contains #34 `480533b`): PR CI 39932167542, seed 39932159904, restore 39932194829. Codex P1s fixed: two live leases rejected on load; replayed PASS needs a revision and a lease token.
- **Remaining:** a Codex verdict on current HEAD `56966962dc284e912f8deb8e8da5f97048539b6d`; owner confirmation of the ci.yml probe lines; merge after #34.
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

### P2 — Count Codex bot reviews as verdicts — `READY` (branch prepared, PR not opened)
- **Observed (2026-10-23):** PRs #20–#34 have no review from a Codex bot account. Every Codex post so far is an issue comment by the shared account with `performed_via_github_app = chatgpt-codex-connector`. Reviews are not read by `audit_verdict`.
- **Observed (2026-10-23 08:35 UTC):** commenting `@codex review` triggers a Codex review by `chatgpt-codex-connector[bot]` on the exact head (summary comment with `codex-review-state`, inline findings, 👍 when clean). First seen on #33 comment 6360909547. At 09:30 UTC it stopped with "You have reached your Codex usage limits for code reviews".
- **Independent of #33/#34/#36:** it touches only `autopoesis/audit_verdict.py`, its tests and `AGENTS.md`, branched from `main` `685c5a0`.
- **Acceptance:**
  1. A summary comment counts only from the bot account (`chatgpt-codex-connector[bot]`, id `199175422`, type `Bot`) through the auditor app.
  2. It counts only for `status: completed` and a `commit_sha` equal to the current head; an older head is `STALE_SHA`.
  3. Findings → `REJECTED`; no findings and nothing unresolved → `ACCEPTED`; anything else is no verdict.
  4. A human or the shared account pasting the marker counts for nothing; a running or failed review (usage limit) counts for nothing.
  5. The bot's verdict dates from the comment's last edit when compared with GPT verdicts.
- **Evidence:** branch `claude/cl-015-codex-review-verdict` at `f27cc15`, CI 39970453578 (workflow_dispatch) green; 8 new tests fail on `main`. On live #33/#34/#36 comments it returns `PENDING_AUDIT` (all bot reviews there are `failed`).
- **Blocked on opening the PR:** five own PRs are already waiting (limit 5). It changes the review rules in `AGENTS.md`, so it needs the owner's approval before merge.

### P3 — Coordination protocol and claim checker — `IN_REVIEW` (PR #32)
- **Evidence:** GPT ACCEPTED at `ce55344c091d7eb7b5b6e7ffb688918c630807e9` (comment 6302030182); CI 39501106634.
- **Remaining:** owner merge; then the scheduled loop reads the protocol from `main`.

### Backlog (not READY until acceptance criteria are written)
- A10 bounded orchestration: one scheduled run that recovers, selects, executes, verifies and records, with budgets and a disable switch. **Depends on:** #33, #34, #36. Proposed acceptance criteria (Claude, for GPT and the owner to confirm or edit):
  1. One run performs, in order: recover expired leases, select one task, execute it under its lease, verify, then DONE or back to OPEN; each step is a history event.
  2. A disable switch read at the start of the run stops it before any queue write, and the run says so in its output.
  3. Budgets: at most one task and a fixed wall-clock limit per run; exceeding the limit releases the task back to OPEN with a reason.
  4. A run with nothing eligible leaves the queue file byte-identical and reports "no work".
  5. Two overlapping runs never both act on a task (lease plus queue lock); a test starts two runs at once.
  6. The run's result is persisted in the CI artifact and survives the restore path, as the seed/restore probes do now.
  7. No network, credentials or LLM calls inside the core; the run invokes only the bounded task types in `run_tasks.py`.
- A Copilot test proposal for `autopoesis/task_queue.py` (run 39523564470) still awaits GPT's content audit.
