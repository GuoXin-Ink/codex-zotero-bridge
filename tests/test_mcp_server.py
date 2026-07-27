from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import pathlib
import stat
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "plugins"
    / "codex-zotero-bridge"
    / "scripts"
    / "zotero_mcp.py"
)
SPEC = importlib.util.spec_from_file_location("zotero_mcp", MODULE_PATH)
assert SPEC and SPEC.loader
zotero_mcp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(zotero_mcp)


class FakeBridgeHandler(BaseHTTPRequestHandler):
    token = "test-token-" + "a" * 32

    def log_message(self, format, *args):
        return

    def respond(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.endswith("/status"):
            self.respond(
                200,
                {
                    "ok": True,
                    "bridge": "codex-zotero-bridge",
                    "pairingActive": True,
                },
            )
            return
        self.respond(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path.endswith("/pair"):
            if payload.get("code") != "12345678":
                self.respond(401, {"ok": False, "error": "invalid code"})
                return
            self.respond(
                200,
                {
                    "ok": True,
                    "token": self.token,
                    "bridgeVersion": "0.1.0",
                },
            )
            return
        if self.path.endswith("/op"):
            if self.headers.get("Authorization") != f"Bearer {self.token}":
                self.respond(401, {"ok": False, "error": "unauthorized"})
                return
            self.respond(200, {"ok": True, "result": payload})
            return
        self.respond(404, {"ok": False, "error": "not found"})


@contextlib.contextmanager
def fake_bridge():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeBridgeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/codex-zotero-bridge/v1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class MCPServerTests(unittest.TestCase):
    def test_initialize_and_tools(self):
        initialized = zotero_mcp.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
        self.assertEqual(
            initialized["result"]["protocolVersion"], "2025-06-18"
        )
        listed = zotero_mcp.handle_request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        )
        names = {entry["name"] for entry in listed["result"]["tools"]}
        self.assertIn("zotero_pair", names)
        self.assertIn("zotero_update_item", names)
        self.assertIn("zotero_trash_items", names)
        self.assertTrue(
            next(
                entry
                for entry in listed["result"]["tools"]
                if entry["name"] == "zotero_trash_items"
            )["annotations"]["destructiveHint"]
        )

    def test_pair_stores_token_without_returning_it(self):
        with tempfile.TemporaryDirectory() as temporary, fake_bridge() as url:
            config = pathlib.Path(temporary) / "config.json"
            environment = {
                "ZOTERO_BRIDGE_URL": url,
                "ZOTERO_BRIDGE_CONFIG": str(config),
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                result = zotero_mcp.call_tool(
                    "zotero_pair", {"code": "12345678"}
                )
            self.assertTrue(result["paired"])
            self.assertNotIn("token", result)
            stored = json.loads(config.read_text(encoding="utf-8"))
            self.assertEqual(stored["token"], FakeBridgeHandler.token)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)

    def test_authenticated_operation_translation(self):
        with tempfile.TemporaryDirectory() as temporary, fake_bridge() as url:
            config = pathlib.Path(temporary) / "config.json"
            config.write_text(
                json.dumps({"token": FakeBridgeHandler.token}),
                encoding="utf-8",
            )
            environment = {
                "ZOTERO_BRIDGE_URL": url,
                "ZOTERO_BRIDGE_CONFIG": str(config),
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                response = zotero_mcp.call_tool(
                    "zotero_update_item",
                    {
                        "key": "ABCD1234",
                        "updates": {"fields": {"publication_title": "Journal"}},
                        "dry_run": True,
                    },
                )
            payload = response["result"]
            self.assertEqual(payload["action"], "updateItem")
            self.assertTrue(payload["dryRun"])
            self.assertEqual(
                payload["updates"]["fields"]["publicationTitle"], "Journal"
            )

    def test_rejects_non_loopback_override(self):
        with mock.patch.dict(
            os.environ,
            {"ZOTERO_BRIDGE_URL": "https://example.com/bridge"},
            clear=False,
        ):
            with self.assertRaises(zotero_mcp.BridgeError):
                zotero_mcp.base_url()

    def test_wsl_fallback_after_direct_connection_failure(self):
        with mock.patch.object(
            zotero_mcp.urllib.request,
            "urlopen",
            side_effect=zotero_mcp.urllib.error.URLError("unreachable"),
        ), mock.patch.object(
            zotero_mcp, "is_wsl", return_value=True
        ), mock.patch.object(
            zotero_mcp,
            "wsl_windows_request",
            return_value=(200, b'{"ok":true,"bridge":"codex-zotero-bridge"}'),
        ) as fallback:
            response = zotero_mcp.bridge_request("status", method="GET")
        self.assertTrue(response["ok"])
        fallback.assert_called_once()

    def test_pair_code_validation(self):
        with self.assertRaises(zotero_mcp.BridgeError):
            zotero_mcp.call_tool("zotero_pair", {"code": "1234"})


if __name__ == "__main__":
    unittest.main()
