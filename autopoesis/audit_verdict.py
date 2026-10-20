"""Audit state of a pull request, derived from machine-readable verdict comments.

The rules live in AGENTS.md ("Review and audit"). A verdict counts only if:

- the comment body starts with the verdict block (an optional ``Agent:`` line first);
- it names this PR and the PR's current head SHA;
- GitHub reports that an authorized auditor app posted it
  (``performed_via_github_app``); the text ``Agent:`` line is never proof.

The state is recomputed from scratch each time, so a repeated or late event
yields the same labels and no new action. Nothing here talks to GitHub:
callers pass the PR facts and comments and apply the returned label changes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

AUTHORIZED_AUDITOR_APPS = frozenset({"ChatGPT Codex Connector"})
AUDIT_DEADLINE = timedelta(days=7)
VERDICTS = frozenset({"ACCEPTED", "REJECTED"})

LABEL_PENDING = "pending-audit"
LABEL_BLOCKED = "blocked-review"
LABEL_READY = "ready-for-owner"
LABEL_OVERDUE = "audit-overdue"
MANAGED_LABELS = frozenset({LABEL_PENDING, LABEL_BLOCKED, LABEL_READY, LABEL_OVERDUE})

_VERDICT_LINE = re.compile(r"^Verdict: (\S+)$")
_PR_LINE = re.compile(r"^pr: #?(\d+)$")
_SHA_LINE = re.compile(r"^head_sha: ([0-9a-f]{40})$")


def parse_verdict(body: Any) -> dict[str, Any] | None:
    """Return the verdict block at the top of a comment, or None if there is none."""
    if not isinstance(body, str):
        return None
    lines = [line.strip() for line in body.strip().splitlines()]
    if lines and lines[0].startswith("Agent:"):
        lines = lines[1:]
    if len(lines) < 3:
        return None
    verdict, pr, sha = (_VERDICT_LINE.match(lines[0]), _PR_LINE.match(lines[1]), _SHA_LINE.match(lines[2]))
    if not (verdict and pr and sha) or verdict.group(1) not in VERDICTS:
        return None
    return {"verdict": verdict.group(1), "pr": int(pr.group(1)), "head_sha": sha.group(1)}


def classify_comment(comment: dict[str, Any], *, pr_number: int, head_sha: str) -> str:
    """Return VALID or the reason a comment is not a usable verdict for this head."""
    parsed = parse_verdict(comment.get("body"))
    if parsed is None:
        return "NOT_A_VERDICT"
    app = comment.get("performed_via_github_app")
    if not isinstance(app, dict) or app.get("name") not in AUTHORIZED_AUDITOR_APPS:
        return "UNAUTHORIZED"
    if parsed["pr"] != pr_number:
        return "WRONG_PR"
    if parsed["head_sha"] != head_sha.lower():
        return "STALE_SHA"
    return "VALID"


def evaluate_pr_audit(
    *,
    pr_number: int,
    head_sha: str,
    head_committed_at: str,
    labels: list[str],
    comments: list[dict[str, Any]],
    ci_passed: bool,
    now: datetime,
) -> dict[str, Any]:
    """Compute the audit state of a PR and the label changes that reach it."""
    if not isinstance(head_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", head_sha):
        raise ValueError("head_sha must be a 40-character hexadecimal commit hash")
    head_time = _parse_time(head_committed_at)

    decisions = []
    valid = []
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        reason = classify_comment(comment, pr_number=pr_number, head_sha=head_sha)
        if reason == "NOT_A_VERDICT":
            continue
        decisions.append({"comment_id": comment.get("id"), "decision": reason})
        if reason == "VALID":
            valid.append((_parse_time(comment.get("created_at")), comment.get("id"), comment))

    if valid:
        # The newest valid verdict on the current head wins.
        _, comment_id, latest = max(valid, key=lambda item: (item[0], item[1] or 0))
        verdict = parse_verdict(latest["body"])["verdict"]
        if verdict == "REJECTED":
            state = "BLOCKED_REVIEW"
        else:
            state = "READY_FOR_OWNER" if ci_passed is True else "ACCEPTED_CI_NOT_GREEN"
        verdict_comment_id = comment_id
    else:
        state = "AUDIT_OVERDUE" if now - head_time > AUDIT_DEADLINE else "PENDING_AUDIT"
        verdict_comment_id = None

    wanted = {
        "READY_FOR_OWNER": {LABEL_READY},
        "BLOCKED_REVIEW": {LABEL_BLOCKED},
        "ACCEPTED_CI_NOT_GREEN": set(),
        "PENDING_AUDIT": {LABEL_PENDING},
        "AUDIT_OVERDUE": {LABEL_PENDING, LABEL_OVERDUE},
    }[state]
    current = set(labels) & MANAGED_LABELS
    return {
        "pr": pr_number,
        "head_sha": head_sha.lower(),
        "state": state,
        "verdict_comment_id": verdict_comment_id,
        "add_labels": sorted(wanted - current),
        "remove_labels": sorted(current - wanted),
        "notify_owner": state == "AUDIT_OVERDUE" and LABEL_OVERDUE not in current,
        "decisions": decisions,
    }


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamps must be ISO 8601 strings")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamps must carry a timezone")
    return parsed.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("input", help="JSON file: pr, head_sha, head_committed_at, labels, comments, ci_passed")
    parser.add_argument("--now", help="ISO 8601 time to evaluate at (default: current UTC time)")
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as handle:
        facts = json.load(handle)
    now = _parse_time(args.now) if args.now else datetime.now(timezone.utc)
    result = evaluate_pr_audit(
        pr_number=facts["pr"],
        head_sha=facts["head_sha"],
        head_committed_at=facts["head_committed_at"],
        labels=facts.get("labels", []),
        comments=facts.get("comments", []),
        ci_passed=facts.get("ci_passed") is True,
        now=now,
    )
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
