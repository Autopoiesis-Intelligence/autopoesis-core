"""Capture complete GitHub REST collection pagination from observed Link headers.

The caller supplies a transport callback. Every captured page records its requested
URL and raw Link header; terminal-page evidence is derived only from the observed
response header, never from an arbitrary stopping condition.
"""
from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


_LINK_PART = re.compile(r',(?=\s*<)')


def _links(header: str | None) -> dict[str, str]:
    if header is None or header.strip() == "":
        return {}
    if not isinstance(header, str):
        raise ValueError("Link header must be text or None")
    result: dict[str, str] = {}
    for part in _LINK_PART.split(header):
        match = re.fullmatch(r'\s*<([^>]+)>\s*;\s*rel="([^"]+)"\s*', part)
        if not match:
            raise ValueError("Malformed pagination Link header")
        url, relation = match.groups()
        for rel in relation.split():
            if rel in result:
                raise ValueError(f"Duplicate Link relation: {rel}")
            result[rel] = url
    return result


def _page_from_url(url: str, *, expected_page_size: int) -> int:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    pages = query.get("page", [])
    sizes = query.get("per_page", [])
    if len(pages) != 1 or not pages[0].isdigit():
        raise ValueError("Next-page URL must contain one numeric page parameter")
    if len(sizes) != 1 or not sizes[0].isdigit() or int(sizes[0]) != expected_page_size:
        raise ValueError("Next-page URL has inconsistent per_page parameter")
    return int(pages[0])


def collect_paginated_collection(
    fetch_page: Callable[[int, int], tuple[dict[str, Any], str | None, str]],
    *,
    collection_key: str,
    expected_page_size: int = 100,
    max_pages: int = 1000,
) -> dict[str, Any]:
    """Fetch pages until observed Link metadata has no rel=next.

    fetch_page(page, per_page) returns (JSON payload, raw Link header, request URL).
    The returned evidence includes raw Link headers and URLs and is validated
    before records are returned. A max-pages guard fails closed if pagination
    does not terminate.
    """
    if type(expected_page_size) is not int or expected_page_size < 1:
        raise ValueError("Expected page size must be a positive integer")
    if type(max_pages) is not int or max_pages < 1:
        raise ValueError("max_pages must be a positive integer")
    captured: list[dict[str, Any]] = []
    page_number = 1
    while True:
        if page_number > max_pages:
            raise ValueError("Pagination exceeded max_pages without observed termination")
        payload, link_header, request_url = fetch_page(page_number, expected_page_size)
        if not isinstance(payload, dict):
            raise ValueError(f"Page {page_number} payload must be a JSON object")
        if not isinstance(request_url, str) or not request_url:
            raise ValueError(f"Page {page_number} request URL is missing")
        links = _links(link_header)
        next_url = links.get("next")
        next_page = _page_from_url(next_url, expected_page_size=expected_page_size) if next_url else None
        if next_page is not None and next_page != page_number + 1:
            raise ValueError(f"Page {page_number} Link header skips or repeats a page")
        if "last" in links and next_page is None and _page_from_url(links["last"], expected_page_size=expected_page_size) != page_number:
            raise ValueError("Terminal Link header conflicts with its last-page URL")
        captured.append({
            "page": page_number,
            "per_page": expected_page_size,
            "total_count": payload.get("total_count"),
            "next_page": next_page,
            "request_url": request_url,
            "link_header": link_header,
            collection_key: payload.get(collection_key),
        })
        if next_page is None:
            break
        page_number = next_page

    records = validate_paginated_collection(
        captured,
        collection_key=collection_key,
        expected_page_size=expected_page_size,
    )
    return {
        "pages": captured,
        "records": records,
        "total_count": captured[0]["total_count"],
        "complete": True,
    }


def validate_paginated_collection(
    pages: Any,
    *,
    collection_key: str,
    identity_key: str = "id",
    expected_page_size: int = 100,
) -> list[dict[str, Any]]:
    """Return records only when page sequence and count evidence are consistent."""
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
        raise ValueError(f"Page count mismatch: expected {expected_pages}, received {len(pages)}")

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
        if not isinstance(page_data.get("request_url"), str) or not page_data["request_url"]:
            raise ValueError(f"Page {index} has no captured request URL")
        if "link_header" not in page_data:
            raise ValueError(f"Page {index} has no captured Link header evidence")

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
        raise ValueError(f"Record count mismatch: total_count={total_count}, collected={len(records)}")
    return records
