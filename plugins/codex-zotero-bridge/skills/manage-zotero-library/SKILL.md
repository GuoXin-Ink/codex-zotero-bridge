---
name: manage-zotero-library
description: Safely inspect and manage a local Zotero library through the Codex Zotero Bridge tools. Use when the user asks to search Zotero, audit or normalize bibliographic metadata, check fields, review duplicates, add or remove tags, organize collections, create or update records, add notes, or move confirmed records to Zotero Trash.
---

# Manage Zotero Library

Use the `zotero_*` tools to work with the user's local Zotero library. Keep the library as the source of truth and make every proposed change reviewable.

## Connect

1. Call `zotero_status`.
2. If the bridge is offline, ask the user to start Zotero and confirm the extension is enabled.
3. If it is not paired, ask the user to choose **Tools > Codex Zotero Bridge > Pair Codex…** in Zotero. Call `zotero_pair` with the one-time code they provide.
4. Never ask for, print, or read the permanent token or bridge config file.

## Read and audit

- Use `zotero_list_libraries` before operating on a group library.
- Use `zotero_search_items` for targeted requests and `zotero_list_items` with pagination for full-library audits.
- Preserve Zotero item keys in findings and proposed changes.
- Treat duplicate matches as candidates. Compare creators, dates, publication, DOI, attachments, notes, tags, and collections before recommending any item for Trash.
- Do not infer missing metadata when a reliable source is unavailable. Clearly label uncertainty and leave the field unchanged.
- For large audits, return findings in manageable batches and maintain a deterministic change list keyed by Zotero item key.

## Change workflow

Follow this sequence for every mutation:

1. Read the current item immediately before proposing a change.
2. Call the relevant mutation tool with `dry_run=true`.
3. Summarize the exact keys and before/after values. Separate supported corrections from judgment calls.
4. Obtain explicit user approval for that exact batch.
5. Ask the user to choose **Tools > Codex Zotero Bridge > Allow writes for 10 minutes…**.
6. Reuse the reviewed payload with `dry_run=false`.
7. Read back the affected records and report the verified result.

Approval for one batch does not authorize later batches. If the write window expires, ask the user to re-enable it; do not weaken or bypass the bridge.

## Destructive changes

Moving items to Trash is destructive even though Zotero normally allows recovery.

- Always preview with `zotero_trash_items` and `dry_run=true`.
- Show the exact item keys and titles.
- Require explicit approval specifically to move those records to Trash.
- Only then call with `dry_run=false` and `confirmation="TRASH"`.
- Never permanently erase items, attachments, notes, or collections. The bridge deliberately exposes no permanent-delete or automatic-merge tool.

## Metadata conventions

- Preserve intentional capitalization for acronyms, proper nouns, chemical formulas, place names, and product or sensor names.
- Normalize DOI values to the DOI itself when editing, without a `doi:` prefix or resolver URL.
- Use Zotero creator objects with a valid `creatorType`; preserve creator order.
- Do not replace all tags or collection memberships unless the user approved the complete replacement. Prefer the dedicated add/remove tools for incremental changes.
- Store evidence and unresolved questions in the report rather than inventing field values.

Read [safety.md](references/safety.md) before a batch metadata cleanup, duplicate cleanup, or any request involving deletion.
