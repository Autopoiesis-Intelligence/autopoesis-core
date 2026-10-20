import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from autopoesis.agent_budget import (
    BudgetPolicy,
    ledger_lock,
    load_ledger,
    new_ledger,
    plan,
    record_run,
    reported_credits,
    usage_readings,
    save_ledger,
)
from autopoesis.core import EvolutionError


ROOT = Path(__file__).resolve().parents[1]
OCT_10 = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)
# Tests of learning from reported spending assume the allowance unit has been resolved.
TRUSTED = "totalPremiumRequestCost"


def record(ledger, now, policy, *, kind="docs", cap=10, exit_code=0, usage=None, stderr="", task_id="t1"):
    return record_run(
        ledger, now, kind=kind, task_id=task_id, cap=cap, exit_code=exit_code,
        usage=usage, stderr=stderr, policy=policy,
    )


class UnknownAllowanceTests(unittest.TestCase):
    def test_probe_runs_are_limited_per_day(self):
        policy = BudgetPolicy(probe_runs_per_day=2)
        ledger = new_ledger(OCT_10, policy)
        self.assertEqual(plan(ledger, OCT_10, "docs", policy)["reason"], "PROBING_UNKNOWN_ALLOWANCE")
        ledger = record(ledger, OCT_10, policy, usage={"totalPremiumRequestCost": 3})
        ledger = record(ledger, OCT_10, policy, usage={"totalPremiumRequestCost": 3})
        decision = plan(ledger, OCT_10, "docs", policy)
        self.assertEqual(decision["decision"], "WAIT")
        self.assertEqual(decision["reason"], "PROBE_DAILY_RUNS_USED")
        self.assertEqual(plan(ledger, OCT_10 + timedelta(days=1), "docs", policy)["decision"], "RUN")

    def test_exhaustion_blocks_until_monthly_reset_and_learns_allowance(self):
        policy = BudgetPolicy(allowance_unit_field=TRUSTED)
        ledger = record(new_ledger(OCT_10, policy), OCT_10, policy, cap=60, usage={"totalPremiumRequestCost": 40})
        ledger = record(ledger, OCT_10, policy, cap=30, exit_code=1,
                        stderr="Error: monthly AI credits allowance exhausted for this plan")
        self.assertEqual(ledger["allowance_source"], "observed")
        self.assertEqual(ledger["allowance"], 70.0)
        decision = plan(ledger, OCT_10 + timedelta(days=5), "docs", policy)
        self.assertEqual(decision["decision"], "WAIT")
        self.assertEqual(decision["retry_after"], "2026-11-01T00:00:00+00:00")

        # After the reset the block is gone; the learned allowance grows by a quarter and paces spending.
        november = datetime(2026, 11, 1, 0, 30, tzinfo=timezone.utc)
        decision = plan(ledger, november, "docs", policy)
        self.assertEqual(decision["allowance"], 87.5)
        self.assertEqual(decision["used"], 0.0)
        self.assertEqual(decision["reason"], "DAILY_BUDGET_USED")

    def test_exhaustion_with_unresolved_unit_blocks_but_learns_nothing(self):
        policy = BudgetPolicy()
        ledger = record(new_ledger(OCT_10, policy), OCT_10, policy, cap=60,
                        usage={"totalPremiumRequestCost": 1, "totalNanoAiu": 100_000_000})
        ledger = record(ledger, OCT_10, policy, cap=30, exit_code=1, stderr="monthly credits exhausted")
        self.assertEqual(ledger["used"], 90.0)
        self.assertEqual(ledger["block_reason"], "ALLOWANCE_EXHAUSTED")
        self.assertIsNone(ledger["allowance"])
        self.assertEqual(ledger["allowance_source"], "unknown")
        november = datetime(2026, 11, 1, 0, 30, tzinfo=timezone.utc)
        self.assertEqual(plan(ledger, november, "docs", policy)["reason"], "PROBING_UNKNOWN_ALLOWANCE")

    def test_rate_limit_backs_off_exponentially_and_success_clears_it(self):
        policy = BudgetPolicy()
        ledger = new_ledger(OCT_10, policy)
        ledger = record(ledger, OCT_10, policy, exit_code=1, stderr="429 Too Many Requests")
        self.assertEqual(ledger["blocked_until"], (OCT_10 + timedelta(hours=1)).isoformat())
        later = OCT_10 + timedelta(hours=2)
        ledger = record(ledger, later, policy, exit_code=1, stderr="rate limit hit")
        self.assertEqual(ledger["blocked_until"], (later + timedelta(hours=2)).isoformat())
        self.assertEqual(plan(ledger, later + timedelta(hours=1), "docs", policy)["reason"], "RATE_LIMITED")
        ledger = record(ledger, later + timedelta(hours=3), policy)
        self.assertEqual(ledger["rate_limit_strikes"], 0)
        self.assertIsNone(ledger["blocked_until"])

    def test_unrelated_failure_does_not_block(self):
        policy = BudgetPolicy()
        for stderr in ("Error: quota of files in prompt is small", "FAILED test_x.py:402 assert"):
            ledger = record(new_ledger(OCT_10, policy), OCT_10, policy, exit_code=1, stderr=stderr)
            self.assertIsNone(ledger["blocked_until"], stderr)
            self.assertEqual(ledger["runs"][-1]["outcome"], "FAILED")
            self.assertEqual(ledger["allowance_source"], "unknown")

    def test_exhaustion_with_nothing_spent_learns_nothing(self):
        policy = BudgetPolicy(allowance_unit_field=TRUSTED)
        ledger = record(new_ledger(OCT_10, policy), OCT_10, policy, exit_code=1,
                        usage={"totalPremiumRequestCost": 0}, stderr="HTTP 402 Payment Required")
        self.assertEqual(ledger["block_reason"], "ALLOWANCE_EXHAUSTED")
        self.assertIsNone(ledger["allowance"])
        self.assertEqual(ledger["allowance_source"], "unknown")

    def test_clock_going_backwards_is_rejected(self):
        policy = BudgetPolicy()
        november = datetime(2026, 11, 2, tzinfo=timezone.utc)
        ledger = record(new_ledger(november, policy), november, policy, exit_code=1,
                        stderr="monthly credits exhausted")
        with self.assertRaises(EvolutionError):
            plan(ledger, OCT_10, "docs", policy)


