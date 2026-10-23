"""Fail-closed selection of the previous scheduled-cycle run."""

from __future__ import annotations

from typing import Any


WORKFLOW_PATH = ".github/workflows/autopoiesis-cycle.yml"


def select_prior_successful_run(
    pages: Any, *, current_run_id: int, bootstrap: bool
) -> dict[str, Any] | None:
    """Select the newest successful main-branch cycle from all API pages.

    pages is the list produced by gh api --paginate --slurp. Refuse malformed
    or incomplete-looking input instead of treating it as empty history.
    """
    if not isinstance(pages, list) or not pages:
        raise ValueError("workflow runs history is incomplete or malformed")
    if any(not isinstance(page, dict) or not isinstance(page.get("workflow_runs"), list)
           for page in pages):
        raise ValueError("workflow runs page is malformed")

    runs = [run for page in pages for run in page["workflow_runs"]]
    prior = [
        run for run in runs
        if isinstance(run, dict)
        and run.get("id") != current_run_id
        and run.get("head_branch") == "main"
        and run.get("conclusion") == "success"
        and isinstance(run.get("path"), str)
        and run["path"].split("@", 1)[0] == WORKFLOW_PATH
    ]
    prior.sort(key=lambda run: (run.get("run_number", 0), run.get("id", 0)), reverse=True)

    if prior and bootstrap:
        raise ValueError("Refusing bootstrap: a prior successful cycle already exists")
    if not prior and not bootstrap:
        raise ValueError("No successful prior snapshot; dispatch once with bootstrap=true")
    return prior[0] if prior else None
