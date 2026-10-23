"""Regression tests for strict captured GitHub pagination evidence."""
import unittest

from autopoesis.github_pagination import validate_paginated_collection


def sample_pages():
    return [
        {
            "page": 1,
            "per_page": 2,
            "total_count": 3,
            "next_page": 2,
            "workflow_runs": [{"id": 11}, {"id": 12}],
        },
        {
            "page": 2,
            "per_page": 2,
            "total_count": 3,
            "next_page": None,
            "workflow_runs": [{"id": 13}],
        },
    ]


class PaginatedCollectionTests(unittest.TestCase):
    def validate(self, pages):
        return validate_paginated_collection(
            pages, collection_key="workflow_runs", expected_page_size=2
        )

    def test_complete_pages_return_all_records_in_order(self):
        records = self.validate(sample_pages())
        self.assertEqual([item["id"] for item in records], [11, 12, 13])

    def test_missing_terminal_page_blocks(self):
        with self.assertRaisesRegex(ValueError, "Page count mismatch"):
            self.validate(sample_pages()[:1])

    def test_missing_next_page_link_blocks(self):
        pages = sample_pages()
        pages[0]["next_page"] = None
        with self.assertRaisesRegex(ValueError, "next-page evidence"):
            self.validate(pages)

    def test_extra_next_page_link_after_terminal_page_blocks(self):
        pages = sample_pages()
        pages[1]["next_page"] = 3
        with self.assertRaisesRegex(ValueError, "next-page evidence"):
            self.validate(pages)

    def test_conflicting_total_count_blocks(self):
        pages = sample_pages()
        pages[1]["total_count"] = 4
        with self.assertRaisesRegex(ValueError, "total_count conflicts"):
            self.validate(pages)

    def test_duplicate_identity_across_pages_blocks(self):
        pages = sample_pages()
        pages[1]["workflow_runs"][0]["id"] = 12
        with self.assertRaisesRegex(ValueError, "Duplicate id"):
            self.validate(pages)

    def test_record_count_must_match_total_count(self):
        pages = sample_pages()
        pages[1]["workflow_runs"] = []
        with self.assertRaisesRegex(ValueError, "Record count mismatch"):
            self.validate(pages)

    def test_nonterminal_page_must_not_be_short(self):
        pages = sample_pages()
        pages[0]["workflow_runs"] = [{"id": 11}]
        with self.assertRaisesRegex(ValueError, "unexpectedly short"):
            self.validate(pages)

    def test_page_sequence_must_start_at_one_and_be_contiguous(self):
        pages = sample_pages()
        pages[1]["page"] = 3
        with self.assertRaisesRegex(ValueError, "Expected page 2"):
            self.validate(pages)

    def test_empty_capture_is_not_proof_of_empty_history(self):
        with self.assertRaisesRegex(ValueError, "at least one page"):
            self.validate([])


if __name__ == "__main__":
    unittest.main()
