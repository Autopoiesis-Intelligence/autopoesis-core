"""CLI tests prove the HTTP transport captures response Link headers."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from autopoesis import github_pagination_cli


class FakeResponse:
    def __init__(self, payload, link):
        self.payload = json.dumps(payload).encode("utf-8")
        self.headers = {"Link": link} if link is not None else {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


class PaginationCliTests(unittest.TestCase):
    def test_cli_uses_observed_link_headers_and_emits_complete_evidence(self):
        urls = []

        def fake_urlopen(request, timeout):
            urls.append(request.full_url)
            page = 1 if "page=1" in request.full_url else 2
            if page == 1:
                return FakeResponse(
                    {"total_count": 3, "workflow_runs": [{"id": 1}, {"id": 2}]},
                    '<https://api.github.com/repos/example/repo/actions/runs?event=workflow_dispatch&per_page=2&page=2>; rel="next", '
                    '<https://api.github.com/repos/example/repo/actions/runs?event=workflow_dispatch&per_page=2&page=2>; rel="last"',
                )
            return FakeResponse({"total_count": 3, "workflow_runs": [{"id": 3}]}, None)

        with tempfile.TemporaryDirectory() as directory:
            output = os.path.join(directory, "captured.json")
            argv = [
                "https://api.github.com/repos/example/repo/actions/runs?event=workflow_dispatch",
                "--collection-key", "workflow_runs", "--output", output, "--page-size", "2",
            ]
            with patch.dict(os.environ, {"GH_TOKEN": "test-token"}), \
                 patch("autopoesis.github_pagination_cli.urlopen", side_effect=fake_urlopen), \
                 patch("sys.argv", ["github_pagination_cli", *argv]):
                self.assertEqual(github_pagination_cli.main(), 0)
            captured = json.loads(open(output, encoding="utf-8").read())

        self.assertEqual(len(urls), 2)
        self.assertIn("page=1", urls[0])
        self.assertIn("page=2", urls[1])
        self.assertEqual([item["id"] for item in captured["workflow_runs"]], [1, 2, 3])
        self.assertTrue(captured["pagination_evidence"]["complete"])
        self.assertEqual(captured["pagination_evidence"]["page_count"], 2)
        self.assertIn("link_header", captured["pagination_evidence"]["pages"][0])


if __name__ == "__main__":
    unittest.main()
