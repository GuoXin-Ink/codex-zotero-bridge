# Threat model

## Assets

- Zotero bibliographic metadata
- Notes and attachment metadata
- Collection and tag organization
- Group-library membership and metadata
- The permanent connection token

## Trusted components

- The user's Zotero installation and profile
- The installed release of this Zotero extension
- The installed release of the Codex plugin
- The user's local operating-system account
- The user's explicit actions in Zotero's Tools menu

## Threats and mitigations

| Threat | Mitigation |
|---|---|
| A website sends requests to Zotero's local connector | Reject every request with an `Origin` header; accept JSON POST only; do not send CORS headers |
| DNS rebinding or a non-loopback Host | Accept only `127.0.0.1`, `localhost`, or `[::1]` Host values |
| A copied public XPI contains a shared secret | Generate a fresh 256-bit token per Zotero profile; no default token exists in source or artifacts |
| A pairing code is guessed | Eight random digits, two-minute lifetime, five attempts, single use, user-initiated window |
| A token leaks through logs or chat | Return it only from `/pair`; MCP strips it before tool output and stores it in a restricted local config |
| A WSL fallback exposes the token in the process list | Send request data and the token to a fixed PowerShell program over standard input; never interpolate them into command arguments |
| Codex changes records without review | All mutations default to dry-run; Zotero independently requires a temporary user-confirmed write window |
| Broad or permanent deletion | Only move regular items to Zotero Trash; require exact keys plus `confirmation="TRASH"`; expose no erase operation |
| A plan references arbitrary local files | No plan-path, attachment-content, import, or arbitrary file-read operation exists |
| Oversized or malformed input causes resource pressure | Enforce 1 MiB request and bounded result or mutation sizes |
| Internal exception leaks implementation details | Return a bounded public message; keep stack details in local Zotero logs |
| Write access remains open | Ten-minute in-memory expiry; reset on Zotero restart; manual disable and token rotation menu actions |

## Residual risks

- Malware running as the same operating-system user can often read user config files, control local applications, or access Zotero directly.
- Zotero's connector server and extension APIs are upstream trust dependencies.
- The short pairing code is not intended to withstand an attacker who can observe the user's screen or clipboard.
- A model can propose incorrect metadata. Dry-run and approval reduce impact but cannot establish bibliographic truth.
- Attachment child metadata may reveal local file names or paths when the user asks to read children.

## Out of scope

- Protecting a compromised operating-system account
- Remote access to Zotero
- Codex cloud-to-desktop tunneling
- Permanent deletion
- Automatic duplicate merging
- Reading PDF or attachment contents
- Remote bibliographic lookup
