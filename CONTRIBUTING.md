# Contributing

Issues and pull requests are welcome. Keep changes focused, add tests for behavior, and do not include real Zotero libraries, database files, exported notes, tokens, pairing codes, user names, or local paths.

## Development

Requirements:

- Python 3.9 or later
- Zotero 8 or 9 for manual extension testing
- Codex CLI or IDE extension for plugin integration testing

Run:

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate.py
python3 scripts/build_xpi.py
```

Use a disposable Zotero profile and a synthetic library for mutation tests. Exercise both denied and allowed write paths, restart Zotero to confirm writes return to disabled, and rotate the token after testing.

## Pull request checklist

- No hard-coded secrets, private paths, or library data
- Mutations still default to dry-run
- New destructive behavior has explicit bridge-side enforcement
- README and protocol documentation reflect tool changes
- Validation and tests pass
- Version changed consistently when release behavior changes
