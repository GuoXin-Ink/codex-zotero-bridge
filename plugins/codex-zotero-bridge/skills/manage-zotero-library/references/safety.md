# Zotero Safety Reference

## Trust boundaries

- Zotero runs a loopback HTTP endpoint. Treat every browser page, local process, and Codex tool call as untrusted until the bridge authenticates it.
- Pairing codes are short-lived and single-use. Permanent tokens belong only in the bridge's user-only config file.
- Library metadata may contain private research topics, notes, file names, and group membership. Return only the records needed for the current request.

## Audit checklist

For each proposed metadata correction:

1. Identify the item by library ID and Zotero key.
2. Record the current value.
3. Record the proposed value.
4. State the supporting evidence or rule.
5. State confidence and any ambiguity.
6. Preview with `dry_run=true`.
7. Apply only the approved subset.
8. Read the item back and verify.

Do not treat visual formatting differences alone as evidence of incorrect stored metadata. Citation styles may transform capitalization, names, dates, and page ranges during rendering.

## Duplicate review

The duplicate finder reports exact normalized DOI or title matches, not proof of duplication. Before moving a candidate to Trash, compare:

- item type;
- full title and subtitle;
- all creators and their order;
- publication and date;
- DOI, ISBN, PMID, arXiv ID, or other identifiers;
- abstract and language;
- child notes and attachments;
- tags and collection memberships.

Prefer keeping the most complete record. The bridge does not auto-merge child items or permanently delete anything.

## Preprints

Do not remove a preprint merely because a published version exists. Confirm that both records describe the same work, preserve useful attachments and notes, and ask whether the user's library policy prefers merging, retaining both, or moving one record to Trash.

## Batch limits

Keep change batches small enough for meaningful review. The bridge enforces a maximum of 100 records per mutation call, but smaller batches are usually safer for heterogeneous corrections.
