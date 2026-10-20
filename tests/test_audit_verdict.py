# Agent: Claude
"""Audit state rules from AGENTS.md: stale SHA, wrong author, repeats, head changes, deadline."""

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from autopoesis.audit_verdict import apply_audit_result, evaluate_pr_audit, parse_verdict

HEAD_A = "a" * 40
HEAD_B = "b" * 40
PUSHED = "2026-10-20T12:00:00Z"
SOON = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
GPT = {"id": 1144995, "slug": "chatgpt-codex-connector", "name": "ChatGPT Codex Connector"}


def verdict_comment(comment_id, verdict="ACCEPTED", pr=29, sha=HEAD_A, app=GPT, created="2026-10-20T13:00:00Z"):
    body = f"Agent: GPT\nVerdict: {verdict}\npr: {pr}\nhead_sha: {sha}\n\nReasons follow."
    return {"id": comment_id, "body": body, "performed_via_github_app": app, "created_at": created}


def evaluate(comments, *, head=HEAD_A, labels=(), now=SOON, ci_passed=True):
    return evaluate_pr_audit(
        pr_number=29,
        head_sha=head,
        head_committed_at=PUSHED,
        labels=list(labels),
        comments=comments,
        ci_passed=ci_passed,
        now=now,
    )


class VerdictFormatTests(unittest.TestCase):
    def test_verdict_block_must_open_the_comment(self):
        self.assertEqual(
            parse_verdict(f"Verdict: REJECTED\npr: #29\nhead_sha: {HEAD_A}"),
            {"verdict": "REJECTED", "pr": 29, "head_sha": HEAD_A},
        )
        for body in (
            f"Looks good.\nVerdict: ACCEPTED\npr: 29\nhead_sha: {HEAD_A}",
            f"Verdict: ACCEPTED\nhead_sha: {HEAD_A}",
            f"Verdict: MAYBE\npr: 29\nhead_sha: {HEAD_A}",
            "Verdict: ACCEPTED\npr: 29\nhead_sha: abc123",
            None,
        ):
            with self.subTest(body=body):
                self.assertIsNone(parse_verdict(body))


    def test_free_text_audits_in_the_old_style_are_not_verdicts(self):
        legacy = (
            "Agent: GPT\n\nAUDIT RESULT: ACCEPTED\nPR #28, head d80b293de764ccd4945d3bd49e7c45ae3431b964.\n"
            "Verdict: ACCEPTED (tests are meaningful)"
        )
        result = evaluate([{"id": 6282214941, "body": legacy, "performed_via_github_app": GPT, "created_at": PUSHED}])

        self.assertIsNone(parse_verdict(legacy))
        self.assertEqual(result["state"], "PENDING_AUDIT")
        self.assertEqual(result["decisions"], [])


