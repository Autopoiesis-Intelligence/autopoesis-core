import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from autopoesis.copilot_writer import AGENT_LINE, MAX_TEST_BYTES, CopilotTestWriter, unwrap_response
from autopoesis.executor import apply_patch_to_sandbox, prepare_patch_artifact, validate_patch_artifact


ROOT = Path(__file__).resolve().parents[1]
GOOD = AGENT_LINE + '\n"""Synthetic Copilot response used only by these tests."""\n\nimport unittest\n'
TASK = {"id": "CL-004-T1", "target": "tests/test_synthetic_copilot.py"}


def prepare(response, task=TASK, root=ROOT):
    return prepare_patch_artifact(task, root, CopilotTestWriter(response))


class CopilotTestWriterTests(unittest.TestCase):
    def test_valid_response_becomes_a_validated_artifact(self):
        artifact = prepare(GOOD)
        self.assertEqual(artifact["writer_id"], "copilot-cli-tests-v1")
        self.assertEqual([item["path"] for item in artifact["files"]], [TASK["target"]])
        self.assertEqual(artifact["files"][0]["content"], GOOD)
        self.assertEqual(validate_patch_artifact(artifact)["status"], "VALID")
        self.assertFalse((ROOT / TASK["target"]).exists())

    def test_one_surrounding_fence_is_unwrapped(self):
        self.assertEqual(unwrap_response("```python\r\n" + GOOD.replace("\n", "\r\n") + "```\r\n"), GOOD)
        self.assertEqual(unwrap_response("```\n" + GOOD + "```"), GOOD)
        self.assertEqual(unwrap_response(GOOD.rstrip("\n")), GOOD)

    def test_prose_around_code_is_rejected(self):
        for response in ("Here is the test:\n```python\n" + GOOD + "```\n", GOOD + "```\nextra\n```\n"):
            with self.assertRaises(ValueError):
                prepare(response)

    def test_missing_author_line_is_rejected(self):
        for response in ('"""No author line."""\n', "\n" + GOOD, "# Agent: Claude\nimport unittest\n"):
            with self.assertRaises(ValueError):
                prepare(response)

    def test_targets_outside_new_test_files_are_rejected(self):
        for target in ("tests/test_core.py", "autopoesis/core.py", "tests/../run_tasks.py",
                       "tests/sub/test_x.py", "tests/test_X.py", "/tmp/test_x.py", None):
            with self.assertRaises(ValueError, msg=target):
                prepare(GOOD, {"id": "CL-004-T1", "target": target})
        with self.assertRaises(ValueError):
            prepare(GOOD, {"id": "../x", "target": TASK["target"]})

    def test_symlinked_tests_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            outside = Path(directory) / "outside"
            root.mkdir()
            outside.mkdir()
            (root / "tests").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                prepare(GOOD, root=root)

    def test_oversized_or_invalid_python_is_rejected(self):
        with self.assertRaises(ValueError):
            prepare(GOOD + "#" * MAX_TEST_BYTES + "\n")
        with self.assertRaises(ValueError):
            prepare(AGENT_LINE + "\ndef broken(:\n")

    def test_source_encoding_declaration_is_rejected(self):
        # UTF-7 would turn the "comment" on line 3 into code when Python reads the file.
        hidden = AGENT_LINE + "\n# -*- coding: utf-7 -*-\n# note +AAo-print('hidden')\nimport unittest\n"
        for response in (hidden, AGENT_LINE + "\n# vim: set fileencoding=utf-8 :\n"):
            with self.assertRaises(ValueError):
                prepare(response)

    def test_artifact_applies_only_inside_a_sandbox(self):
        with tempfile.TemporaryDirectory() as directory:
            result = apply_patch_to_sandbox(prepare(GOOD), Path(directory))
            self.assertEqual(result["files_written"], [TASK["target"]])
            self.assertEqual((Path(directory) / TASK["target"]).read_text(encoding="utf-8"), GOOD)

    def test_cli_writes_artifact_or_rejects(self):
        with tempfile.TemporaryDirectory() as directory:
            response = Path(directory) / "response.txt"
            output = Path(directory) / "artifact.json"
            command = [sys.executable, "-m", "autopoesis.copilot_writer", "--task-id", TASK["id"],
                       "--target", TASK["target"], "--response-file", str(response),
                       "--repository-root", str(ROOT), "--output", str(output)]

            response.write_text(GOOD, encoding="utf-8")
            accepted = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            self.assertEqual(validate_patch_artifact(json.loads(output.read_text(encoding="utf-8")))["status"], "VALID")

            # An existing output is refused and kept, including when it is the response itself.
            accepted_artifact = output.read_bytes()
            stale = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(stale.returncode, 2, stale.stderr)
            self.assertEqual(output.read_bytes(), accepted_artifact)
            same = command[:-1] + [str(response)]
            self.assertEqual(subprocess.run(same, cwd=ROOT, capture_output=True, text=True).returncode, 2)
            self.assertEqual(response.read_text(encoding="utf-8"), GOOD)

            output.unlink()
            for bad in ("import os\n", AGENT_LINE + "\nx=" + "~" * 11000 + "1\n"):
                response.write_text(bad, encoding="utf-8")
                rejected = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
                self.assertEqual(rejected.returncode, 2, rejected.stderr)
                self.assertEqual(json.loads(rejected.stdout)["status"], "REJECTED")
                self.assertFalse(output.exists())

if __name__ == "__main__":
    unittest.main()
