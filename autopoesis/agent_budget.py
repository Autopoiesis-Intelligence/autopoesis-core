"""Self-calibrating usage budget for an external code-writing agent (Copilot CLI).

The Copilot Free allowance of AI credits is not published as a number, so the
core does not assume one. It learns from its own runs:

- every run is charged the credits the CLI reported, or the whole per-run cap
  when no usage report can be read (fail closed);
- the average charge per task kind becomes the estimate for the next plan;
- an "allowance exhausted" error blocks runs until the monthly reset
  (00:00 UTC on the first day of the month) and records the spent amount as
  the observed allowance. That figure misses the owner's own spending, so
  each new month raises it by a quarter until the next exhaustion corrects it;
- a rate-limit error blocks runs with exponential backoff.

Spending is paced evenly over the days left in the month, and a reserve is
kept for the owner's own use once the allowance is known. Nothing here calls
the agent: callers ask ``plan`` before a run and report it with ``record``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms
    fcntl = None

from .core import EvolutionError, canonical_json


LEDGER_VERSION = 1
MAX_RECORDED_RUNS = 200
_EXHAUSTED = re.compile(
    r"\b(?:quota|allowance|credits?)\b[^\n]{0,40}?\b(?:exhausted|exceeded|reached|used up|depleted)\b"
    r"|out of (?:ai )?credits|payment required|\b(?:http|status)[ /:]*402\b",
    re.IGNORECASE,
)
_RATE_LIMITED = re.compile(r"rate.?limit|too many requests|\b429\b", re.IGNORECASE)
OBSERVED_ALLOWANCE_MONTHLY_GROWTH = 1.25
BLOCK_REASONS = {"ALLOWANCE_EXHAUSTED", "RATE_LIMITED"}
RUN_OUTCOMES = {"OK", "FAILED"} | BLOCK_REASONS
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


@dataclass(frozen=True)
class BudgetPolicy:
    max_credits_per_run: float = 10.0
    owner_reserve_fraction: float = 0.2
    probe_runs_per_day: int = 2
    configured_allowance: float | None = None
    max_backoff_hours: int = 24

    def __post_init__(self) -> None:
        if not _is_amount(self.max_credits_per_run) or self.max_credits_per_run < 1:
            raise EvolutionError("max_credits_per_run must be a finite number of at least 1")
        if not _is_amount(self.owner_reserve_fraction) or self.owner_reserve_fraction >= 1:
            raise EvolutionError("owner_reserve_fraction must be in [0, 1)")
        if not _is_count(self.probe_runs_per_day):
            raise EvolutionError("probe_runs_per_day must be a non-negative integer")
        if self.configured_allowance is not None and not _is_amount(self.configured_allowance):
            raise EvolutionError("configured_allowance must be a non-negative number")
        if not _is_count(self.max_backoff_hours) or self.max_backoff_hours < 1:
            raise EvolutionError("max_backoff_hours must be a positive integer")


def month_period(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m")


def next_reset(now: datetime) -> datetime:
    current = now.astimezone(timezone.utc)
    year, month = (current.year + 1, 1) if current.month == 12 else (current.year, current.month + 1)
    return datetime(year, month, 1, tzinfo=timezone.utc)


def days_left_in_month(now: datetime) -> int:
    current = now.astimezone(timezone.utc)
    start_of_today = datetime(current.year, current.month, current.day, tzinfo=timezone.utc)
    return (next_reset(now) - start_of_today).days


def new_ledger(now: datetime, policy: BudgetPolicy) -> dict[str, Any]:
    allowance = policy.configured_allowance
    return {
        "version": LEDGER_VERSION,
        "period": month_period(now),
        "allowance": allowance,
        "allowance_source": "configured" if allowance is not None else "unknown",
        "used": 0.0,
        "blocked_until": None,
        "block_reason": None,
        "rate_limit_strikes": 0,
        "cost_by_kind": {},
        "runs": [],
    }


def validate_ledger(ledger: Any) -> dict[str, Any]:
    if not isinstance(ledger, dict) or ledger.get("version") != LEDGER_VERSION:
        raise EvolutionError("Unsupported agent budget ledger format")
    if not isinstance(ledger.get("period"), str) or not re.fullmatch(r"\d{4}-\d{2}", ledger["period"]):
        raise EvolutionError("Budget ledger period must be YYYY-MM")
    if not _is_amount(ledger.get("used")):
        raise EvolutionError("Budget ledger used must be a non-negative number")
    if ledger.get("allowance") is not None and not _is_amount(ledger["allowance"]):
        raise EvolutionError("Budget ledger allowance must be a non-negative number or null")
    if ledger.get("allowance_source") not in {"configured", "observed", "unknown"}:
        raise EvolutionError("Budget ledger allowance_source is invalid")
    if not isinstance(ledger.get("cost_by_kind"), dict) or not isinstance(ledger.get("runs"), list):
        raise EvolutionError("Budget ledger needs cost_by_kind and runs")
    if not isinstance(ledger.get("rate_limit_strikes"), int) or ledger["rate_limit_strikes"] < 0:
        raise EvolutionError("Budget ledger rate_limit_strikes must be a non-negative integer")
    if ledger.get("blocked_until") is not None:
        _parse_time(ledger["blocked_until"])
        if ledger.get("block_reason") not in BLOCK_REASONS:
            raise EvolutionError("Budget ledger block needs a known block_reason")
    elif "block_reason" not in ledger or ledger["block_reason"] is not None:
        raise EvolutionError("Budget ledger block_reason must be null when not blocked")
    for run in ledger["runs"]:
        if (
            not isinstance(run, dict)
            or not isinstance(run.get("kind"), str)
            or not isinstance(run.get("task_id"), str)
            or not _is_amount(run.get("cap"))
            or not _is_amount(run.get("charged"))
            or (run.get("reported") is not None and not _is_amount(run["reported"]))
            or not isinstance(run.get("exit_code"), int)
            or run.get("outcome") not in RUN_OUTCOMES
        ):
            raise EvolutionError("Budget ledger contains an invalid run entry")
        if month_period(_parse_time(run.get("at"))) != ledger["period"]:
            raise EvolutionError("Budget ledger run is outside the ledger period")
    for kind, stats in ledger["cost_by_kind"].items():
        if (
            not isinstance(stats, dict)
            or not isinstance(stats.get("runs"), int)
            or stats["runs"] < 1
            or not _is_amount(stats.get("total"))
        ):
            raise EvolutionError(f"Budget ledger cost stats are invalid for {kind!r}")
    return ledger


def load_ledger(path: Path, now: datetime, policy: BudgetPolicy) -> dict[str, Any]:
    """A missing ledger starts fresh; an unreadable one stops the caller."""
    if not path.exists():
        return new_ledger(now, policy)
    try:
        ledger = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvolutionError(f"Cannot read agent budget ledger: {exc}") from exc
    return validate_ledger(ledger)


def save_ledger(path: Path, ledger: dict[str, Any]) -> None:
    validate_ledger(ledger)
    payload = json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


@contextmanager
def ledger_lock(path: Path) -> Iterator[None]:
    """Hold an exclusive, non-blocking lock beside the ledger; a second writer is rejected."""
    if fcntl is None:
        raise EvolutionError("Budget ledger locking is not supported on this platform")
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise EvolutionError(f"Budget ledger {path.as_posix()} is locked by another run") from exc
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def roll_period(ledger: dict[str, Any], now: datetime, policy: BudgetPolicy) -> dict[str, Any]:
    """Apply the owner's allowance, and on a new month reset spending.

    An allowance set by the owner always wins over a learned one. Learned
    allowance and per-kind costs carry over into the new month.
    """
    updated = json.loads(canonical_json(ledger))
    if policy.configured_allowance is not None:
        updated["allowance"] = float(policy.configured_allowance)
        updated["allowance_source"] = "configured"
    current_period = month_period(now)
    if updated["period"] > current_period:
        # A clock that went backwards must not erase this month's spending.
        raise EvolutionError(f"Budget ledger period {updated['period']} is after {current_period}")
    if updated["period"] == current_period:
        return updated
    updated["period"] = current_period
    updated["used"] = 0.0
    updated["runs"] = []
    if updated["allowance_source"] == "observed":
        updated["allowance"] = round(updated["allowance"] * OBSERVED_ALLOWANCE_MONTHLY_GROWTH, 6)
    if updated["block_reason"] == "ALLOWANCE_EXHAUSTED":
        updated["blocked_until"] = None
        updated["block_reason"] = None
    return updated


def estimate_cost(ledger: dict[str, Any], kind: str) -> float | None:
    """Average charged credits for this kind, or None before its first run."""
    stats = ledger["cost_by_kind"].get(kind)
    if not stats:
        return None
    return stats["total"] / stats["runs"]


def plan(ledger: dict[str, Any], now: datetime, kind: str, policy: BudgetPolicy) -> dict[str, Any]:
    """Decide whether one run of ``kind`` fits the budget, and with what credit cap."""
    _require_name(kind, "task kind")
    current = roll_period(ledger, now, policy)
    estimate = estimate_cost(current, kind)
    # A kind with no history may run with whatever is left today; its cap bounds the cost.
    needed = 1.0 if estimate is None else max(estimate, 1.0)
    decision: dict[str, Any] = {
        "kind": kind,
        "period": current["period"],
        "estimate": None if estimate is None else round(estimate, 4),
        "used": current["used"],
        "allowance": current["allowance"],
        "allowance_source": current["allowance_source"],
    }

    if current["blocked_until"] is not None and _parse_time(current["blocked_until"]) > now:
        return {**decision, "decision": "WAIT", "reason": current["block_reason"],
                "retry_after": current["blocked_until"]}

    today = now.astimezone(timezone.utc).date().isoformat()
    runs_today = [run for run in current["runs"] if run["at"][:10] == today]
    spent_today = sum(run["charged"] for run in runs_today)

    if current["allowance"] is None:
        if len(runs_today) >= policy.probe_runs_per_day:
            return {**decision, "decision": "WAIT", "reason": "PROBE_DAILY_RUNS_USED",
                    "retry_after": _start_of_next_day(now)}
        return {**decision, "decision": "RUN", "reason": "PROBING_UNKNOWN_ALLOWANCE",
                "max_ai_credits": _cap(policy.max_credits_per_run)}

    usable = current["allowance"] * (1 - policy.owner_reserve_fraction)
    spent_before_today = current["used"] - spent_today
    daily_budget = max(usable - spent_before_today, 0.0) / days_left_in_month(now)
    left_today = min(daily_budget - spent_today, usable - current["used"])
    decision["daily_budget"] = round(daily_budget, 4)
    if left_today < needed:
        reason = "MONTHLY_BUDGET_USED" if usable - current["used"] < needed else "DAILY_BUDGET_USED"
        retry_after = next_reset(now).isoformat() if reason == "MONTHLY_BUDGET_USED" else _start_of_next_day(now)
        return {**decision, "decision": "WAIT", "reason": reason, "retry_after": retry_after}
    return {**decision, "decision": "RUN", "reason": "WITHIN_BUDGET",
            "max_ai_credits": _cap(min(policy.max_credits_per_run, left_today))}


def record_run(
    ledger: dict[str, Any],
    now: datetime,
    *,
    kind: str,
    task_id: str,
    cap: float,
    exit_code: int,
    usage: Any,
    stderr: str,
    policy: BudgetPolicy,
) -> dict[str, Any]:
    """Charge one finished run and learn from its outcome."""
    _require_name(kind, "task kind")
    _require_name(task_id, "task id")
    if not _is_amount(cap):
        raise EvolutionError("Run cap must be a non-negative number")
    updated = roll_period(ledger, now, policy)

    reported = reported_credits(usage)
    charged = reported if reported is not None else float(cap)
    updated["used"] = round(updated["used"] + charged, 6)
    if exit_code == 0 or reported is not None:
        stats = updated["cost_by_kind"].setdefault(kind, {"runs": 0, "total": 0.0})
        stats["runs"] += 1
        stats["total"] = round(stats["total"] + charged, 6)

    if exit_code == 0:
        outcome = "OK"
        updated["rate_limit_strikes"] = 0
        if updated["block_reason"] == "RATE_LIMITED":
            updated["blocked_until"] = None
            updated["block_reason"] = None
    elif _EXHAUSTED.search(stderr):
        outcome = "ALLOWANCE_EXHAUSTED"
        updated["blocked_until"] = next_reset(now).isoformat()
        updated["block_reason"] = outcome
        if policy.configured_allowance is None and updated["used"] >= 1:
            # Below one credit the owner must have spent the allowance; nothing is learned.
            updated["allowance"] = updated["used"]
            updated["allowance_source"] = "observed"
    elif _RATE_LIMITED.search(stderr):
        outcome = "RATE_LIMITED"
        updated["rate_limit_strikes"] += 1
        hours = min(2 ** (updated["rate_limit_strikes"] - 1), policy.max_backoff_hours)
        updated["blocked_until"] = (now + timedelta(hours=hours)).isoformat()
        updated["block_reason"] = outcome
    else:
        outcome = "FAILED"

    updated["runs"].append({
        "at": now.astimezone(timezone.utc).isoformat(),
        "kind": kind,
        "task_id": task_id,
        "cap": float(cap),
        "reported": reported,
        "charged": charged,
        "exit_code": exit_code,
        "outcome": outcome,
    })
    updated["runs"] = updated["runs"][-MAX_RECORDED_RUNS:]
    return validate_ledger(updated)


def reported_credits(usage: Any) -> float | None:
    """Return the one credit total in a usage report, or None if it is absent or ambiguous."""
    found: set[float] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                lowered = str(key).lower()
                if ("credit" in lowered or "premiumrequest" in lowered.replace("_", "")) and _is_amount(item):
                    found.add(float(item))
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(usage)
    return found.pop() if len(found) == 1 else None


def _is_amount(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _cap(value: float) -> int:
    return max(int(math.floor(value)), 1)


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise EvolutionError("Timestamp must be an ISO-8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise EvolutionError(f"Invalid timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise EvolutionError(f"Timestamp must include a timezone: {value!r}")
    return parsed


def _start_of_next_day(now: datetime) -> str:
    current = now.astimezone(timezone.utc)
    start = datetime(current.year, current.month, current.day, tzinfo=timezone.utc)
    return (start + timedelta(days=1)).isoformat()


def _require_name(value: Any, label: str) -> None:
    if not isinstance(value, str) or not _SAFE_NAME.fullmatch(value):
        raise EvolutionError(f"Invalid {label}: {value!r}")


def _read_optional_json(path: str | None) -> Any:
    if not path or not Path(path).is_file():
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["plan", "record"])
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--now", help="ISO-8601 time with timezone; defaults to the current UTC time")
    parser.add_argument("--allowance", type=float, help="known monthly AI credit allowance, if the owner set one")
    parser.add_argument("--max-credits-per-run", type=float, default=BudgetPolicy.max_credits_per_run)
    parser.add_argument("--task-id")
    parser.add_argument("--cap", type=float)
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--usage-file")
    parser.add_argument("--stderr-file")
    args = parser.parse_args(argv)

    now = _parse_time(args.now) if args.now else datetime.now(timezone.utc)
    policy = BudgetPolicy(
        max_credits_per_run=args.max_credits_per_run,
        configured_allowance=args.allowance,
    )
    if args.command == "record" and (args.task_id is None or args.cap is None or args.exit_code is None):
        parser.error("record needs --task-id, --cap and --exit-code")
    with ledger_lock(args.ledger):
        return _run_command(args, now, policy)


def _run_command(args: argparse.Namespace, now: datetime, policy: BudgetPolicy) -> int:
    ledger = load_ledger(args.ledger, now, policy)
    if args.command == "plan":
        result = plan(ledger, now, args.kind, policy)
        print(canonical_json(result))
        return 0 if result["decision"] == "RUN" else 3

    stderr = ""
    if args.stderr_file and Path(args.stderr_file).is_file():
        stderr = Path(args.stderr_file).read_text(encoding="utf-8", errors="replace")
    updated = record_run(
        ledger,
        now,
        kind=args.kind,
        task_id=args.task_id,
        cap=args.cap,
        exit_code=args.exit_code,
        usage=_read_optional_json(args.usage_file),
        stderr=stderr,
        policy=policy,
    )
    save_ledger(args.ledger, updated)
    print(canonical_json(updated["runs"][-1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