class AuditStateTests(unittest.TestCase):
    def test_no_verdict_means_pending_audit(self):
        result = evaluate([{"id": 1, "body": "Thanks!", "performed_via_github_app": GPT, "created_at": PUSHED}])

        self.assertEqual(result["state"], "PENDING_AUDIT")
        self.assertEqual(result["add_labels"], ["pending-audit"])
        self.assertEqual(result["decisions"], [])

    def test_valid_acceptance_makes_pr_ready_for_owner(self):
        result = evaluate([verdict_comment(10)], labels=["pending-audit", "agent:claude"])

        self.assertEqual(result["state"], "READY_FOR_OWNER")
        self.assertEqual(result["verdict_comment_id"], 10)
        self.assertEqual(result["add_labels"], ["ready-for-owner"])
        self.assertEqual(result["remove_labels"], ["pending-audit"])

    def test_acceptance_without_green_ci_is_not_ready_for_owner(self):
        result = evaluate([verdict_comment(10)], labels=["pending-audit"], ci_passed=False)

        self.assertEqual(result["state"], "ACCEPTED_CI_NOT_GREEN")
        self.assertEqual(result["add_labels"], [])
        self.assertEqual(result["remove_labels"], ["pending-audit"])

    def test_valid_rejection_blocks_review(self):
        result = evaluate([verdict_comment(10, verdict="REJECTED")])

        self.assertEqual(result["state"], "BLOCKED_REVIEW")
        self.assertEqual(result["add_labels"], ["blocked-review"])

    def test_stale_sha_verdict_does_not_count(self):
        result = evaluate([verdict_comment(10, sha=HEAD_B)])

        self.assertEqual(result["state"], "PENDING_AUDIT")
        self.assertEqual(result["decisions"], [{"comment_id": 10, "decision": "STALE_SHA"}])

    def test_verdict_for_another_pr_does_not_count(self):
        result = evaluate([verdict_comment(10, pr=28)])

        self.assertEqual(result["decisions"], [{"comment_id": 10, "decision": "WRONG_PR"}])
        self.assertEqual(result["state"], "PENDING_AUDIT")

    def test_wrong_author_is_rejected_even_with_a_matching_agent_line(self):
        cases = (
            ("Claude app", {"id": 1236702, "slug": "claude", "name": "Claude"}),
            ("right name, wrong app id", {"id": 999, "slug": "chatgpt-codex-connector", "name": "ChatGPT Codex Connector"}),
            ("right id, wrong slug", {"id": 1144995, "slug": "other", "name": "ChatGPT Codex Connector"}),
            ("name only", {"name": "ChatGPT Codex Connector"}),
            ("no app", None),
            ("malformed", "ChatGPT"),
        )
        for label, app in cases:
            with self.subTest(author=label):
                result = evaluate([verdict_comment(10, app=app)])
                self.assertEqual(result["state"], "PENDING_AUDIT")
                self.assertEqual(result["decisions"], [{"comment_id": 10, "decision": "UNAUTHORIZED"}])

    def test_repeated_event_produces_no_new_label_changes(self):
        comments = [verdict_comment(10)]
        first = evaluate(comments, labels=["pending-audit"])
        applied = ["ready-for-owner"]

        repeat = evaluate(comments + [comments[0]], labels=applied)

        self.assertEqual(first["state"], repeat["state"])
        self.assertEqual(repeat["add_labels"], [])
        self.assertEqual(repeat["remove_labels"], [])

    def test_new_head_after_audit_removes_ready_for_owner(self):
        accepted_on_a = [verdict_comment(10, sha=HEAD_A)]

        result = evaluate(accepted_on_a, head=HEAD_B, labels=["ready-for-owner"])

        self.assertEqual(result["state"], "PENDING_AUDIT")
        self.assertEqual(result["add_labels"], ["pending-audit"])
        self.assertEqual(result["remove_labels"], ["ready-for-owner"])
        self.assertEqual(result["decisions"], [{"comment_id": 10, "decision": "STALE_SHA"}])

    def test_newest_valid_verdict_on_current_head_wins(self):
        comments = [
            verdict_comment(11, verdict="ACCEPTED", created="2026-10-20T15:00:00Z"),
            verdict_comment(10, verdict="REJECTED", created="2026-10-20T13:00:00Z"),
        ]

        self.assertEqual(evaluate(comments)["state"], "READY_FOR_OWNER")

    def test_audit_overdue_after_seven_days_notifies_owner_once(self):
        late = datetime(2026, 10, 27, 12, 0, 1, tzinfo=timezone.utc)

        first = evaluate([], labels=["pending-audit"], now=late)
        again = evaluate([], labels=["pending-audit", "audit-overdue"], now=late + timedelta(days=1))

        self.assertEqual(first["state"], "AUDIT_OVERDUE")
        self.assertTrue(first["notify_owner"])
        self.assertEqual(first["add_labels"], ["audit-overdue"])
        self.assertFalse(again["notify_owner"])
        self.assertEqual(again["add_labels"], [])
        self.assertEqual(again["remove_labels"], [])

    def test_exactly_seven_days_is_not_yet_overdue(self):
        at_deadline = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)

        self.assertEqual(evaluate([], now=at_deadline)["state"], "PENDING_AUDIT")

    def test_valid_verdict_after_deadline_clears_overdue(self):
        late = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)

        result = evaluate(
            [verdict_comment(10, created="2026-10-28T11:00:00Z")],
            labels=["pending-audit", "audit-overdue"],
            now=late,
        )

        self.assertEqual(result["state"], "READY_FOR_OWNER")
        self.assertEqual(result["remove_labels"], ["audit-overdue", "pending-audit"])

    def test_invalid_head_sha_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "40-character"):
            evaluate([], head="not-a-sha")

    def test_command_line_prints_the_same_decision(self):
        facts = {
            "pr": 29,
            "head_sha": HEAD_A,
            "head_committed_at": PUSHED,
            "labels": [],
            "comments": [verdict_comment(10)],
            "ci_passed": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "facts.json"
            path.write_text(json.dumps(facts), encoding="utf-8")
            output = subprocess.run(
                [sys.executable, "-m", "autopoesis.audit_verdict", str(path), "--now", "2026-10-21T12:00:00Z"],
                check=True, capture_output=True, text=True,
            ).stdout

        self.assertEqual(json.loads(output)["state"], "READY_FOR_OWNER")



class FakeGitHub:
    """Records label writes and owner messages; can fail on a chosen call."""

    def __init__(self, labels=(), fail_notify=False, fail_overdue_label=False):
        self.labels = set(labels)
        self.messages = []
        self.fail_notify = fail_notify
        self.fail_overdue_label = fail_overdue_label

    def notify(self, text):
        if self.fail_notify:
            raise OSError("message not delivered")
        self.messages.append(text)

    def add(self, labels):
        if self.fail_overdue_label and "audit-overdue" in labels:
            raise OSError("label write failed")
        self.labels |= set(labels)

    def remove(self, labels):
        self.labels -= set(labels)

    def check(self, now):
        result = evaluate([], labels=sorted(self.labels), now=now)
        return apply_audit_result(result, notify_owner=self.notify, add_labels=self.add, remove_labels=self.remove)


class ApplyAuditResultTests(unittest.TestCase):
    LATE = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)

    def test_overdue_sends_one_message_then_adds_the_label(self):
        github = FakeGitHub(labels=["pending-audit"])

        actions = github.check(self.LATE)
        repeat = github.check(self.LATE + timedelta(hours=4))

        self.assertEqual(actions, ["notify", "add:audit-overdue"])
        self.assertEqual(repeat, [])
        self.assertEqual(len(github.messages), 1)
        self.assertEqual(github.labels, {"pending-audit", "audit-overdue"})

    def test_failed_send_adds_no_label_and_the_next_check_retries(self):
        github = FakeGitHub(labels=["pending-audit"], fail_notify=True)

        with self.assertRaises(OSError):
            github.check(self.LATE)
        self.assertNotIn("audit-overdue", github.labels)

        github.fail_notify = False
        github.check(self.LATE + timedelta(hours=4))
        self.assertEqual(len(github.messages), 1)
        self.assertIn("audit-overdue", github.labels)

    def test_label_failure_after_send_duplicates_but_never_loses_the_message(self):
        github = FakeGitHub(labels=["pending-audit"], fail_overdue_label=True)

        with self.assertRaises(OSError):
            github.check(self.LATE)
        github.fail_overdue_label = False
        github.check(self.LATE + timedelta(hours=4))
        final = github.check(self.LATE + timedelta(hours=8))

        self.assertEqual(len(github.messages), 2)
        self.assertEqual(final, [])

    def test_label_changes_are_applied_without_a_message_when_not_overdue(self):
        github = FakeGitHub(labels=["ready-for-owner"])

        actions = github.check(SOON)

        self.assertEqual(actions, ["remove:ready-for-owner", "add:pending-audit"])
        self.assertEqual(github.messages, [])

if __name__ == "__main__":
    unittest.main()
