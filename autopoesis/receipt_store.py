"""Atomic, hash-chained local journal for decision records.

The journal is integrity-evident, not tamper-proof: a writer able to rewrite the
entire file can recompute hashes. It assumes a single writer; cross-process
locking and fsync durability guarantees are not claimed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .core import EvolutionError, canonical_json, digest_state

JOURNAL_SCHEMA_VERSION = 1
GENESIS_DIGEST = "0" * 64


class JournalIntegrityError(ValueError):
    """Raised when a journal is malformed, duplicated, or hash-chain-invalid."""


def _validate_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise JournalIntegrityError("Journal record must be a JSON object.")
    receipt_id = record.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id.strip():
        raise JournalIntegrityError("Record requires a non-empty receipt_id.")
    try:
        # Also rejects NaN/Infinity, unsupported objects, and invalid JSON data.
        canonical_json(record)
    except EvolutionError as exc:
        raise JournalIntegrityError(str(exc)) from exc
    return record


def _entry_digest(entry_without_digest: dict[str, Any]) -> str:
    return digest_state(entry_without_digest)


def load_journal(path: str | Path) -> dict[str, Any]:
    """Load and fully verify a journal snapshot; a missing file is an empty journal."""
    journal_path = Path(path)
    if not journal_path.exists():
        return {"schema_version": JOURNAL_SCHEMA_VERSION, "entries": []}
    try:
        raw = json.loads(journal_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise JournalIntegrityError(f"Cannot read journal: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != JOURNAL_SCHEMA_VERSION:
        raise JournalIntegrityError("Unsupported or malformed journal schema.")
    entries = raw.get("entries")
    if not isinstance(entries, list):
        raise JournalIntegrityError("Journal entries must be a list.")

    previous = GENESIS_DIGEST
    seen_ids: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise JournalIntegrityError(f"Entry {index} must be an object.")
        if entry.get("sequence") != index:
            raise JournalIntegrityError(f"Entry {index} has invalid sequence.")
        if entry.get("previous_digest") != previous:
            raise JournalIntegrityError(f"Entry {index} breaks the previous-digest chain.")
        record = _validate_record(entry.get("record"))
        if record["receipt_id"] in seen_ids:
            raise JournalIntegrityError(f"Duplicate receipt_id: {record['receipt_id']}")
        seen_ids.add(record["receipt_id"])
        expected = _entry_digest({
            "sequence": index,
            "previous_digest": previous,
            "record": record,
        })
        if entry.get("entry_digest") != expected:
            raise JournalIntegrityError(f"Entry {index} digest mismatch.")
        previous = expected
    return raw


def append_record(path: str | Path, record: dict[str, Any]) -> dict[str, Any]:
    """Append a record using same-directory replace; intended for a single writer."""
    journal_path = Path(path)
    validated = _validate_record(record)
    journal = load_journal(journal_path)
    if any(item["record"]["receipt_id"] == validated["receipt_id"] for item in journal["entries"]):
        raise JournalIntegrityError(f"Duplicate receipt_id: {validated['receipt_id']}")

    previous = (
        journal["entries"][-1]["entry_digest"]
        if journal["entries"] else GENESIS_DIGEST
    )
    sequence = len(journal["entries"]) + 1
    unsigned = {
        "sequence": sequence,
        "previous_digest": previous,
        "record": validated,
    }
    entry = {**unsigned, "entry_digest": _entry_digest(unsigned)}
    updated = {
        "schema_version": JOURNAL_SCHEMA_VERSION,
        "entries": [*journal["entries"], entry],
    }

    journal_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = journal_path.with_name(journal_path.name + ".tmp")
    try:
        temp_path.write_text(canonical_json(updated) + "\n", encoding="utf-8")
        os.replace(temp_path, journal_path)
    except OSError:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return entry
