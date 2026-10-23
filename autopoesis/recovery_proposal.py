"""Deterministic, read-only recovery proposals from captured GitHub evidence.

This module does not download artifacts, read/write the task queue, restore state,
or authorize an apply operation. Callers supply a captured evidence document and
receive a proposal that must be reviewed and applied separately by an owner.
"""
from __future__ import annotations

import re
from typing import Any

WORKFLOW_PATH = ".github/workflows/autopoiesis-cycle.yml"
ARTIFACT_NAME = "autopoiesis-cycle-state"
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_QUEUE_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _blocked(reason: str, *, latest_run_id: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "BLOCKED",
        "mode": "PROPOSAL_ONLY",
        "reason": reason,
        "candidate": None,
        "actions_taken": [],
    }
    if latest_run_id is not None:
        result["latest_run_id"] = latest_run_id
    return result


def build_recovery_proposal(evidence: Any) -> dict[str, Any]:
    """Build a stable proposal from a captured evidence object; never mutate state.

    Expected shape:
      {"repository": "owner/repo", "runs": [run metadata, ...],
       "artifacts": [{"run_id": 123, "name": ..., "expired": false,
         "digest": "sha256:<64 hex>", "manifest": {...},
         "snapshot_sha256": "<64 hex>", "snapshot_size_bytes": 256}]}

    The snapshot hash is optional because artifact metadata alone cannot prove
    the queue bytes inside an archive. If absent, the result remains blocked
    rather than claiming that the archive contents were verified.
    """
    if not isinstance(evidence, dict):
        return _blocked("Evidence must be a JSON object")
    repository = evidence.get("repository")
    if not isinstance(repository, str) or not repository.strip():
        return _blocked("Evidence has no repository identity")
    if evidence.get("history_complete") is not True:
        return _blocked("Run history completeness is not proven; refusing to select a possibly stale snapshot")
    runs = evidence.get("runs")
    artifacts = evidence.get("artifacts")
    if not isinstance(runs, list) or not isinstance(artifacts, list):
        return _blocked("Evidence must contain run and artifact lists")

    relevant: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict):
            return _blocked("Run history contains a malformed record")
        if (run.get("head_branch") == "main"
                and isinstance(run.get("path"), str)
                and run["path"].split("@", 1)[0] == WORKFLOW_PATH):
            if type(run.get("run_number")) is not int or type(run.get("id")) is not int:
                return _blocked("Relevant run has invalid numeric identity")
            relevant.append(run)
    if not relevant:
        return _blocked("No evidence for a prior cycle run")

    relevant.sort(key=lambda run: (run["run_number"], run["id"]), reverse=True)
    latest = relevant[0]
    run_id = latest["id"]
    if latest.get("conclusion") != "success":
        return _blocked(
            "Newest relevant cycle is not successful; refusing rollback or bootstrap",
            latest_run_id=run_id,
        )
    if type(latest.get("run_attempt")) is not int or latest["run_attempt"] != 1:
        return _blocked("Newest run attempt is missing, invalid, or rerun; refusing ambiguous state", latest_run_id=run_id)
    head_sha = latest.get("head_sha")
    if not isinstance(head_sha, str) or not _SHA1.fullmatch(head_sha):
        return _blocked("Newest run has no valid lowercase head SHA", latest_run_id=run_id)
    if latest.get("event") not in {"schedule", "workflow_dispatch"}:
        return _blocked("Newest run has an unexpected trigger event", latest_run_id=run_id)
    run_repository = latest.get("repository")
    if isinstance(run_repository, dict):
        run_repository = run_repository.get("full_name")
    if run_repository != repository:
        return _blocked("Newest run repository does not match evidence repository", latest_run_id=run_id)

    matching = [
        artifact for artifact in artifacts
        if isinstance(artifact, dict)
        and str(artifact.get("run_id", "")) == str(run_id)
        and artifact.get("name") == ARTIFACT_NAME
    ]
    if not matching:
        return _blocked("Newest successful run has no state artifact", latest_run_id=run_id)
    if len(matching) != 1:
        return _blocked("Conflicting or duplicate state artifacts for newest run", latest_run_id=run_id)
    artifact = matching[0]
    if artifact.get("expired") is not False:
        return _blocked("State artifact is expired or expiry is unknown", latest_run_id=run_id)
    digest = artifact.get("digest")
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        return _blocked("Artifact archive digest is missing or malformed", latest_run_id=run_id)

    manifest = artifact.get("manifest")
    if not isinstance(manifest, dict):
        return _blocked("Snapshot manifest evidence is missing or malformed", latest_run_id=run_id)
    if str(manifest.get("source_run_id", "")) != str(run_id):
        return _blocked("Manifest run ID does not match source run", latest_run_id=run_id)
    if manifest.get("source_head_sha") != head_sha:
        return _blocked("Manifest head SHA does not match source run", latest_run_id=run_id)
    if manifest.get("source_repository") != repository:
        return _blocked("Manifest repository does not match source repository", latest_run_id=run_id)
    queue_digest = manifest.get("task_queue_sha256")
    if not isinstance(queue_digest, str) or not _QUEUE_SHA256.fullmatch(queue_digest):
        return _blocked("Manifest queue digest is missing or malformed", latest_run_id=run_id)
    size = manifest.get("task_queue_size_bytes")
    if type(size) is not int or size < 0:
        return _blocked("Manifest queue size is missing or malformed", latest_run_id=run_id)
    observed = artifact.get("snapshot_sha256")
    if not isinstance(observed, str) or not _QUEUE_SHA256.fullmatch(observed):
        return _blocked("Queue bytes have not been independently hashed", latest_run_id=run_id)
    if observed != queue_digest:
        return _blocked("Observed queue digest conflicts with manifest", latest_run_id=run_id)
    observed_size = artifact.get("snapshot_size_bytes")
    if type(observed_size) is not int or observed_size < 0:
        return _blocked("Queue bytes have not been independently sized", latest_run_id=run_id)
    if observed_size != size:
        return _blocked("Observed queue size conflicts with manifest", latest_run_id=run_id)

    return {
        "status": "PROPOSAL_READY",
        "mode": "PROPOSAL_ONLY",
        "reason": "Evidence is internally consistent; owner review is still required",
        "latest_run_id": run_id,
        "candidate": {
            "repository": repository,
            "source_run_id": run_id,
            "source_head_sha": head_sha,
            "artifact_name": ARTIFACT_NAME,
            "artifact_archive_digest": digest,
            "task_queue_sha256": queue_digest,
            "task_queue_size_bytes": size,
        },
        "actions_taken": [],
        "requires_owner_approval": True,
        "applied": False,
    }
