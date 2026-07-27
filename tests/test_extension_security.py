from __future__ import annotations

import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BOOTSTRAP = (ROOT / "zotero-extension" / "bootstrap.js").read_text(
    encoding="utf-8"
)
MANIFEST = json.loads(
    (ROOT / "zotero-extension" / "manifest.json").read_text(encoding="utf-8")
)


class ExtensionSecurityTests(unittest.TestCase):
    def test_no_hard_coded_token(self):
        self.assertNotRegex(BOOTSTRAP, r"DEFAULT_TOKEN\s*[:=]")
        self.assertNotIn('searchParams.get("token")', BOOTSTRAP)
        self.assertNotIn("queryToken", BOOTSTRAP)

    def test_origin_and_host_are_checked(self):
        self.assertIn("headers.origin", BOOTSTRAP)
        self.assertRegex(BOOTSTRAP, r"127\\\.0\\\.0\\\.1")
        self.assertIn("Only loopback requests are allowed", BOOTSTRAP)

    def test_write_gates_and_trash_confirmation(self):
        self.assertIn("WRITE_WINDOW_MS", BOOTSTRAP)
        self.assertIn("!dryRun && !bridge.writesAllowed()", BOOTSTRAP)
        self.assertIn('input.confirmation !== "TRASH"', BOOTSTRAP)
        self.assertNotIn("eraseTx", BOOTSTRAP)

    def test_no_arbitrary_file_operations(self):
        forbidden = [
            "planPath",
            "getContentsAsync",
            "importFromFile",
            "downloaded_pdf",
        ]
        for value in forbidden:
            self.assertNotIn(value, BOOTSTRAP)

    def test_manifest_has_no_placeholder_update_url(self):
        update_url = MANIFEST["applications"]["zotero"]["update_url"]
        self.assertTrue(update_url.startswith("https://raw.githubusercontent.com/"))
        self.assertNotIn("example.com", update_url)

    def test_public_errors_do_not_return_stack(self):
        response_block = re.search(
            r"catch \(error\).*?return bridge\.json\(400, \{(.*?)\}\);",
            BOOTSTRAP,
            re.DOTALL,
        )
        self.assertIsNotNone(response_block)
        self.assertNotIn("stack", response_block.group(1))


if __name__ == "__main__":
    unittest.main()
