# Owner acknowledgement of a failed production cycle run (N3, design only)

Status: DESIGN. No code. Author: Claude; not audited.

## Problem

`select_prior_successful_run` (`autopoesis/scheduled_state.py`, #49) refuses when the newest
relevant cycle run on main is not `success` with `run_attempt == 1`. That is correct: an older
snapshot must not silently replace a newer run's outcome. But nothing ever clears the refusal.
After one real failed, cancelled or timed-out run, every later scheduled run fails, and bootstrap
is refused too because a prior run exists. Today the only way out is a code change.

## Constraint that shapes the design

All agents and the owner use one GitHub account. `github.actor`, environment reviewers and
dispatch permissions cannot tell the owner from an agent. So an "owner-only" dispatch input
would be owner-only only by rule, not by mechanism. Rejected for that reason.

The only step that is owner-only in practice is a merge into protected `main` (PR, required
`test` check, no force push, merges by the owner). The acknowledgement should therefore be data
on `main`, changed only through a reviewed PR.

## Proposal

1. A file on main, `state/acknowledged_cycle_failures.json`:
   ```json
   {"version": 1, "acknowledged": [{"run_id": 123, "run_attempt": 1, "reason": "…", "pr": 61}]}
   ```
   Every field is required and strictly typed; unknown keys, duplicates or a non-list refuse.
2. The cycle reads the file from its own checkout (the exact main SHA of the run), never from
   inputs, the API or an artifact.
3. The selector skips a relevant run only when its `(id, run_attempt)` is listed **and** its
   outcome is not a clean success (`conclusion != "success"` or `run_attempt != 1`).
   It refuses if a listed run is a clean success (acknowledging a good run would be a rollback),
   or if a listed run id is absent from the history (typo or wrong repository).
4. After skipping acknowledged runs, the existing rule applies unchanged: the newest remaining
   relevant run must be a clean success, and it becomes the restore source.
5. Acknowledging discards the failed run's state. That is safe because the cycle token is
   `contents: read`: a failed run can leave state only in its own artifact, which is never
   selected.
6. An in-progress or queued run (`conclusion == null`) cannot be acknowledged.

## Threats considered

| Threat | Result under this design |
|---|---|
| An agent dispatches with a crafted input to skip a failure | No input exists; the list is read only from the run's own main checkout |
| An agent pushes the file to main directly | Blocked by `main-protection` (PR and `test` check required) |
| A PR silently adds an entry | Visible in review; the owner merges; the entry names the run and the PR |
| Acknowledging a good run to roll back to an older snapshot | Refused: only non-clean runs can be listed |
| A forged run history makes a failure look acknowledged | Matching is on `(id, run_attempt)` from the same paginated API history the selector already validates |
| Partial state left by the failed run | The token is `contents: read`; the failed run's artifact is never a restore source |

Residual risk: on a single shared account, PR review and the merge are procedural controls, not
identity checks. That is the same trust boundary as every other change to main.

## Owner procedure

1. Claude reports the failed run ID, attempt, cause and the source run it would fall back to.
2. Claude or GPT opens a PR that adds one entry. An independent audit checks the run ID.
3. The owner merges. The next scheduled run restores from the run before the failure.

## Tests the implementation would need

- A listed failed run is skipped and the older success is selected.
- An unlisted newer failure still refuses (current behaviour kept).
- Listing a clean success refuses; listing an unknown id refuses; a malformed file refuses.
- A listed run with a different `run_attempt` does not match.
- Two consecutive failures need two entries.

## Open questions for the owner

- Should one entry also cover later re-runs of the same run, or only the exact attempt? (Design: exact attempt.)
- Should the file live under `state/` or `docs/`? (Design: `state/`.)
