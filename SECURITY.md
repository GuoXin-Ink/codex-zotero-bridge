# Security policy

## Supported versions

Security fixes are provided for the latest release.

## Report a vulnerability

Please use GitHub's private vulnerability reporting feature for this repository. Do not open a public issue containing an exploit, pairing code, permanent token, private Zotero metadata, local file path, or bridge config.

Include the affected version, operating system, Zotero version, Codex surface, reproduction steps, and expected impact. Use a new test library rather than a real research library whenever possible.

## Security model

- The Zotero extension uses Zotero's existing loopback connector server and does not open a public network listener.
- Every installation generates its own random 256-bit bearer token.
- Pairing requires a single-use 8-digit code shown inside Zotero and expires after two minutes or five failed attempts.
- The permanent token is stored by the local MCP server in a user-only config file.
- Browser-originated requests are rejected. Query-string and custom-header authentication are not supported.
- Writes are disabled after startup and require a user-confirmed 10-minute window in Zotero.
- Mutation tools default to dry-run. Moving records to Trash requires an additional literal confirmation.
- The bridge exposes no permanent erase, arbitrary local file read, automatic merge, or remote network fetch operation.

The bearer token protects against unpaired local processes, but a process already running as the same operating-system user may be able to read user files or control Zotero. This project does not claim to defend a compromised user account or operating system.
