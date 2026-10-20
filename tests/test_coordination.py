# Agent: Claude
"""Claim rules from docs/coordination/PROTOCOL.md: identity, conflicts, expiry, takeover."""

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from autopoesis.coordination import coordination_state, parse_claim

CLAUDE = {"id": 1236702, "slug": "claude", "name": "Claude"}
GPT = {"id": 1144995, "slug": "chatgpt-codex-connector", "name": "ChatGPT Codex Connector"}
START = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def at(hours):
    return (START + timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def claim(comment_id, agent, task, status, hours, app=None):
    app = app if app is not None else {"Claude": CLAUDE, "GPT": GPT}.get(agent)
    body = f"Agent: {agent}\nTask: {task}\nClaim: {status}\n\nDetails follow."
    return {"id": comment_id, "body": body, "performed_via_github_app": app, "created_at": at(hours)}


def state(comments, now_hours=1, activity=None):
    return coordination_state(comments, now=START + timedelta(hours=now_hours), activity=activity)


def decisions(result):
    return [d["decision"] for d in result["decisions"]]


class ClaimFormatTests(unittest.TestCase):
    def test_block_must_open_the_comment(self):
        self.assertEqual(parse_claim("Agent: Claude\nTask: CL-009\nClaim: OPEN"),
                         {"agent": "Claude", "task": "CL-009", "status": "OPEN"})
        self.assertIsNone(parse_claim("Note\nAgent: Claude\nTask: CL-009\nClaim: OPEN"))
        self.assertIsNone(parse_claim("Agent: Claude\nTask: CL-009\nClaim: DONE"))
        self.assertIsNone(parse_claim("Agent: Claude · CL-004 · claim · 2026-10-20 00:50 UTC"))
        self.assertIsNone(parse_claim(None))

    def test_old_free_text_comments_are_ignored(self):
        old = {"id": 1, "body": "Agent: Claude · CL-004 · claim · 2026-10-20", "performed_via_github_app": CLAUDE,
               "created_at": at(0)}
        self.assertEqual(state([old]), {"claims": {}, "decisions": []})


class IdentityTests(unittest.TestCase):
    def test_agent_line_must_match_the_posting_app(self):
        spoofed = claim(1, "GPT", "GP-001", "OPEN", 0, app=CLAUDE)
        no_app = claim(2, "Claude", "CL-001", "OPEN", 0, app={})
        result = state([spoofed, no_app])
        self.assertEqual(decisions(result), ["UNAUTHORIZED", "UNAUTHORIZED"])
        self.assertEqual(result["claims"], {})

    def test_task_prefix_must_belong_to_the_agent(self):
        result = state([claim(1, "Claude", "GP-001", "OPEN", 0)])
        self.assertEqual(decisions(result), ["WRONG_PREFIX"])

    def test_agents_without_a_known_app_cannot_claim_yet(self):
        result = state([claim(1, "Copilot", "CP-001", "OPEN", 0, app=GPT)])
        self.assertEqual(decisions(result), ["UNAUTHORIZED"])


class LifecycleTests(unittest.TestCase):
    def test_open_then_release(self):
        result = state([claim(1, "Claude", "CL-009", "OPEN", 0), claim(2, "Claude", "CL-009", "RELEASED", 1)])
        self.assertEqual(decisions(result), ["OPENED", "RELEASED"])
        self.assertEqual(result["claims"]["CL-009"]["status"], "RELEASED")

    def test_only_the_owner_releases(self):
        result = state([claim(1, "Claude", "CL-009", "OPEN", 0), claim(2, "GPT", "CL-009", "RELEASED", 1)])
        self.assertEqual(decisions(result), ["OPENED", "WRONG_PREFIX"])
        self.assertEqual(result["claims"]["CL-009"]["status"], "OPEN")

    def test_one_open_claim_per_agent(self):
        result = state([claim(1, "Claude", "CL-009", "OPEN", 0), claim(2, "Claude", "CL-010", "OPEN", 1)])
        self.assertEqual(decisions(result), ["OPENED", "SECOND_CLAIM"])
        self.assertNotIn("CL-010", result["claims"])

    def test_both_agents_can_hold_independent_claims(self):
        result = state([claim(1, "Claude", "CL-009", "OPEN", 0), claim(2, "GPT", "GP-020", "OPEN", 0.5)])
        self.assertEqual(decisions(result), ["OPENED", "OPENED"])

    def test_repeated_events_give_the_same_state(self):
        comments = [claim(1, "Claude", "CL-009", "OPEN", 0), claim(2, "GPT", "GP-020", "OPEN", 0.5)]
        self.assertEqual(state(comments), state(list(reversed(comments))))


class ExpiryTests(unittest.TestCase):
    def test_claim_expires_after_24_hours_without_activity(self):
        comments = [claim(1, "Claude", "CL-009", "OPEN", 0)]
        self.assertFalse(state(comments, now_hours=24)["claims"]["CL-009"]["expired"])
        self.assertTrue(state(comments, now_hours=24.1)["claims"]["CL-009"]["expired"])


class TakeoverTests(unittest.TestCase):
    """STALE is the one status another agent posts under the owner's task ID."""

    def mark(self, comment_id, agent, task, hours):
        return {"id": comment_id, "body": f"Agent: {agent}\nTask: {task}\nClaim: STALE",
                "performed_via_github_app": {"Claude": CLAUDE, "GPT": GPT}[agent], "created_at": at(hours)}

    def test_stale_after_expiry_closes_the_claim(self):
        result = state([claim(1, "Claude", "CL-009", "OPEN", 0), self.mark(2, "GPT", "CL-009", 25)], 26)
        self.assertEqual(decisions(result), ["OPENED", "MARKED_STALE"])
        self.assertEqual(result["claims"]["CL-009"]["status"], "STALE")

    def test_stale_before_expiry_does_not_take_over_running_work(self):
        result = state([claim(1, "Claude", "CL-009", "OPEN", 0), self.mark(2, "GPT", "CL-009", 23)], 26)
        self.assertEqual(decisions(result), ["OPENED", "NOT_EXPIRED"])
        self.assertEqual(result["claims"]["CL-009"]["status"], "OPEN")

    def test_branch_activity_keeps_the_claim_alive(self):
        comments = [claim(1, "Claude", "CL-009", "OPEN", 0), self.mark(2, "GPT", "CL-009", 30)]
        result = state(comments, 31, activity={"CL-009": [at(10)]})
        self.assertEqual(decisions(result), ["OPENED", "NOT_EXPIRED"])
        self.assertFalse(result["claims"]["CL-009"]["expired"])

    def test_owner_refresh_keeps_the_claim_alive(self):
        comments = [claim(1, "Claude", "CL-009", "OPEN", 0), claim(2, "Claude", "CL-009", "OPEN", 20),
                    self.mark(3, "GPT", "CL-009", 30)]
        self.assertEqual(decisions(state(comments, 31)), ["OPENED", "REFRESHED", "NOT_EXPIRED"])

    def test_owner_cannot_mark_its_own_claim_stale(self):
        comments = [claim(1, "Claude", "CL-009", "OPEN", 0), self.mark(2, "Claude", "CL-009", 30)]
        self.assertEqual(decisions(state(comments, 31)), ["OPENED", "OWN_CLAIM"])

    def test_stale_without_an_open_claim_does_nothing(self):
        self.assertEqual(decisions(state([self.mark(1, "GPT", "CL-404", 0)])), ["NO_OPEN_CLAIM"])

    def test_takeover_uses_a_new_task_of_the_new_agent(self):
        comments = [claim(1, "Claude", "CL-009", "OPEN", 0), self.mark(2, "GPT", "CL-009", 25),
                    claim(3, "GPT", "GP-031", "OPEN", 25.5)]
        result = state(comments, 26)
        self.assertEqual(decisions(result), ["OPENED", "MARKED_STALE", "OPENED"])
        self.assertEqual(result["claims"]["GP-031"]["agent"], "GPT")


class RobustnessTests(unittest.TestCase):
    def test_a_closed_task_id_cannot_be_reopened(self):
        mark = {"id": 2, "body": "Agent: GPT\nTask: CL-009\nClaim: STALE", "performed_via_github_app": GPT,
                "created_at": at(25)}
        result = state([claim(1, "Claude", "CL-009", "OPEN", 0), mark, claim(3, "Claude", "CL-009", "OPEN", 26)], 27)
        self.assertEqual(decisions(result), ["OPENED", "MARKED_STALE", "CLOSED_TASK"])
        self.assertEqual(result["claims"]["CL-009"]["status"], "STALE")

        released = state([claim(1, "Claude", "CL-009", "OPEN", 0), claim(2, "Claude", "CL-009", "RELEASED", 1),
                          claim(3, "Claude", "CL-009", "OPEN", 2)], 3)
        self.assertEqual(decisions(released), ["OPENED", "RELEASED", "CLOSED_TASK"])

    def test_malformed_comments_do_not_break_the_state(self):
        broken_claim = claim(3, "Claude", "CL-009", "OPEN", 0)
        broken_claim["created_at"] = "2026-10-20T12:00:00"
        comments = ["not a dict", {"id": None, "body": "chat", "created_at": None}, broken_claim,
                    claim(None, "GPT", "GP-040", "OPEN", 0), claim(5, "Claude", "CL-010", "OPEN", 0)]
        result = state(comments)
        self.assertEqual(sorted(decisions(result)), ["BAD_TIMESTAMP", "OPENED", "OPENED"])

    def test_activity_before_the_claim_does_not_count(self):
        mark = {"id": 2, "body": "Agent: GPT\nTask: CL-009\nClaim: STALE", "performed_via_github_app": GPT,
                "created_at": at(25)}
        result = state([claim(1, "Claude", "CL-009", "OPEN", 0), mark], 26, activity={"CL-009": [at(-1)]})
        self.assertEqual(decisions(result), ["OPENED", "MARKED_STALE"])

    def test_naive_now_fails_closed(self):
        with self.assertRaises(ValueError):
            coordination_state([], now=datetime(2026, 10, 20, 12, 0))


class CommandLineTests(unittest.TestCase):
    def test_command_line_prints_the_same_state(self):
        comments = [claim(1, "Claude", "CL-009", "OPEN", 0)]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facts.json"
            path.write_text(json.dumps({"comments": comments, "now": at(1)}), encoding="utf-8")
            out = subprocess.run([sys.executable, "-m", "autopoesis.coordination", str(path)],
                                 check=True, capture_output=True, text=True).stdout
        self.assertEqual(json.loads(out)["claims"]["CL-009"]["status"], "OPEN")


if __name__ == "__main__":
    unittest.main()
