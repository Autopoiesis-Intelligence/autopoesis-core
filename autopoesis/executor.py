"""Replaceable, bounded code-writing adapters that emit reviewable patch artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .core import canonical_json


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


@dataclass(frozen=True)
class PatchFile:
    path: str
    content: str
    sha256: str


@dataclass(frozen=True)
class WriterResult:
    status: str
    writer_id: str
    task_id: str
    files: tuple[PatchFile, ...]
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "writer_id": self.writer_id,
            "task_id": self.task_id,
            "files": [
                {"path": item.path, "content": item.content, "sha256": item.sha256}
                for item in self.files
            ],
            "rationale": self.rationale,
        }


class CodeWriter(Protocol):
    """Provider-neutral contract: produce a patch artifact, never execute it."""

    writer_id: str

    def prepare(self, task: dict[str, Any], repository_root: Path) -> WriterResult:
        """Return proposed files without modifying the repository."""


class BoundedTestScaffoldWriter:
    """Generate a minimal import-smoke-test patch for one supported Python module."""

    writer_id = "bounded-test-scaffold-v1"

    def prepare(self, task: dict[str, Any], repository_root: Path) -> WriterResult:
        task_id = task.get("id")
        source_value = task.get("source")
        if not isinstance(task_id, str) or not _SAFE_ID.fullmatch(task_id):
            raise ValueError("Task id contains unsupported characters")
        if not isinstance(source_value, str) or not source_value.endswith(".py"):
            raise ValueError("Task source must be a Python file path")

        source_path = Path(source_value)
        if source_path.is_absolute() or ".." in source_path.parts:
            raise ValueError("Task source must stay inside the repository")
        if not source_value.startswith("autopoesis/") or source_path.name == "__init__.py":
            raise ValueError("Writer only supports non-package Python modules under autopoesis/")
        resolved_root = repository_root.resolve()
        resolved_source = (resolved_root / source_path).resolve()
        if resolved_root not in resolved_source.parents or not resolved_source.is_file():
            raise ValueError("Task source does not resolve to an existing repository file")

        test_path = Path("tests") / f"test_{source_path.stem}.py"
        resolved_test = (resolved_root / test_path).resolve()
        if resolved_root not in resolved_test.parents:
            raise ValueError("Generated test path escapes the repository")
        if resolved_test.exists():
            raise ValueError(f"Refusing to overwrite existing test file: {test_path.as_posix()}")

        module_name = ".".join(source_path.with_suffix("").parts)
        test_content = (
            f'"""Generated import smoke test for {module_name}."""\n\n'
            "import importlib\n"
            "import unittest\n\n\n"
            "class GeneratedImportSmokeTest(unittest.TestCase):\n"
            "    def test_module_imports(self):\n"
            f"        module = importlib.import_module({module_name!r})\n"
            "        self.assertIsNotNone(module)\n\n\n"
            'if __name__ == "__main__":\n'
            "    unittest.main()\n"
        )
        digest = hashlib.sha256(test_content.encode("utf-8")).hexdigest()
        return WriterResult(
            status="PATCH_PREPARED",
            writer_id=self.writer_id,
            task_id=task_id,
            files=(PatchFile(path=test_path.as_posix(), content=test_content, sha256=digest),),
            rationale=(
                "Generated one deterministic import-smoke-test file for an existing module. "
                "The source tree was not modified; review and verification are still required."
            ),
        )


def prepare_patch_artifact(
    task: dict[str, Any],
    repository_root: Path,
    writer: CodeWriter | None = None,
) -> dict[str, Any]:
    """Create a deterministic JSON patch artifact; do not apply or execute it."""
    selected_writer = writer or BoundedTestScaffoldWriter()
    result = selected_writer.prepare(task, repository_root)
    payload = result.to_dict()
    payload["artifact_sha256"] = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return payload
