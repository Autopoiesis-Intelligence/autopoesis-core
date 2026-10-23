"""Strict validation for captured, paginated GitHub API collections.

This module validates pagination evidence supplied by a collector; it does not
make network requests. The collector must preserve each page's observed
pagination Link-header result as next_page (the next page number, or None).
A caller must not synthesize next_page=None merely because it stopped fetching.
"""
from __future__ import annotations

from typing import Any


def validate_paginated_collection(
    pages: Any,
    *,
    collection_key: str,
    identity_key: str = "id",
    expected_page_size: int = 100,
) -> list[dict[str, Any]]:
    """Return records only when page sequence and count evidence are consistent.

    Each captured page has this normalized shape:
      {"page": 1, "per_page": 100, "total_count": 201,
       "next_page": 2, "<collection_key>": [...]}

    next_page must come from the response's pagination link metadata.
    The total_count is checked against all collected records, expected page
    count, per-page bounds, sequential links, and unique record identities.
    """
    if not isinstance(pages, list) or not pages:
        raise ValueError("Pagination evidence must contain at least one page")
    if not isinstance(collection_key, str) or not collection_key:
        raise ValueError("Collection key must be a non-empty string")
    if not isinstance(identity_key, str) or not identity_key:
        raise ValueError("Identity key must be a non-empty string")
    if type(expected_page_size) is not int or expected_page_size < 1:
        raise ValueError("Expected page size must be a positive integer")

    first = pages[0]
    if not isinstance(first, dict) or type(first.get("total_count")) is not int:
        raise ValueError("First page has no valid total_count")
    total_count = first["total_count"]
    if total_count < 0:
        raise ValueError("total_count cannot be negative")

    records: list[dict[str, Any]] = []
    seen: set[tuple[type, Any]] = set()
    expected_pages = max(1, (total_count + expected_page_size - 1) // expected_page_size)
    if len(pages) != expected_pages:
        raise ValueError(
            f"Page count mismatch: expected {expected_pages}, received {len(pages)}"
        )

    for index, page_data in enumerate(pages, start=1):
        if not isinstance(page_data, dict):
            raise ValueError(f"Page {index} is malformed")
        if type(page_data.get("page")) is not int or page_data["page"] != index:
            raise ValueError(f"Expected page {index} in sequence")
        if type(page_data.get("per_page")) is not int or page_data["per_page"] != expected_page_size:
            raise ValueError(f"Page {index} has unexpected per_page")
        if type(page_data.get("total_count")) is not int or page_data["total_count"] != total_count:
            raise ValueError(f"Page {index} total_count conflicts with first page")

        expected_next = index + 1 if index < expected_pages else None
        if page_data.get("next_page") != expected_next:
            raise ValueError(f"Page {index} next-page evidence is inconsistent")

        page_records = page_data.get(collection_key)
        if not isinstance(page_records, list):
            raise ValueError(f"Page {index} has no {collection_key} list")
        if len(page_records) > expected_page_size:
            raise ValueError(f"Page {index} exceeds expected page size")
        if index < expected_pages and len(page_records) != expected_page_size:
            raise ValueError(f"Non-terminal page {index} is unexpectedly short")

        for record in page_records:
            if not isinstance(record, dict):
                raise ValueError(f"Page {index} contains a malformed record")
            identity = record.get(identity_key)
            if identity is None or isinstance(identity, (dict, list, set)):
                raise ValueError(f"Page {index} record has no scalar {identity_key}")
            marker = (type(identity), identity)
            if marker in seen:
                raise ValueError(f"Duplicate {identity_key} across paginated records")
            seen.add(marker)
            records.append(record)

    if len(records) != total_count:
        raise ValueError(
            f"Record count mismatch: total_count={total_count}, collected={len(records)}"
        )
    return records
