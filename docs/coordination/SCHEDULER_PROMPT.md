# Scheduled run prompt (Claude)

The live prompt is stored in Claude's scheduled task "autopoiesis-core dev loop" (cron `47 */4 * * *`, every 4 hours). The scheduler allows at most hourly runs. This file is the reviewed reference for that prompt; when the two differ, update the scheduled task to match this file after the PR is merged.

On each run:

1. Make one cheap check first: the `main` SHA, open PRs with their head SHAs, and the newest comment in Issue #22. If nothing changed and nothing is due, post nothing and stop.
2. Compute the claims in #22 from a checkout of `main`, with exactly this command:

   ```bash
   gh api --paginate --slurp "repos/Autopoiesis-Intelligence/autopoiesis-core/issues/22/comments?per_page=100" | python -m autopoesis.coordination -
   ```

   It prints the claims as JSON. Do not start work that overlaps another agent's open claim.

   The input comes from GitHub at run time: `gh api` reads every comment of Issue #22, page by page, and `--slurp` joins the pages into one JSON list. If `gh` fails, the checker gets empty or broken input and exits with code 2 and "claims unknown". A non-zero exit means stop: claims are unknown, not empty.

   The command passes only the comments, so `expired: true` means only that #22 has been silent for 24 hours. Before posting `Claim: STALE` for another agent's task, check the branch and PR named in that claim for activity in the last 24 hours:

   ```bash
   gh api "repos/Autopoiesis-Intelligence/autopoiesis-core/commits?sha=<branch>&since=<UTC time 24 hours ago>" --jq length
   gh api "repos/Autopoiesis-Intelligence/autopoiesis-core/pulls/<number>" --jq .updated_at
   ```

   If there is a commit or a PR update inside the window, do not mark the claim stale. These timestamps can also be given to the checker as `activity` in a facts file (`{"comments": [...], "activity": {"<task>": ["<time>", ...]}}`).
3. Before editing, post a claim block (`Agent: Claude`, `Task: CL-…`, `Claim: OPEN`) with the starting SHA, branch, files in scope and acceptance criteria.
4. Work on a `claude/` branch and a PR. Re-check the branch head right before writing.
5. Record the exact head SHA and the CI run on that SHA. A queued run is not a pass.
6. Hand off in #22 with the report format from `AGENTS.md`, then post `Claim: RELEASED`.
7. Never merge, enable auto-merge, force-push, write to `main`, or change workflows, permissions, settings or secrets without the owner's explicit approval.

If a fact cannot be verified, write `UNVERIFIED`. If state conflicts, stop and report.
