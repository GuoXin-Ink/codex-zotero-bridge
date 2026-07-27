# Privacy

Codex Zotero Bridge is local software. The Zotero extension and bundled MCP server do not send Zotero records, pairing codes, tokens, or usage telemetry to a project-operated service.

When you ask Codex to inspect Zotero, the selected metadata is returned to the Codex client as tool output and is then handled according to the terms and privacy settings of the Codex product and model provider you use. This project does not control that processing.

The bridge stores one permanent connection token locally:

- Linux/WSL: `${XDG_CONFIG_HOME:-~/.config}/codex-zotero-bridge/config.json`
- macOS: `~/.config/codex-zotero-bridge/config.json`
- Windows: `%APPDATA%\codex-zotero-bridge\config.json`

On POSIX systems, the directory and file are created with user-only permissions where the platform permits. You can revoke the token from **Tools > Codex Zotero Bridge > Disconnect all clients and rotate token…**. Removing the local config file disconnects that Codex environment.

The bridge does not expose attachment file contents. Child attachment metadata may include a local path when the user explicitly asks to include child records.
