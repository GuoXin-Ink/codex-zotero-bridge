# Architecture

```text
Codex
  │  stdio / JSON-RPC (MCP)
  ▼
Bundled Python MCP server
  │  HTTP + bearer token, loopback only
  ▼
Zotero connector server on 127.0.0.1:23119
  │
  ▼
Codex Zotero Bridge extension
  │  Zotero internal item/collection APIs
  ▼
Selected local Zotero library
```

## Zotero extension

`zotero-extension/bootstrap.js` is a restartless Zotero extension. It registers three versioned paths on Zotero's existing connector HTTP server:

- `GET /codex-zotero-bridge/v1/status`
- `POST /codex-zotero-bridge/v1/pair`
- `POST /codex-zotero-bridge/v1/op`

It also adds a **Codex Zotero Bridge** submenu under Zotero's **Tools** menu. The menu is the trusted user-presence channel for starting pairing, temporarily enabling writes, disabling writes, inspecting status, and rotating the token.

The extension stores only the permanent random token in Zotero preferences. Pairing state and write authorization are memory-only, so both disappear when Zotero exits.

## MCP server

`plugins/codex-zotero-bridge/scripts/zotero_mcp.py` is a zero-dependency Python stdio MCP server. It:

- negotiates MCP lifecycle versions;
- publishes typed Zotero tools;
- translates snake-case tool inputs to the extension's JSON operations;
- stores the paired token in a user-only config file;
- sends authenticated requests only to a loopback URL;
- uses a standard-input-only Windows PowerShell fallback when Codex runs in WSL and Zotero runs on Windows;
- never returns the permanent token as model-visible tool output.

The MCP server cannot bypass write authorization because the Zotero extension independently enforces the write window, dry-run state, action allowlist, request limits, and Trash confirmation.

## Codex skill

The bundled `manage-zotero-library` skill teaches Codex to:

- pair without exposing a permanent secret;
- page through audits;
- distinguish duplicate candidates from proven duplicates;
- preview each mutation;
- obtain approval for an exact batch;
- verify applied changes;
- use stricter approval for Trash.

The skill is defense in depth. Correctness and authorization are still enforced in code where possible.

## Distribution

The GitHub repository is a repo-local Codex marketplace. Codex installs the plugin folder into its plugin cache. GitHub Releases distribute the separately built Zotero XPI.

The XPI build is deterministic for identical source files and contains only `manifest.json` and `bootstrap.js`.