class KnownAllowanceTests(unittest.TestCase):
    def test_spending_is_paced_over_remaining_days(self):
        policy = BudgetPolicy(configured_allowance=880, max_credits_per_run=60)
        ledger = new_ledger(OCT_10, policy)
        decision = plan(ledger, OCT_10, "docs", policy)
        # 22 days left including today; 880 credits -> 40 per day.
        self.assertEqual(decision["daily_budget"], 40.0)
        self.assertEqual(decision["max_ai_credits"], 40)

    def test_daily_budget_below_the_agent_minimum_waits(self):
        policy = BudgetPolicy(configured_allowance=176)
        decision = plan(new_ledger(OCT_10, policy), OCT_10, "docs", policy)
        self.assertEqual(decision["daily_budget"], 8.0)
        self.assertEqual(decision["decision"], "WAIT")
        self.assertEqual(decision["reason"], "DAILY_BUDGET_USED")

    def test_learned_cost_decides_whether_a_run_fits_today(self):
        policy = BudgetPolicy(configured_allowance=2200)
        ledger = record(new_ledger(OCT_10, policy), OCT_10, policy, cap=60, usage={"totalPremiumRequestCost": 60})
        decision = plan(ledger, OCT_10, "docs", policy)
        # 100 per day; 60 spent leaves 40, less than the learned cost of 60.
        self.assertEqual(decision["estimate"], 60.0)
        self.assertEqual(decision["decision"], "WAIT")
        self.assertEqual(decision["reason"], "DAILY_BUDGET_USED")
        self.assertEqual(plan(ledger, OCT_10 + timedelta(days=1), "docs", policy)["decision"], "RUN")

    def test_monthly_budget_stops_when_less_than_a_minimum_run_is_left(self):
        policy = BudgetPolicy(configured_allowance=80, allowance_unit_field=TRUSTED)
        last_day = datetime(2026, 10, 31, 8, 0, tzinfo=timezone.utc)
        ledger = record(new_ledger(last_day, policy), last_day, policy, usage={"totalPremiumRequestCost": 75})
        decision = plan(ledger, last_day, "docs", policy)
        self.assertEqual(decision["decision"], "WAIT")
        self.assertEqual(decision["reason"], "MONTHLY_BUDGET_USED")


