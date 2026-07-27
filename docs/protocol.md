# Local bridge protocol

Protocol version: `v1`

Default base URL:

```text
http://127.0.0.1:23119/codex-zotero-bridge/v1
```

The protocol is an implementation detail between the bundled MCP server and Zotero extension. Third-party clients should preserve every security control described here.

## Common rules

- Only loopback `Host` values are accepted.
- Requests with an `Origin` header are rejected.
- POST bodies use `Content-Type: application/json`.
- JSON request bodies are limited to 1 MiB.
- Authenticated requests use `Authorization: Bearer <token>`.
- Tokens in URLs or custom headers are not accepted.
- Responses use `Cache-Control: no-store`.

## Status

```http
GET /status
```

Returns bridge availability, version, whether pairing is active, and remaining write-window state. It does not return Zotero version, library metadata, or secrets.

## Pairing

The user starts pairing from Zotero's Tools menu. Zotero generates an 8-digit code using the platform cryptographic random generator.

```http
POST /pair
Content-Type: application/json

{"code":"12345678"}
```

The code:

- is valid for two minutes;
- can be used once;
- is invalidated after five failed attempts;
- is held only in memory.

On success, the endpoint returns the installation's random 256-bit token once to the loopback client. The bundled MCP server removes the token from model-visible output and writes it to the local user config.

## Operations

```http
POST /op
Authorization: Bearer <token>
Content-Type: application/json

{"action":"searchItems","query":"InSAR","limit":25}
```

Only an explicit action allowlist is accepted. The extension classifies each action as read or write.

Every write action treats missing `dryRun` as `true`. An actual write therefore requires:

```json
{"action":"updateItem","key":"ABCD1234","updates":{"fields":{"title":"Example"}},"dryRun":false}
```

and a live user-enabled write window inside Zotero.

`trashItems` additionally requires:

```json
{"action":"trashItems","keys":["ABCD1234"],"dryRun":false,"confirmation":"TRASH"}
```

No operation accepts a path to a plan, database, attachment, or arbitrary local file.

## Limits

- list result: 200 items per page;
- search result: 100 items;
- duplicate groups: 500;
- mutation batch: 100 items;
- child records returned for one parent: 100;
- note body: 100,000 characters;
- request JSON: 1 MiB.

## Errors and logs

Client responses contain a short error message but no JavaScript stack trace. Zotero logs action name, dry-run state, and success or failure; it does not intentionally log bearer tokens or pairing codes.
