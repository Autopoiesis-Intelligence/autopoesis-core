"""Tests for read-only, proposal-only recovery inspection."""
import unittest

from autopoesis.recovery_proposal import build_recovery_proposal

REPO = "Autopoiesis-Intelligence/autopoiesis-core"
SHA = "a" * 40
QUEUE_SHA = "b" * 64
ARCHIVE_DIGEST = "sha256:" + "c" * 64


def valid_evidence():
    return {
        "repository": REPO,
        "history_complete": True,
        "runs": [{
            "id": 123, "run_number": 12, "run_attempt": 1,
            "head_branch": "main",
            "path": ".github/workflows/autopoiesis-cycle.yml@refs/heads/main",
            "conclusion": "success", "event": "schedule",
            "head_sha": SHA, "repository": REPO,
        }],
        "artifacts": [{
            "run_id": 123, "name": "autopoiesis-cycle-state",
            "expired": False, "digest": ARCHIVE_DIGEST,
            "manifest": {
                "source_run_id": 123, "source_head_sha": SHA,
                "source_repository": REPO, "task_queue_sha256": QUEUE_SHA,
                "task_queue_size_bytes": 256,
            },
            "snapshot_sha256": QUEUE_SHA,
        }],
    }


class RecoveryProposalTests(unittest.TestCase):
    def test_consistent_evidence_yields_proposal_only_not_apply(self):
        result = build_recovery_proposal(valid_evidence())
        self.assertEqual(result["status"], "PROPOSAL_READY")
        self.assertEqual(result["mode"], "PROPOSAL_ONLY")
        self.assertTrue(result["requires_owner_approval"])
        self.assertFalse(result["applied"])
        self.assertEqual(result["actions_taken"], [])

    def test_incomplete_history_blocks_even_with_successful_snapshot(self):
        evidence = valid_evidence()
        evidence["history_complete"] = False
        result = build_recovery_proposal(evidence)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("history completeness", result["reason"])

    def test_no_evidence_blocks(self):
        result = build_recovery_proposal({"repository": REPO, "history_complete": True, "runs": [], "artifacts": []})
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("No evidence", result["reason"])

    def test_failed_newest_run_blocks_rollback_to_older_success(self):
        evidence = valid_evidence()
        evidence["runs"].append({
            **evidence["runs"][0], "id": 124, "run_number": 13,
            "conclusion": "failure", "head_sha": "d" * 40,
        })
        result = build_recovery_proposal(evidence)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["latest_run_id"], 124)
        self.assertIn("refusing rollback", result["reason"])

    def test_missing_artifact_blocks(self):
        evidence = valid_evidence()
        evidence["artifacts"] = []
        self.assertIn("no state artifact", build_recovery_proposal(evidence)["reason"])

    def test_expired_or_unknown_artifact_blocks(self):
        for expired in (True, None):
            with self.subTest(expired=expired):
                evidence = valid_evidence()
                evidence["artifacts"][0]["expired"] = expired
                self.assertIn("expired", build_recovery_proposal(evidence)["reason"])

    def test_duplicate_or_conflicting_artifacts_block(self):
        evidence = valid_evidence()
        evidence["artifacts"].append(dict(evidence["artifacts"][0], digest="sha256:" + "e" * 64))
        self.assertIn("Conflicting", build_recovery_proposal(evidence)["reason"])

    def test_malformed_archive_digest_blocks(self):
        evidence = valid_evidence()
        evidence["artifacts"][0]["digest"] = "bad"
        self.assertIn("archive digest", build_recovery_proposal(evidence)["reason"])

    def test_malformed_manifest_digest_blocks(self):
        evidence = valid_evidence()
        evidence["artifacts"][0]["manifest"]["task_queue_sha256"] = "bad"
        self.assertIn("queue digest", build_recovery_proposal(evidence)["reason"])

    def test_conflicting_observed_queue_digest_blocks(self):
        evidence = valid_evidence()
        evidence["artifacts"][0]["snapshot_sha256"] = "f" * 64
        self.assertIn("conflicts", build_recovery_proposal(evidence)["reason"])

    def test_malformed_manifest_or_provenance_blocks(self):
        for field, value in (("source_run_id", 999), ("source_head_sha", "e" * 40),
                             ("source_repository", "other/repo")):
            with self.subTest(field=field):
                evidence = valid_evidence()
                evidence["artifacts"][0]["manifest"][field] = value
                self.assertEqual(build_recovery_proposal(evidence)["status"], "BLOCKED")

    def test_tool_does_not_touch_canonical_queue(self):
        # The public function accepts data only; no path or write/apply operation
        # is exposed. All blocked and ready outputs explicitly report no action.
        for evidence in (valid_evidence(), {"repository": REPO, "runs": [], "artifacts": []}):
            result = build_recovery_proposal(evidence)
            self.assertEqual(result["actions_taken"], [])
            self.assertEqual(result["mode"], "PROPOSAL_ONLY")
            self.assertNotIn("queue_path", result)
            self.assertNotIn("apply", result)


if __name__ == "__main__":
    unittest.main()
