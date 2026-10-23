"""Tests for observed-Link-header GitHub pagination collection."""
import unittest

from autopoesis.github_pagination import collect_paginated_collection, validate_paginated_collection


BASE = "https://api.github.com/repos/example/repo/actions/runs"


def page_url(page, size):
    return f"{BASE}?per_page={size}&page={page}"


def fixture_fetch(pages, headers):
    def fetch(page, size):
        return pages[page - 1], headers[page - 1], page_url(page, size)
    return fetch


class PaginationCollectorTests(unittest.TestCase):
    def test_follows_observed_next_link_and_records_raw_headers(self):
        payloads = [
            {"total_count": 3, "workflow_runs": [{"id": 1}, {"id": 2}]},
            {"total_count": 3, "workflow_runs": [{"id": 3}]},
        ]
        headers = [
            f'<{page_url(2, 2)}>; rel="next", <{page_url(2, 2)}>; rel="last"',
            None,
        ]
        result = collect_paginated_collection(
            fixture_fetch(payloads, headers), collection_key="workflow_runs", expected_page_size=2
        )
        self.assertEqual([x["id"] for x in result["records"]], [1, 2, 3])
        self.assertTrue(result["complete"])
        self.assertEqual(result["pages"][0]["link_header"], headers[0])
        self.assertIsNone(result["pages"][1]["next_page"])

    def test_no_next_link_is_terminal_only_after_observed_response(self):
        payloads = [{"total_count": 1, "workflow_runs": [{"id": 1}]}]
        result = collect_paginated_collection(
            fixture_fetch(payloads, [None]), collection_key="workflow_runs", expected_page_size=2
        )
        self.assertEqual(result["total_count"], 1)
        self.assertEqual(len(result["pages"]), 1)

    def test_skipped_page_link_blocks(self):
        headers = [f'<{page_url(3, 2)}>; rel="next"']
        with self.assertRaisesRegex(ValueError, "skips or repeats"):
            collect_paginated_collection(
                fixture_fetch([{"total_count": 3, "workflow_runs": [{"id": 1}, {"id": 2}]}], headers),
                collection_key="workflow_runs", expected_page_size=2
            )

    def test_inconsistent_page_size_in_link_blocks(self):
        url = f"{BASE}?per_page=3&page=2"
        with self.assertRaisesRegex(ValueError, "inconsistent per_page"):
            collect_paginated_collection(
                fixture_fetch([{"total_count": 3, "workflow_runs": [{"id": 1}, {"id": 2}]}],
                              [f'<{url}>; rel="next"']),
                collection_key="workflow_runs", expected_page_size=2
            )

    def test_cross_endpoint_link_blocks(self):
        url = "https://attacker.example/repos/example/repo/actions/runs?per_page=2&page=2"
        with self.assertRaisesRegex(ValueError, "changes API origin or endpoint"):
            collect_paginated_collection(
                fixture_fetch([{"total_count": 3, "workflow_runs": [{"id": 1}, {"id": 2}]}],
                              [f'<{url}>; rel="next"']),
                collection_key="workflow_runs", expected_page_size=2
            )

    def test_malformed_link_header_blocks(self):
        with self.assertRaisesRegex(ValueError, "Malformed"):
            collect_paginated_collection(
                fixture_fetch([{"total_count": 1, "workflow_runs": [{"id": 1}]}], ["rel=next"]),
                collection_key="workflow_runs", expected_page_size=2
            )

    def test_non_terminating_pagination_hits_guard(self):
        def endless(page, size):
            return {"total_count": 2, "workflow_runs": [{"id": page}]}, f'<{page_url(page + 1, size)}>; rel="next"', page_url(page, size)
        with self.assertRaisesRegex(ValueError, "max_pages"):
            collect_paginated_collection(endless, collection_key="workflow_runs", expected_page_size=1, max_pages=2)

    def test_validator_requires_captured_link_evidence(self):
        page = {"page": 1, "per_page": 2, "total_count": 1, "next_page": None,
                "request_url": page_url(1, 2), "workflow_runs": [{"id": 1}]}
        with self.assertRaisesRegex(ValueError, "Link header evidence"):
            validate_paginated_collection([page], collection_key="workflow_runs", expected_page_size=2)

    def test_missing_page_blocks(self):
        pages = [
            {"page": 1, "per_page": 2, "total_count": 3, "next_page": 2,
             "request_url": page_url(1, 2), "link_header": f'<{page_url(2, 2)}>; rel="next"',
             "workflow_runs": [{"id": 1}, {"id": 2}]}
        ]
        with self.assertRaisesRegex(ValueError, "Page count mismatch"):
            validate_paginated_collection(pages, collection_key="workflow_runs", expected_page_size=2)


if __name__ == "__main__":
    unittest.main()
