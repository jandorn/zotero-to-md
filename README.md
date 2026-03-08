# zotero-to-md

<p align="center">
  <img src="assets/zotero-to-md.png" alt="zotero-to-md" width="600">
</p>


CLI tool to sync Zotero entries from a chosen root collection to Markdown files in a configurable destination directory.

## Features

- Hybrid sync for a chosen Zotero root collection recursively (including subfolders)
- Extract content from attached PDFs and URL-only entries
- Mirror Zotero folder structure into your configured destination directory
- Save files as `<author> - <title>.md`
- Stateful sync with retries for failed items and reprocessing for changed Zotero metadata
- Status inspection, canonical resync, and stale file pruning

## Setup

1. Install dependencies:

```bash
uv sync
```

2. Create a `.env` file:

```bash
cp .env.example .env
```

3. Fill in Zotero credentials:

```env
ZOTERO_API_KEY=...
ZOTERO_USER_ID=...
```

## Usage

Sync into an absolute destination path:

```bash
uv run zotero-to-md sync \
  --root-collection "Masterarbeit" \
  --target-destination-path /absolute/path/to/output
```

Optional flags:

- `--recursive/--no-recursive` (default: recursive)
- `--dry-run`
- `--verbose`

Inspect the current sync state:

```bash
uv run zotero-to-md status \
  --root-collection "Masterarbeit" \
  --target-destination-path /absolute/path/to/output
```

Force canonical rewrite and rename for one item or all items:

```bash
uv run zotero-to-md resync \
  --root-collection "Masterarbeit" \
  --target-destination-path /absolute/path/to/output \
  --item-key ABCD1234
```

```bash
uv run zotero-to-md resync \
  --root-collection "Masterarbeit" \
  --target-destination-path /absolute/path/to/output \
  --all
```

Show stale files or delete them:

```bash
uv run zotero-to-md prune \
  --root-collection "Masterarbeit" \
  --target-destination-path /absolute/path/to/output
```

```bash
uv run zotero-to-md prune \
  --root-collection "Masterarbeit" \
  --target-destination-path /absolute/path/to/output \
  --apply
```

Output is written only to:

```text
/absolute/path/to/output/
```

State file:

```text
/absolute/path/to/output/.zotero_state.json
```

`sync` keeps existing file paths stable by default. Use `resync` when you want files renamed or moved to the current canonical Zotero-derived path.
