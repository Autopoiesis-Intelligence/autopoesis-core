# Agent: Claude
"""Executor contract cases that tests/test_core.py and tests/test_copilot_writer.py do not check."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from autopoesis.core import canonical_json
from autopoesis.executor import BoundedTestScaffoldWriter, apply_patch_to_sandbox, validate_patch_artifact


def artifact(files):
    """Build an artifact whose file and envelope hashes are correct, so only the case under test fails."""
    payload = {
        "status": "PATCH_PREPARED",
        "writer_id": "test-writer",
        "task_id": "EXEC-T1",
        "files": [
            {"path": path, "content": content, "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()}
            for path, content in files
        ],
        "rationale": "test",
    }
    payload["artifact_sha256"] = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return payload


GOOD = artifact([("tests/test_example.py", "VALUE = 1\n")])


class ValidatePatchArtifactTests(unittest.TestCase):
    def test_envelope_without_a_matching_checksum_or_files_is_rejected(self):
        self.assertEqual(validate_patch_artifact(GOOD)["status"], "VALID")
        no_hash = dict(GOOD, artifact_sha256="abc")
        changed = dict(GOOD, rationale="changed after hashing")
        for case in ([], no_hash, changed, artifact([])):
            with self.assertRaises(ValueError, msg=repr(case)[:60]):
                validate_patch_artifact(case)

    def test_duplicate_or_unnormalized_paths_are_rejected(self):
        cases = (
            [("tests/test_example.py", "A = 1\n"), ("tests/test_example.py", "B = 2\n")],
            [("tests/./test_example.py", "A = 1\n")],
            [("tests//test_example.py", "A = 1\n")],
            [("tests/example.py", "A = 1\n")],
        )
        for files in cases:
            with self.assertRaises(ValueError, msg=files[0][0]):
                validate_patch_artifact(artifact(files))


class ApplyPatchToSandboxTests(unittest.TestCase):
    def test_symlinked_sandbox_tests_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            sandbox = Path(directory) / "sandbox"
            outside = Path(directory) / "outside"
            sandbox.mkdir()
            outside.mkdir()
            (sandbox / "tests").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                apply_patch_to_sandbox(GOOD, sandbox)
            self.assertEqual(list(outside.iterdir()), [])


class BoundedTestScaffoldWriterTests(unittest.TestCase):
    def test_unsupported_tasks_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "autopoesis").mkdir()
            (root / "autopoesis" / "__init__.py").write_text("", encoding="utf-8")
            (root / "autopoesis" / "covered.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_covered.py").write_text("KEEP = True\n", encoding="utf-8")
            (root / "run_tasks.py").write_text("VALUE = 1\n", encoding="utf-8")
            cases = (
                {"id": "../x", "source": "autopoesis/covered.py"},
                {"id": "EXEC-T1", "source": "autopoesis/__init__.py"},
                {"id": "EXEC-T1", "source": "run_tasks.py"},
                {"id": "EXEC-T1", "source": "autopoesis/missing.py"},
                {"id": "EXEC-T1", "source": "autopoesis/covered.py"},
            )
            for task in cases:
                with self.assertRaises(ValueError, msg=task):
                    BoundedTestScaffoldWriter().prepare(task, root)
            self.assertEqual((root / "tests" / "test_covered.py").read_text(encoding="utf-8"), "KEEP = True\n")


if __name__ == "__main__":
    unittest.main()