class ChargingTests(unittest.TestCase):
    def test_missing_usage_report_charges_the_whole_cap(self):
        policy = BudgetPolicy()
        ledger = record(new_ledger(OCT_10, policy), OCT_10, policy, cap=7, usage=None)
        self.assertEqual(ledger["used"], 7.0)
        self.assertIsNone(ledger["runs"][-1]["reported"])

    def test_unresolved_unit_charges_the_whole_cap_and_keeps_raw_readings(self):
        policy = BudgetPolicy()
        usage = json.loads((ROOT / "tests" / "fixtures" / "copilot_usage_report.json").read_text(encoding="utf-8"))
        ledger = record(new_ledger(OCT_10, policy), OCT_10, policy, cap=60, usage=usage)
        self.assertEqual(ledger["used"], 60.0)
        run = ledger["runs"][-1]
        self.assertIsNone(run["reported"])
        self.assertEqual(run["usage"]["totalPremiumRequestCost"], 1.0)
        self.assertAlmostEqual(run["usage"]["totalNanoAiu"], 0.103832)

    def test_trusted_unit_field_is_charged_alone(self):
        readings = usage_readings({"totalPremiumRequestCost": 1, "totalNanoAiu": 3_000_000_000})
        self.assertEqual(reported_credits(readings, BudgetPolicy(allowance_unit_field="totalPremiumRequestCost")), 1.0)
        self.assertEqual(reported_credits(readings, BudgetPolicy(allowance_unit_field="totalNanoAiu")), 3.0)
        with self.assertRaises(EvolutionError):
            BudgetPolicy(allowance_unit_field="creditsAvailable")

    def test_limit_and_balance_fields_are_never_read_as_consumption(self):
        empty = {"totalPremiumRequestCost": None, "totalNanoAiu": None}
        for key in ("creditLimit", "creditsAvailable", "remainingCredits", "aiCredits", "premium_requests"):
            self.assertEqual(usage_readings({key: 5}), empty, key)
        nested = {"modelMetrics": {"m": {"requests": {"cost": 9}, "totalNanoAiu": 9_000_000_000}}}
        self.assertEqual(usage_readings(nested), empty)
        self.assertEqual(usage_readings({"totalPremiumRequestCost": 1, "creditLimit": 300})["totalPremiumRequestCost"], 1.0)
        for bad in (True, -1, "1"):
            self.assertEqual(usage_readings({"totalPremiumRequestCost": bad}), empty)
        self.assertEqual(usage_readings([{"totalPremiumRequestCost": 1}]), empty)

    def test_report_without_consumption_field_charges_the_whole_cap(self):
        policy = BudgetPolicy(allowance_unit_field=TRUSTED)
        ledger = record(new_ledger(OCT_10, policy), OCT_10, policy, cap=30,
                        usage={"creditsAvailable": 250, "remainingCredits": 250})
        self.assertEqual(ledger["used"], 30.0)
        self.assertIsNone(ledger["runs"][-1]["reported"])

    def test_month_rollover_resets_spending_but_keeps_learned_costs(self):
        policy = BudgetPolicy(allowance_unit_field=TRUSTED)
        ledger = record(new_ledger(OCT_10, policy), OCT_10, policy, usage={"totalPremiumRequestCost": 4})
        november = datetime(2026, 11, 2, tzinfo=timezone.utc)
        ledger = record(ledger, november, policy, usage={"totalPremiumRequestCost": 2})
        self.assertEqual(ledger["period"], "2026-11")
        self.assertEqual(ledger["used"], 2.0)
        self.assertEqual(ledger["cost_by_kind"]["docs"], {"runs": 2, "total": 6.0})

    def test_invalid_policy_is_rejected(self):
        for kwargs in ({"max_credits_per_run": 20}, {"max_credits_per_run": float("nan")},
                       {"min_credits_per_run": 0.5},
                       {"probe_runs_per_day": -1},
                       {"configured_allowance": -5}, {"max_backoff_hours": 0}):
            with self.assertRaises(EvolutionError, msg=kwargs):
                BudgetPolicy(**kwargs)

    def test_invalid_names_are_rejected(self):
        policy = BudgetPolicy()
        with self.assertRaises(EvolutionError):
            plan(new_ledger(OCT_10, policy), OCT_10, "../escape", policy)
        with self.assertRaises(EvolutionError):
            record(new_ledger(OCT_10, policy), OCT_10, policy, task_id="")


