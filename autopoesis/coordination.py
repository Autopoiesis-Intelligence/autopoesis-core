"""Task claims in the coordination issue, derived from machine-readable claim comments.

The rules live in docs/coordination/PROTOCOL.md ("Claims"). A claim comment counts only if:

- the comment body starts with the claim block (``Agent:``, ``Task:``, ``Claim:``);
- the task ID prefix belongs to the agent named in ``Agent:``;
- GitHub reports that the app of that agent posted it (``performed_via_github_app``);
  the text ``Agent:`` line alone is never proof, because all agents share one account.

The state is recomputed from scratch each time, so a repeated or late event
yields the same claims. Nothing here talks to GitHub: callers pass the comments.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

# Agent name -> (GitHub App id, slug) that GitHub records on its comments, and its task ID prefix.
AGENT_APPS = {"Claude": (1236702, "claude"), "GPT": (1144995, "chatgpt-codex-connector")}
TASK_PREFIXES = {"Claude": "CL", "GPT": "GP", "Copilot": "CP", "Manus": "MN"}
CLAIM_EXPIRY = timedelta(hours=24)
STATUSES = frozenset({"OPEN", "RELEASED", "STALE"})

_AGENT_LINE = re.compile(r"^Agent: (\S+)$")
_TASK_LINE = re.compile(r"^Task: ([A-Z]{2}-[A-Za-z0-9-]+)$")
_CLAIM_LINE = re.compile(r"^Claim: (\S+)$")


def parse_claim(body: Any) -> dict[str, str] | None:
    """Return the claim block at the top of a comment, or None if there is none."""
    if not isinstance(body, str):
        return None
    lines = [line.strip() for line in body.strip().splitlines()]
    if len(lines) < 3:
        return None
    agent, task, claim = (_AGENT_LINE.match(lines[0]), _TASK_LINE.match(lines[1]), _CLAIM_LINE.match(lines[2]))
    if not (agent and task and claim) or claim.group(1) not in STATUSES:
        return None
    return {"agent": agent.group(1), "task": task.group(1), "status": claim.group(1)}


def _authentic(comment: dict[str, Any], agent: str) -> bool:
    app = comment.get("performed_via_github_app")
    expected = AGENT_APPS.get(agent)
    return (
        expected is not None
        and isinstance(app, dict)
        and type(app.get("id")) is int
        and (app["id"], app.get("slug")) == expected
    )


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"timestamp must be an ISO 8601 string, got {value!r}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp has no time zone: {value!r}")
    return parsed


def coordination_state(
    comments: list[dict[str, Any]],
    *,
    now: datetime,
    activity: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Compute every task claim and the reason each claim comment was or was not applied.

    ``activity`` maps a task ID to extra activity timestamps (commits on its branch,
    updates of its PR). Any of them, or a newer OPEN comment by the owner, keeps the claim alive.
    """
    if now.tzinfo is None:
        raise ValueError("now must be time-zone aware")
    extra = {task: sorted(_parse_time(t) for t in times) for task, times in (activity or {}).items()}
    claims: dict[str, dict[str, Any]] = {}
    decisions = []

    def last_activity(task: str, before: datetime) -> datetime:
        opened = claims[task]["opened_at"]
        times = [claims[task]["last_activity"]] + [t for t in extra.get(task, []) if opened <= t <= before]
        return max(times)

    candidates = []
    for comment in comments:
        parsed = parse_claim(comment.get("body")) if isinstance(comment, dict) else None
        if parsed is None:
            continue
        try:
            at = _parse_time(comment.get("created_at"))
        except ValueError:
            decisions.append({"comment_id": comment.get("id"), "task": parsed["task"], "decision": "BAD_TIMESTAMP"})
            continue
        candidates.append((at, comment.get("id") or 0, parsed, comment))

    for at, _, parsed, comment in sorted(candidates, key=lambda item: item[:2]):
        agent, task, status = parsed["agent"], parsed["task"], parsed["status"]
        current = claims.get(task)

        # OPEN and RELEASED use the agent's own task IDs; STALE names another agent's task.
        if status != "STALE" and not task.startswith(TASK_PREFIXES.get(agent, "?") + "-"):
            decision = "WRONG_PREFIX"
        elif not _authentic(comment, agent):
            decision = "UNAUTHORIZED"
        elif status == "OPEN":
            other = [t for t, c in claims.items() if t != task and c["agent"] == agent and c["status"] == "OPEN"]
            if current is not None and current["agent"] != agent and current["status"] == "OPEN":
                decision = "CONFLICT"
            elif other:
                decision = "SECOND_CLAIM"
            elif current is not None and current["status"] == "OPEN":
                current["last_activity"] = at
                decision = "REFRESHED"
            elif current is not None:
                decision = "CLOSED_TASK"  # task IDs are single-use; come back under a new ID
            else:
                claims[task] = {"agent": agent, "status": "OPEN", "opened_at": at, "last_activity": at,
                                "comment_id": comment.get("id")}
                decision = "OPENED"
        elif current is None or current["status"] != "OPEN":
            decision = "NO_OPEN_CLAIM"
        elif status == "RELEASED":  # the prefix check above already limits this to the owner
            current.update(status="RELEASED", closed_at=at)
            decision = "RELEASED"
        elif current["agent"] == agent:
            decision = "OWN_CLAIM"  # the owner releases its claim; only another agent marks it stale
        elif at - last_activity(task, at) <= CLAIM_EXPIRY:
            decision = "NOT_EXPIRED"
        else:
            current.update(status="STALE", closed_at=at, marked_by=agent)
            decision = "MARKED_STALE"
        decisions.append({"comment_id": comment.get("id"), "task": task, "decision": decision})

    result = {}
    for task, claim in claims.items():
        seen = last_activity(task, now)
        result[task] = {
            "agent": claim["agent"],
            "status": claim["status"],
            "last_activity": seen.isoformat(),
            "expired": claim["status"] == "OPEN" and now - seen > CLAIM_EXPIRY,
            "comment_id": claim["comment_id"],
        }
    return {"claims": result, "decisions": decisions}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute task claims from coordination issue comments.")
    parser.add_argument("input", help="JSON file: comments (GitHub issue comments), optional activity, optional now")
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as handle:
        facts = json.load(handle)
    now = _parse_time(facts["now"]) if "now" in facts else datetime.now(timezone.utc)
    state = coordination_state(facts["comments"], now=now, activity=facts.get("activity"))
    json.dump(state, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
