"""Regression checks for the scheduled workflow's safety contract.

These checks intentionally inspect the workflow source without requiring PyYAML.
The CI YAML parser separately validates syntax; this test protects key operational
guards from being accidentally removed during edits.
"""
from pathlib import Path
import unittest


WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "autopoiesis-cycle.yml"


class ScheduledWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")

    def test_schedule_and_manual_bootstrap_are_explicit(self):
        self.assertIn('cron: "17 */6 * * *"', self.source)
        self.assertIn("workflow_dispatch:", self.source)
        self.assertIn("default: false", self.source)
        self.assertIn("BOOTSTRAP: ${{ inputs.bootstrap || false }}", self.source)

    def test_execution_is_restricted_and_serialized(self):
        self.assertIn("github.repository == 'Autopoiesis-Intelligence/autopoiesis-core'", self.source)
        self.assertIn("github.ref == 'refs/heads/main'", self.source)
        self.assertIn("vars.AUTOPOIESIS_CYCLE_DISABLED != 'true'", self.source)
        self.assertIn("cancel-in-progress: false", self.source)
        self.assertIn("timeout-minutes: 20", self.source)

    def test_restore_is_provenance_bound_and_fail_closed(self):
        self.assertIn("status=completed&per_page=100", self.source)
        self.assertIn("gh api --paginate --slurp", self.source)
        self.assertIn("from autopoesis.scheduled_state import select_prior_successful_run", self.source)
        self.assertIn("pages = json.loads(Path(\".cycle-runs-pages.json\").read_text())", self.source)
        self.assertIn("conclusion", self.source)
        self.assertIn("source_run_id", self.source)
        self.assertIn("source_head_sha", self.source)
        self.assertIn("workflow_run", self.source)
        self.assertIn("sha256:[0-9a-f]{64}", self.source)
        self.assertIn("validate_queue_snapshot", self.source)
        self.assertIn("Installed queue differs from validated snapshot", self.source)

    def test_cycle_is_bounded_and_failure_is_not_hidden(self):
        self.assertIn("--budget-seconds 600", self.source)
        self.assertIn("set -o pipefail", self.source)
        self.assertIn("continue-on-error: true", self.source)
        self.assertIn("steps.cycle.outcome == 'failure'", self.source)

    def test_state_is_persisted_with_manifest(self):
        self.assertIn("create_queue_snapshot_manifest", self.source)
        self.assertIn("QUEUE_SNAPSHOT_MANIFEST.json", self.source)
        self.assertIn("name: autopoiesis-cycle-state", self.source)
        self.assertIn("retention-days: 30", self.source)


if __name__ == "__main__":
    unittest.main()
