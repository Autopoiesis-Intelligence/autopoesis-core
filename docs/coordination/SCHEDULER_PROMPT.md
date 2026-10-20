# Scheduled run prompt (Claude)

The live prompt is stored in Claude's scheduled task "autopoiesis-core dev loop" (cron `47 */4 * * *`, every 4 hours). The scheduler allows at most hourly runs. This file is the reviewed reference for that prompt; when the two differ, update the scheduled task to match this file after the PR is merged.

On each run:

1. Make one cheap check first: the `main` SHA, open PRs with their head SHAs, and the newest comment in Issue #22. If nothing changed and nothing is due, post nothing and stop.
2. Compute the claims in #22 from a checkout of `main`, with exactly this command:

   ```bash
   gh api --paginate --slurp "repos/Autopoiesis-Intelligence/autopoiesis-core/issues/22/comments?per_page=100" | python -m autopoesis.coordination -
   ```

   It prints the claims as JSON. Do not start work that overlaps another agent's open claim. If the command fails, stop: claims are unknown, not empty.
3. Before editing, post a claim block (`Agent: Claude`, `Task: CL-…`, `Claim: OPEN`) with the starting SHA, branch, files in scope and acceptance criteria.
4. Work on a `claude/` branch and a PR. Re-check the branch head right before writing.
5. Record the exact head SHA and the CI run on that SHA. A queued run is not a pass.
6. Hand off in #22 with the report format from `AGENTS.md`, then post `Claim: RELEASED`.
7. Never merge, enable auto-merge, force-push, write to `main`, or change workflows, permissions, settings or secrets without the owner's explicit approval.

If a fact cannot be verified, write `UNVERIFIED`. If state conflicts, stop and report.