class LedgerFileTests(unittest.TestCase):
    def test_round_trip_and_corrupt_ledger_fails_closed(self):
        policy = BudgetPolicy()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "budget.json"
            self.assertEqual(load_ledger(path, OCT_10, policy)["used"], 0.0)
            ledger = record(new_ledger(OCT_10, policy), OCT_10, policy, usage={"totalPremiumRequestCost": 1})
            save_ledger(path, ledger)
            self.assertEqual(load_ledger(path, OCT_10, policy), ledger)
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["budget.json"])

            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(EvolutionError):
                load_ledger(path, OCT_10, policy)
            corrupt_runs = [{}, {**ledger["runs"][0], "charged": -1000}, {**ledger["runs"][0], "at": "2026-09-01T00:00:00+00:00"},
                            {**ledger["runs"][0], "usage": {"creditLimit": 300}}]
            for broken in ({**ledger, "used": -1}, {**ledger, "blocked_until": OCT_10.isoformat()},
                           *({**ledger, "runs": [run]} for run in corrupt_runs)):
                path.write_text(json.dumps(broken), encoding="utf-8")
                with self.assertRaises(EvolutionError):
                    load_ledger(path, OCT_10, policy)

    def test_second_writer_is_rejected_while_ledger_is_locked(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "budget.json"
            with ledger_lock(path):
                with self.assertRaises(EvolutionError):
                    with ledger_lock(path):
                        pass
            with ledger_lock(path):
                pass

    def test_cli_plan_and_record(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "budget.json"
            usage = Path(directory) / "usage.json"
            usage.write_text(json.dumps({"totalPremiumRequestCost": 2}), encoding="utf-8")
            base = [sys.executable, "-m", "autopoesis.agent_budget"]
            common = ["--ledger", str(ledger), "--kind", "docs", "--now", OCT_10.isoformat()]

            planned = subprocess.run(base + ["plan"] + common, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(planned.returncode, 0, planned.stderr)
            cap = json.loads(planned.stdout)["max_ai_credits"]

            recorded = subprocess.run(
                base + ["record"] + common + ["--task-id", "t1", "--cap", str(cap), "--exit-code", "0",
                                              "--usage-file", str(usage)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            run = json.loads(recorded.stdout)
            self.assertEqual(run["charged"], float(cap))
            self.assertEqual(run["usage"]["totalPremiumRequestCost"], 2.0)

            blocked = subprocess.run(base + ["plan"] + common + ["--allowance", "0"], cwd=ROOT,
                                     capture_output=True, text=True)
            self.assertEqual(blocked.returncode, 3, blocked.stderr)


if __name__ == "__main__":
    unittest.main()
