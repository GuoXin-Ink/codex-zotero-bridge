#!/usr/bin/env python3
"""Zero-dependency stdio MCP server for Codex Zotero Bridge."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from typing import Any


SERVER_NAME = "codex-zotero-bridge"
SERVER_VERSION = "0.1.0"
PROTOCOL_VERSIONS = {"2024-11-05", "2025-03-26", "2025-06-18"}
DEFAULT_PROTOCOL_VERSION = "2025-06-18"
DEFAULT_BASE_URL = "http://127.0.0.1:23119/codex-zotero-bridge/v1"
REQUEST_TIMEOUT_SECONDS = 30


class BridgeError(RuntimeError):
    """An expected bridge or configuration error safe to show to the user."""


def config_path() -> pathlib.Path:
    override = os.environ.get("ZOTERO_BRIDGE_CONFIG")
    if override:
        return pathlib.Path(override).expanduser()
    if sys.platform == "win32":
        root = pathlib.Path(os.environ.get("APPDATA", pathlib.Path.home()))
        return root / "codex-zotero-bridge" / "config.json"
    root = pathlib.Path(
        os.environ.get("XDG_CONFIG_HOME", pathlib.Path.home() / ".config")
    )
    return root / "codex-zotero-bridge" / "config.json"


def base_url() -> str:
    value = os.environ.get("ZOTERO_BRIDGE_URL", DEFAULT_BASE_URL).rstrip("/")
    if not (
        value.startswith("http://127.0.0.1:")
        or value.startswith("http://localhost:")
        or value.startswith("http://[::1]:")
    ):
        raise BridgeError(
            "ZOTERO_BRIDGE_URL must use plain HTTP on 127.0.0.1, localhost, or [::1]."
        )
    return value


def is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in pathlib.Path("/proc/sys/kernel/osrelease").read_text(
            encoding="utf-8"
        ).lower()
    except OSError:
        return False


POWERSHELL_REQUEST_SCRIPT = r"""
$ErrorActionPreference = "Stop"
try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $headers = @{
        "Accept" = "application/json"
        "User-Agent" = "codex-zotero-bridge/0.1.0"
    }
    if ($request.token) {
        $headers["Authorization"] = "Bearer " + [string]$request.token
    }
    $parameters = @{
        Uri = [string]$request.url
        Method = [string]$request.method
        Headers = $headers
        UseBasicParsing = $true
        TimeoutSec = 30
    }
    if ($null -ne $request.payload) {
        $parameters["ContentType"] = "application/json"
        $parameters["Body"] = $request.payload | ConvertTo-Json -Depth 100 -Compress
    }
    $response = Invoke-WebRequest @parameters
    @{
        status = [int]$response.StatusCode
        body = [string]$response.Content
        error = $null
    } | ConvertTo-Json -Compress
}
catch {
    $status = 0
    $body = ""
    if ($null -ne $_.Exception.Response) {
        try {
            $status = [int]$_.Exception.Response.StatusCode
            $stream = $_.Exception.Response.GetResponseStream()
            if ($null -ne $stream) {
                $reader = New-Object System.IO.StreamReader($stream)
                $body = $reader.ReadToEnd()
                $reader.Dispose()
            }
        }
        catch {}
    }
    @{
        status = $status
        body = $body
        error = [string]$_.Exception.Message
    } | ConvertTo-Json -Compress
}
"""


def wsl_windows_request(
    url: str,
    *,
    method: str,
    payload: dict[str, Any] | None,
    token: str | None,
) -> tuple[int, bytes]:
    """Call Windows loopback without putting the bearer token in process args."""

    request_data = json.dumps(
        {
            "url": url,
            "method": method,
            "payload": payload,
            "token": token,
        },
        ensure_ascii=False,
    )
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                POWERSHELL_REQUEST_SCRIPT,
            ],
            input=request_data,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=REQUEST_TIMEOUT_SECONDS + 5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BridgeError(
            "Could not invoke Windows PowerShell for the WSL-to-Zotero fallback."
        ) from exc
    output_lines = [
        line.strip() for line in completed.stdout.splitlines() if line.strip()
    ]
    if not output_lines:
        raise BridgeError(
            "Windows PowerShell could not reach Zotero's loopback server."
        )
    try:
        result = json.loads(output_lines[-1].lstrip("\ufeff"))
        status = int(result.get("status") or 0)
        body = str(result.get("body") or "").encode("utf-8")
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise BridgeError(
            "Windows PowerShell returned an invalid bridge response."
        ) from exc
    if status <= 0:
        raise BridgeError(
            "Windows could not reach Zotero at 127.0.0.1:23119. Start Zotero "
            "and make sure its local connector server is enabled."
        )
    return status, body


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BridgeError(f"Could not read bridge config at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise BridgeError(f"Bridge config at {path} must contain a JSON object.")
    return data


def save_config(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=".config-", suffix=".tmp", dir=str(path.parent)
    )
    temporary_path = pathlib.Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def bridge_request(
    endpoint: str,
    *,
    method: str = "POST",
    payload: dict[str, Any] | None = None,
    authenticated: bool = False,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "User-Agent": f"{SERVER_NAME}/{SERVER_VERSION}",
    }
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    token: str | None = None
    if authenticated:
        token = load_config().get("token")
        if not isinstance(token, str) or not token:
            raise BridgeError(
                "Zotero is not paired. In Zotero choose Tools > Codex Zotero Bridge "
                "> Pair Codex, then call zotero_pair with the one-time code."
            )
        headers["Authorization"] = f"Bearer {token}"

    url = f"{base_url()}/{endpoint.lstrip('/')}"
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )
    status = 200
    try:
        with urllib.request.urlopen(
            request, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            status = int(response.status)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            details = json.loads(raw.decode("utf-8"))
            message = details.get("error") or f"HTTP {exc.code}"
        except (UnicodeDecodeError, json.JSONDecodeError):
            message = f"HTTP {exc.code}"
        raise BridgeError(str(message)) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if not is_wsl():
            raise BridgeError(
                "Could not reach Zotero at 127.0.0.1:23119. Start Zotero, make "
                "sure the Codex Zotero Bridge extension is enabled, and retry."
            ) from exc
        status, raw = wsl_windows_request(
            url, method=method, payload=payload, token=token
        )

    if status >= 400:
        try:
            details = json.loads(raw.decode("utf-8"))
            message = details.get("error") or f"HTTP {status}"
        except (UnicodeDecodeError, json.JSONDecodeError):
            message = f"HTTP {status}"
        raise BridgeError(str(message))

    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError("Zotero returned an invalid response.") from exc
    if not isinstance(result, dict):
        raise BridgeError("Zotero returned an unexpected response.")
    if result.get("ok") is False:
        raise BridgeError(str(result.get("error") or "Zotero bridge request failed."))
    return result


def object_schema(
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
    *,
    additional_properties: bool = False,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": additional_properties,
    }
    if required:
        schema["required"] = required
    return schema


LIBRARY_ID = {
    "type": "integer",
    "minimum": 1,
    "description": "Zotero library ID. Omit to use My Library.",
}
ITEM_KEY = {
    "type": "string",
    "minLength": 1,
    "description": "The 8-character Zotero item key returned by the bridge.",
}
ITEM_KEYS = {
    "type": "array",
    "minItems": 1,
    "maxItems": 100,
    "uniqueItems": True,
    "items": {"type": "string", "minLength": 1},
}
DRY_RUN = {
    "type": "boolean",
    "default": True,
    "description": (
        "Keep true to preview without modifying Zotero. Set false only after the "
        "user approves the preview and enables writes in Zotero."
    ),
}
CREATORS = {
    "type": "array",
    "items": object_schema(
        {
            "creatorType": {"type": "string"},
            "firstName": {"type": "string"},
            "lastName": {"type": "string"},
            "name": {"type": "string"},
        },
        ["creatorType"],
    ),
}
TAGS = {
    "type": "array",
    "items": {
        "oneOf": [
            {"type": "string"},
            object_schema(
                {"tag": {"type": "string"}, "type": {"type": "integer"}},
                ["tag"],
            ),
        ]
    },
}
UPDATES = object_schema(
    {
        "fields": {
            "type": "object",
            "description": (
                "Zotero metadata fields to set, such as title, DOI, date, "
                "publicationTitle, volume, issue, pages, url, or abstractNote."
            ),
            "additionalProperties": {
                "type": ["string", "number", "boolean", "null"]
            },
        },
        "creators": CREATORS,
        "tags": TAGS,
        "collections": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Replace collection membership using collection keys.",
        },
    }
)


def tool(
    name: str,
    title: str,
    description: str,
    input_schema: dict[str, Any],
    *,
    read_only: bool,
    destructive: bool = False,
    idempotent: bool = False,
) -> dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": input_schema,
        "annotations": {
            "readOnlyHint": read_only,
            "destructiveHint": destructive,
            "idempotentHint": idempotent,
            "openWorldHint": False,
        },
    }


TOOLS = [
    tool(
        "zotero_status",
        "Check Zotero bridge",
        (
            "Check whether the local Zotero bridge is online, paired, and currently "
            "allowing writes. This does not read library records."
        ),
        object_schema(),
        read_only=True,
        idempotent=True,
    ),
    tool(
        "zotero_pair",
        "Pair with Zotero",
        (
            "Exchange the short-lived 8-digit code shown by Zotero for a local "
            "connection token. The permanent token is stored in a user-only config "
            "file and is never returned to the model."
        ),
        object_schema(
            {
                "code": {
                    "type": "string",
                    "pattern": "^[0-9]{8}$",
                    "description": "One-time code from Zotero's Tools menu.",
                }
            },
            ["code"],
        ),
        read_only=False,
        idempotent=False,
    ),
    tool(
        "zotero_list_libraries",
        "List Zotero libraries",
        "List local Zotero libraries and their numeric IDs and editability.",
        object_schema(),
        read_only=True,
        idempotent=True,
    ),
    tool(
        "zotero_list_items",
        "List Zotero items",
        (
            "Page through regular bibliographic items in a Zotero library. Use this "
            "for audits and counts; continue while hasMore is true."
        ),
        object_schema(
            {
                "library_id": LIBRARY_ID,
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 200,
                    "default": 50,
                },
                "include_data": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include complete Zotero item JSON.",
                },
            }
        ),
        read_only=True,
        idempotent=True,
    ),
    tool(
        "zotero_search_items",
        "Search Zotero items",
        (
            "Search local bibliographic metadata by title, creator, DOI, date, "
            "publication, tag, type, or Zotero key."
        ),
        object_schema(
            {
                "query": {"type": "string", "minLength": 1},
                "library_id": LIBRARY_ID,
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 25,
                },
                "include_data": {"type": "boolean", "default": True},
            },
            ["query"],
        ),
        read_only=True,
        idempotent=True,
    ),
    tool(
        "zotero_get_item",
        "Get a Zotero item",
        "Read one item and optionally its attachment/note child metadata by Zotero key.",
        object_schema(
            {
                "key": ITEM_KEY,
                "library_id": LIBRARY_ID,
                "include_children": {"type": "boolean", "default": False},
            },
            ["key"],
        ),
        read_only=True,
        idempotent=True,
    ),
    tool(
        "zotero_list_collections",
        "List Zotero collections",
        "List non-deleted collections and their parent collection keys.",
        object_schema({"library_id": LIBRARY_ID}),
        read_only=True,
        idempotent=True,
    ),
    tool(
        "zotero_find_potential_duplicates",
        "Find potential duplicate items",
        (
            "Find exact DOI matches and exact normalized-title matches. Results are "
            "candidates for human review; this tool never merges or deletes."
        ),
        object_schema(
            {
                "library_id": LIBRARY_ID,
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 500,
                    "default": 100,
                },
            }
        ),
        read_only=True,
        idempotent=True,
    ),
    tool(
        "zotero_create_item",
        "Create a Zotero item",
        (
            "Preview or create one regular bibliographic item. dry_run defaults to "
            "true; actual creation requires Zotero's temporary write window."
        ),
        object_schema(
            {
                "data": {
                    "type": "object",
                    "description": (
                        "Zotero item JSON containing itemType and metadata fields."
                    ),
                    "properties": {"itemType": {"type": "string"}},
                    "required": ["itemType"],
                    "additionalProperties": True,
                },
                "library_id": LIBRARY_ID,
                "dry_run": DRY_RUN,
            },
            ["data"],
        ),
        read_only=False,
        idempotent=False,
    ),
    tool(
        "zotero_update_item",
        "Update a Zotero item",
        (
            "Preview or update fields, creators, tags, or collection membership for "
            "one regular item. Do not change data unless supported by reliable "
            "metadata evidence."
        ),
        object_schema(
            {
                "key": ITEM_KEY,
                "updates": UPDATES,
                "library_id": LIBRARY_ID,
                "dry_run": DRY_RUN,
            },
            ["key", "updates"],
        ),
        read_only=False,
        idempotent=True,
    ),
    tool(
        "zotero_batch_update_items",
        "Batch update Zotero items",
        (
            "Preview or update up to 100 items in one call. First submit the exact "
            "same changes with dry_run=true and summarize the diff for the user."
        ),
        object_schema(
            {
                "changes": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "items": object_schema(
                        {"key": ITEM_KEY, "updates": UPDATES},
                        ["key", "updates"],
                    ),
                },
                "library_id": LIBRARY_ID,
                "dry_run": DRY_RUN,
            },
            ["changes"],
        ),
        read_only=False,
        idempotent=True,
    ),
    tool(
        "zotero_create_collection",
        "Create a Zotero collection",
        "Preview or create a collection, optionally below a parent collection.",
        object_schema(
            {
                "name": {"type": "string", "minLength": 1},
                "parent_key": {"type": "string"},
                "library_id": LIBRARY_ID,
                "dry_run": DRY_RUN,
            },
            ["name"],
        ),
        read_only=False,
        idempotent=False,
    ),
    tool(
        "zotero_add_to_collection",
        "Add items to a Zotero collection",
        "Preview or add up to 100 regular items to an existing collection.",
        object_schema(
            {
                "keys": ITEM_KEYS,
                "collection_key": {"type": "string", "minLength": 1},
                "library_id": LIBRARY_ID,
                "dry_run": DRY_RUN,
            },
            ["keys", "collection_key"],
        ),
        read_only=False,
        idempotent=True,
    ),
    tool(
        "zotero_add_tags",
        "Add Zotero tags",
        "Preview or add manual tags to up to 100 items.",
        object_schema(
            {
                "keys": ITEM_KEYS,
                "tags": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "items": {"type": "string", "minLength": 1},
                },
                "library_id": LIBRARY_ID,
                "dry_run": DRY_RUN,
            },
            ["keys", "tags"],
        ),
        read_only=False,
        idempotent=True,
    ),
    tool(
        "zotero_remove_tags",
        "Remove Zotero tags",
        "Preview or remove named tags from up to 100 items.",
        object_schema(
            {
                "keys": ITEM_KEYS,
                "tags": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "items": {"type": "string", "minLength": 1},
                },
                "library_id": LIBRARY_ID,
                "dry_run": DRY_RUN,
            },
            ["keys", "tags"],
        ),
        read_only=False,
        idempotent=True,
    ),
    tool(
        "zotero_add_note",
        "Add a Zotero child note",
        "Preview or add a child note to one regular item.",
        object_schema(
            {
                "key": ITEM_KEY,
                "note_html": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 100000,
                },
                "library_id": LIBRARY_ID,
                "dry_run": DRY_RUN,
            },
            ["key", "note_html"],
        ),
        read_only=False,
        idempotent=False,
    ),
    tool(
        "zotero_trash_items",
        "Move Zotero items to Trash",
        (
            "Preview or move up to 100 regular items to Zotero Trash. Never call "
            "with dry_run=false without explicit user approval of the exact keys. "
            "Actual execution also requires confirmation='TRASH'."
        ),
        object_schema(
            {
                "keys": ITEM_KEYS,
                "library_id": LIBRARY_ID,
                "dry_run": DRY_RUN,
                "confirmation": {
                    "type": "string",
                    "enum": ["TRASH"],
                    "description": (
                        "Required only for actual execution after explicit approval."
                    ),
                },
            },
            ["keys"],
        ),
        read_only=False,
        destructive=True,
        idempotent=True,
    ),
]


def snake_to_camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest)


TOOL_ACTIONS = {
    "zotero_list_libraries": "listLibraries",
    "zotero_list_items": "listItems",
    "zotero_search_items": "searchItems",
    "zotero_get_item": "getItem",
    "zotero_list_collections": "listCollections",
    "zotero_find_potential_duplicates": "findPotentialDuplicates",
    "zotero_create_item": "createItem",
    "zotero_update_item": "updateItem",
    "zotero_batch_update_items": "batchUpdateItems",
    "zotero_create_collection": "createCollection",
    "zotero_add_to_collection": "addToCollection",
    "zotero_add_tags": "addTags",
    "zotero_remove_tags": "removeTags",
    "zotero_add_note": "addNote",
    "zotero_trash_items": "trashItems",
}


def camelize_arguments(value: Any) -> Any:
    if isinstance(value, list):
        return [camelize_arguments(entry) for entry in value]
    if isinstance(value, dict):
        return {
            snake_to_camel(key): camelize_arguments(entry)
            for key, entry in value.items()
        }
    return value


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "zotero_status":
        return bridge_request("status", method="GET")
    if name == "zotero_pair":
        code = arguments.get("code")
        if not isinstance(code, str) or len(code) != 8 or not code.isdigit():
            raise BridgeError("Pairing code must contain exactly 8 digits.")
        response = bridge_request("pair", payload={"code": code})
        token = response.pop("token", None)
        if not isinstance(token, str) or len(token) < 32:
            raise BridgeError("Zotero did not return a valid connection token.")
        save_config(
            {
                "token": token,
                "base_url": base_url(),
                "bridge_version": response.get("bridgeVersion", SERVER_VERSION),
            }
        )
        return {
            "ok": True,
            "paired": True,
            "configPath": str(config_path()),
            "message": "Paired successfully. The permanent token was stored locally.",
        }
    action = TOOL_ACTIONS.get(name)
    if not action:
        raise BridgeError(f"Unknown tool: {name}")
    payload = camelize_arguments(arguments)
    payload["action"] = action
    return bridge_request("op", payload=payload, authenticated=True)


def tool_result(data: dict[str, Any], *, error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(data, ensure_ascii=False, indent=2),
            }
        ],
        "structuredContent": data,
        "isError": error,
    }


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if request_id is None:
        return None

    if method == "initialize":
        requested = params.get("protocolVersion")
        protocol = (
            requested if requested in PROTOCOL_VERSIONS else DEFAULT_PROTOCOL_VERSION
        )
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Zotero reads are allowed after local pairing. For any mutation, "
                    "first call the same tool with dry_run=true, show the exact proposed "
                    "change, obtain explicit user approval, and ask the user to enable "
                    "the 10-minute write window in Zotero. Never trash items without "
                    "approval of the exact keys and confirmation='TRASH'."
                ),
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {"tools": TOOLS},
        }
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not isinstance(arguments, dict):
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": "Invalid tool call parameters."},
            }
        try:
            result = call_tool(name, arguments)
            payload = tool_result(result)
        except BridgeError as exc:
            payload = tool_result({"ok": False, "error": str(exc)}, error=True)
        except Exception:
            payload = tool_result(
                {
                    "ok": False,
                    "error": (
                        "Unexpected local bridge error. Check the MCP server logs "
                        "without sharing tokens or config files."
                    ),
                },
                error=True,
            )
        return {"jsonrpc": "2.0", "id": request_id, "result": payload}
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": "Method not found."},
    }


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("message is not an object")
            response = handle_request(message)
        except (json.JSONDecodeError, ValueError):
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error."},
            }
        if response is not None:
            sys.stdout.write(
                json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
