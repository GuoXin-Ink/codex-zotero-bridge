# Codex Zotero Bridge

[简体中文](README.zh-CN.md)

Codex Zotero Bridge lets a local Codex client inspect, organize, and update Zotero on the same computer. It is about Zotero library management—not LaTeX—and works independently of any writing or citation workflow.

The repository contains two cooperating components:

1. a Zotero extension (`.xpi`) that exposes a small authenticated API on Zotero's existing loopback server; and
2. a Codex plugin with a local MCP server and a safety-focused Zotero skill.

No project-operated cloud service or API key is required. The bridge is free and open source under the MIT License.

> [!IMPORTANT]
> A Zotero extension runs with access to your Zotero data. Review the source and install only releases you trust. Back up important libraries before using any automation.

## What it can do

- List and search bibliographic records
- Read complete Zotero item metadata and optional child metadata
- List libraries and collections
- Find exact DOI and normalized-title duplicate candidates
- Preview and apply metadata or creator corrections
- Create regular items and collections
- Add items to collections
- Add or remove tags
- Add child notes
- Move explicitly approved items to Zotero Trash

It intentionally cannot permanently erase records, read attachment file contents, import arbitrary local files, automatically merge duplicates, or fetch remote metadata.

## Requirements

- Zotero 8 or 9; currently tested with Zotero 9.0.6
- Python 3.9 or later in the environment where Codex runs
- A local Codex client that supports plugins and stdio MCP servers

Zotero must be running while Codex uses the bridge. Codex cloud environments cannot reach Zotero on your personal computer.

## Install

### 1. Install the Zotero extension

1. Download `codex-zotero-bridge-0.1.0.xpi` from the latest GitHub release.
2. In Zotero, open **Tools > Add-ons**.
3. Open the gear menu, choose **Install Add-on From File…**, and select the XPI.
4. Restart Zotero.

For development builds:

```bash
git clone https://github.com/GuoXin-Ink/codex-zotero-bridge.git
cd codex-zotero-bridge
python3 scripts/build_xpi.py
```

Then install the XPI from `dist/`.

### 2. Install the Codex plugin

```bash
codex plugin marketplace add GuoXin-Ink/codex-zotero-bridge
codex plugin add codex-zotero-bridge@codex-zotero-bridge
```

Restart Codex after installation. The CLI and IDE extension share the same Codex plugin configuration on a given host.

### 3. Pair Codex

1. Keep Zotero open.
2. In Zotero choose **Tools > Codex Zotero Bridge > Pair Codex…**.
3. Zotero copies a single-use 8-digit code to the clipboard. It expires after two minutes.
4. Tell Codex: `Pair Zotero using this code: 12345678`.

The permanent random token is saved locally with user-only file permissions where supported. It is not shown to the model.

## Use

Example requests:

```text
How many records are in My Library? Summarize them by item type.
Find likely duplicate Zotero records, but do not change anything.
Check the metadata for the Kaufmann paper and propose corrections.
Preview changing these titles to sentence case while preserving acronyms.
Create a collection called Reviewed and add the selected items.
Find preprint candidates and explain which ones may correspond to published records.
```

Reads require only a paired connection. For a modification, Codex should:

1. read the current records;
2. call the mutation tool in dry-run mode;
3. show the exact proposed changes and obtain your approval;
4. ask you to choose **Tools > Codex Zotero Bridge > Allow writes for 10 minutes…**;
5. apply the approved payload; and
6. read the records back to verify.

Write access starts disabled, expires after ten minutes, and resets whenever Zotero restarts. Moving records to Trash also requires an explicit bridge-side `TRASH` confirmation. You can revoke access immediately from the same Zotero menu.

## WSL

A common setup is Zotero on Windows and Codex/Python in WSL. The MCP server first tries WSL loopback and, if that is unavailable, automatically makes the same loopback request through Windows PowerShell. The bearer token is passed over standard input, not placed in process arguments.

First check:

```bash
python3 --version
powershell.exe -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'
```

Both commands should print version information. Normal users do not need to run the MCP server manually.

If Codex still cannot connect:

- confirm Zotero and the extension are running on Windows;
- update WSL and restart it with `wsl --shutdown`;
- confirm `powershell.exe` can be launched from WSL;
- optionally enable Windows-to-WSL localhost forwarding or mirrored networking;
- make sure security software is not blocking Zotero's local connector port.

Do not expose port 23119 through port forwarding, a reverse proxy, a tunnel, or a public firewall rule.

## Security

The extension binds no new listener; it registers endpoints on Zotero's local connector server. It rejects non-loopback host headers, browser `Origin` headers, non-JSON mutations, oversized requests, unauthenticated operations, closed write windows, and unconfirmed Trash operations.

The pairing and bearer-token design protects against accidental or unpaired access. It cannot protect a Zotero library after the operating-system user account itself is compromised. See [SECURITY.md](SECURITY.md), [PRIVACY.md](PRIVACY.md), and [docs/threat-model.md](docs/threat-model.md).

## Development and validation

```bash
python3 scripts/validate.py
python3 scripts/build_xpi.py
```

`validate.py` runs unit tests, static security checks, Python syntax checks, JSON validation, the Codex plugin validator when available, and the skill validator when available.

The XPI contains only:

```text
manifest.json
bootstrap.js
```

See [docs/architecture.md](docs/architecture.md) and [docs/protocol.md](docs/protocol.md) for implementation details.

## Limitations

- The Zotero side uses internal extension APIs and may require updates for future major Zotero versions.
- Version 0.1.0 supports Zotero 8 and 9 in its manifest but has only been manually tested with Zotero 9.0.6.
- Exact-title and DOI matches are only duplicate candidates.
- This project is not affiliated with or endorsed by Zotero or OpenAI.

## License

MIT
