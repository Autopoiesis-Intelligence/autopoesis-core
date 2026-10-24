# Owner acknowledgement of a failed production cycle run (N3, design only)

Status: DESIGN (N3, completed as N8). No code. Author: Claude; not audited.

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

### Format

A file on main, `state/acknowledged_cycle_failures.json`:

```json
{
  "version": 1,
  "acknowledged": [
    {
      "run_id": 40100000000,
      "run_attempt": 1,
      "workflow_path": ".github/workflows/autopoiesis-cycle.yml",
      "head_sha": "<40 hex of the failed run>",
      "conclusion": "failure",
      "restore_from_run_id": 40090000000,
      "reason": "one line: what failed and why the state may be discarded",
      "pr": 61
    }
  ]
}
```

Every field is required and strictly typed. Unknown keys, duplicate `(run_id, run_attempt)`
pairs, a non-list `acknowledged` or a `version` other than 1 refuse the whole cycle.

### Matching rules

1. The cycle reads the file only from its own checkout of main. It never takes it from inputs,
   the API or an artifact.
2. An entry matches a run only if all of `run_id`, `run_attempt`, `workflow_path`, `head_sha`
   and `conclusion` equal the values in the paginated run history that the selector already
   validates. A partial match refuses (ID substitution, wrong workflow, stale or wrong SHA).
3. Only a non-clean run can be listed (`conclusion` in failure, cancelled, timed_out, or
   `run_attempt` > 1). Listing a clean success refuses, because that would be a rollback.
   A run with `conclusion == null` (queued or running) cannot be listed.
4. Listing a run that is absent from the history refuses (typo, other repository, expired history).
5. After acknowledged runs are skipped, the existing rule applies unchanged: the newest remaining
   relevant run must be a clean success. It must also equal the entry's `restore_from_run_id`
   for the newest acknowledged run. Otherwise the cycle refuses, so the owner approves the exact
   fallback, not just the failure.
6. Several failures in a row need one entry each. An unlisted failure newer than the fallback
   still refuses.

### Reuse and staleness

- An entry is bound to one `(run_id, run_attempt, head_sha)`. It cannot unlock another run.
- Once a newer clean success exists, the entry is inert: the newest relevant run is that
  success, so nothing is skipped. Entries stay in the file as history. Removing them is a
  separate reviewed PR.
- A re-run of an acknowledged run gets a new `run_attempt` and needs its own entry.
- The newest-run rule still means one new failure after the fallback blocks again until it is
  acknowledged too.

### Why discarding the failed run's state is safe

The cycle token is `contents: read`. A failed run can leave state only in its own artifact, and a
failed run is never selected as a restore source.

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

1. A listed failed run is skipped and the listed `restore_from_run_id` is selected.
2. An unlisted newer failure still refuses (current behaviour kept).
3. Two consecutive failures: one listed refuses, both listed selects the fallback.
4. Mismatch in each one of `run_attempt`, `workflow_path`, `head_sha`, `conclusion` refuses.
5. `restore_from_run_id` not equal to the newest remaining clean success refuses.
6. Listing a clean success, an unknown run ID or a running run refuses.
7. A malformed file (unknown key, duplicate pair, wrong version, wrong type) refuses.
8. After a newer clean success, a stale entry changes nothing.
9. The file is read from the checkout path only. A contract test checks the workflow passes no input for it.

## Question for the owner

Do you approve implementing this as a file on main, changed only through a PR you merge?
Accepting it means a PR with an entry is the only way to restart the cycle after a real failure.
The alternative is that a real failure keeps the cycle stopped until a code change.
