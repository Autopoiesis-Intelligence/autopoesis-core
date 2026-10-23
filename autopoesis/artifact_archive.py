"""Fail-closed verification and safe extraction of a GitHub Actions artifact ZIP."""
from __future__ import annotations

import hashlib
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

_SHA256_DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
_REQUIRED = {"TASK_QUEUE.json", "QUEUE_SNAPSHOT_MANIFEST.json"}


def verify_and_extract_artifact(archive_path: Path, destination: Path, expected_digest: str) -> dict[str, str | int]:
    """Verify the archive digest before extracting only required regular files."""
    match = _SHA256_DIGEST.fullmatch(expected_digest) if isinstance(expected_digest, str) else None
    if match is None:
        raise ValueError("Expected artifact digest must be sha256 followed by 64 lowercase hex digits")
    archive_path, destination = Path(archive_path), Path(destination)
    if not archive_path.is_file():
        raise ValueError("Artifact archive file is missing")

    digest = hashlib.sha256()
    with archive_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_digest = digest.hexdigest()
    if actual_digest != match.group(1):
        raise ValueError("Artifact ZIP SHA-256 does not match GitHub API artifact digest")

    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    found: dict[str, zipfile.ZipInfo] = {}
    with zipfile.ZipFile(archive_path, "r") as archive:
        for info in archive.infolist():
            name = info.filename
            path = PurePosixPath(name)
            if path.is_absolute() or not name or "\\\\" in name or any(part in ("", ".", "..") for part in path.parts):
                raise ValueError(f"Unsafe artifact ZIP path: {name!r}")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"Artifact ZIP contains a symbolic link: {name!r}")
            if info.is_dir():
                continue
            if name in found:
                raise ValueError(f"Artifact ZIP contains a duplicate entry: {name!r}")
            if name in _REQUIRED:
                found[name] = info
        missing = _REQUIRED - found.keys()
        if missing:
            raise ValueError(f"Artifact ZIP is missing required files: {', '.join(sorted(missing))}")
        for name, info in found.items():
            output = (root / name).resolve()
            if output.parent != root:
                raise ValueError(f"Artifact ZIP path escapes extraction directory: {name!r}")
            with archive.open(info, "r") as source, output.open("xb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
    return {"sha256": actual_digest, "files_extracted": len(found)}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3:
        print("usage: python -m autopoesis.artifact_archive ARCHIVE.zip DESTINATION EXPECTED_DIGEST", file=sys.stderr)
        return 2
    try:
        result = verify_and_extract_artifact(Path(args[0]), Path(args[1]), args[2])
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        print(f"Artifact archive verification failed: {exc}", file=sys.stderr)
        return 1
    print(f"Verified artifact archive SHA-256 {result['sha256']}; extracted {result['files_extracted']} required files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
