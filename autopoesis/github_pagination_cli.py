"""Read-only CLI for complete GitHub REST pagination evidence."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from autopoesis.github_pagination import collect_paginated_collection


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="GitHub REST collection endpoint with any fixed filters")
    parser.add_argument("--collection-key", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--page-size", type=int, default=100)
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN")
    if not token:
        raise SystemExit("GH_TOKEN is required")
    parsed = urlparse(args.url)
    if parsed.scheme != "https" or parsed.netloc != "api.github.com" or not parsed.path.startswith("/repos/"):
        raise SystemExit("Only HTTPS api.github.com repository endpoints are allowed")
    fixed_query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                   if key not in {"page", "per_page"}]

    def fetch_page(page: int, per_page: int):
        query = fixed_query + [("per_page", str(per_page)), ("page", str(page))]
        request_url = urlunparse(parsed._replace(query=urlencode(query)))
        request = Request(
            request_url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "User-Agent": "autopoiesis-core-pagination-evidence",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
                link_header = response.headers.get("Link")
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise SystemExit(f"GitHub pagination request failed: {exc}") from exc
        return payload, link_header, request_url

    result = collect_paginated_collection(
        fetch_page,
        collection_key=args.collection_key,
        expected_page_size=args.page_size,
    )
    output = {
        args.collection_key: result["records"],
        "total_count": result["total_count"],
        "pagination_evidence": {
            "complete": result["complete"],
            "page_count": len(result["pages"]),
            "pages": result["pages"],
        },
    }
    Path(args.output).write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Captured {result['total_count']} {args.collection_key} across {len(result['pages'])} observed pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
