import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path

from autopoesis.artifact_archive import verify_and_extract_artifact


class ArtifactArchiveVerificationTests(unittest.TestCase):
    def _archive(self, root: Path, entries=None) -> tuple[Path, str]:
        archive_path = root / "artifact.zip"
        if entries is None:
            entries = {
                "TASK_QUEUE.json": b'{"version":1,"items":[],"history":[]}\n',
                "QUEUE_SNAPSHOT_MANIFEST.json": b'{"task_queue_sha256":"test"}\n',
                "RESULTS.json": b'{}\n',
            }
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return archive_path, "sha256:" + hashlib.sha256(archive_path.read_bytes()).hexdigest()

    def test_valid_archive_extracts_only_required_files_after_digest_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, digest = self._archive(root)
            destination = root / "out"
            result = verify_and_extract_artifact(archive, destination, digest)
            self.assertEqual(result["files_extracted"], 2)
            self.assertTrue((destination / "TASK_QUEUE.json").is_file())
            self.assertTrue((destination / "QUEUE_SNAPSHOT_MANIFEST.json").is_file())
            self.assertFalse((destination / "RESULTS.json").exists())

    def test_digest_mismatch_fails_before_creating_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, _digest = self._archive(root)
            destination = root / "out"
            with self.assertRaisesRegex(ValueError, "does not match"):
                verify_and_extract_artifact(archive, destination, "sha256:" + "0" * 64)
            self.assertFalse(destination.exists())

    def test_invalid_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, _digest = self._archive(root)
            with self.assertRaisesRegex(ValueError, "Expected artifact digest"):
                verify_and_extract_artifact(archive, root / "out", "not-a-digest")

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, _digest = self._archive(root, {
                "TASK_QUEUE.json": b"queue",
                "QUEUE_SNAPSHOT_MANIFEST.json": b"manifest",
                "../escape.txt": b"no",
            })
            digest = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "Unsafe artifact ZIP path"):
                verify_and_extract_artifact(archive, root / "out", digest)
            self.assertFalse((root / "escape.txt").exists())

    def test_missing_required_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, _digest = self._archive(root, {"TASK_QUEUE.json": b"queue"})
            digest = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "missing required files"):
                verify_and_extract_artifact(archive, root / "out", digest)

    def test_duplicate_required_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "artifact.zip"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("TASK_QUEUE.json", b"one")
                output.writestr("TASK_QUEUE.json", b"two")
                output.writestr("QUEUE_SNAPSHOT_MANIFEST.json", b"manifest")
            digest = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "duplicate entry"):
                verify_and_extract_artifact(archive, root / "out", digest)


if __name__ == "__main__":
    unittest.main()
