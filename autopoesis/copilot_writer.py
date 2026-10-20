"""Turn a test file written by the core's Copilot into a reviewable patch artifact.

Copilot runs outside the core (in GitHub Actions); the core never calls it and
makes no network or LLM calls. This writer only accepts the text Copilot
returned and holds it to the patch scope: one new ``tests/test_*.py`` file
that names its author on the first line. Nothing is applied or executed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from .executor import PatchFile, WriterResult, prepare_patch_artifact


AGENT_LINE = "# Agent: Copilot (core)"
MAX_TEST_BYTES = 12000
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_TEST_PATH = re.compile(r"^tests/test_[a-z0-9_]{1,60}\.py$")
# PEP 263: a coding declaration on line 1 or 2 would make Python run different text than was reviewed.
_CODING = re.compile(r"^[ \t\f]*#.*?coding[:=]")
_FENCED = re.compile(r"\A```(?:python)?\n(.*\n)```\n?\Z", re.DOTALL)


class CopilotTestWriter:
    """Wrap one test file the core's Copilot already wrote; never call the agent."""

    writer_id = "copilot-cli-tests-v1"

    def __init__(self, response: str) -> None:
        if not isinstance(response, str):
            raise ValueError("Copilot response must be text")
        self.response = response

    def prepare(self, task: dict[str, Any], repository_root: Path) -> WriterResult:
        task_id = task.get("id")
        target = task.get("target")
        if not isinstance(task_id, str) or not _SAFE_ID.fullmatch(task_id):
            raise ValueError("Task id contains unsupported characters")
        if not isinstance(target, str) or not _TEST_PATH.fullmatch(target):
            raise ValueError("Task target must be a new tests/test_*.py path")

        resolved_root = repository_root.resolve()
        resolved_target = (resolved_root / target).resolve()
        if resolved_target.parent != resolved_root / "tests":
            raise ValueError("Task target escapes the tests directory")
        if resolved_target.exists():
            raise ValueError(f"Refusing to overwrite existing test file: {target}")

        content = unwrap_response(self.response)
        if content.split("\n", 1)[0] != AGENT_LINE:
            raise ValueError(f"Copilot test file must start with {AGENT_LINE!r}")
        if any(_CODING.match(line) for line in content.split("\n")[:2]):
            raise ValueError("Copilot test file must not declare a source encoding")
        if len(content.encode("utf-8")) > MAX_TEST_BYTES:
            raise ValueError(f"Copilot test file exceeds {MAX_TEST_BYTES} bytes")

        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return WriterResult(
            status="PATCH_PREPARED",
            writer_id=self.writer_id,
            task_id=task_id,
            files=(PatchFile(path=target, content=content, sha256=digest),),
            rationale=(
                "Wrapped one test file proposed by the core's Copilot. The source tree was "
                "not modified and the test was not run; review and verification are still required."
            ),
        )


def unwrap_response(response: str) -> str:
    """Return the file text, unwrapping one surrounding code fence; reject anything else."""
    text = response.replace("\r\n", "\n")
    fenced = _FENCED.match(text)
    if fenced:
        text = fenced.group(1)
    if "```" in text:
        raise ValueError("Copilot response must be one Python file, not prose with code blocks")
    if not text.endswith("\n"):
        text += "\n"
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--target", required=True, help="new test path, for example tests/test_executor.py")
    parser.add_argument("--response-file", required=True, type=Path)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        args.output.unlink(missing_ok=True)
        writer = CopilotTestWriter(args.response_file.read_text(encoding="utf-8"))
        artifact = prepare_patch_artifact(
            {"id": args.task_id, "target": args.target}, args.repository_root, writer
        )
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"status": "REJECTED", "reason": str(exc)}))
        return 2
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": artifact["status"], "validation": artifact["validation"]["status"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
