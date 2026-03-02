# zotero-to-md

<p align="center">
  <img src="assets/zotero-to-md.png" alt="zotero-to-md" width="600">
</p>


CLI tool to sync Zotero entries from a chosen root collection to Markdown files in a configurable destination directory.

## Features

- Sync a chosen Zotero root collection recursively (including subfolders)
- Extract content from attached PDFs and URL-only entries
- Mirror Zotero folder structure into your configured destination directory
- Save files as `<author> - <title>.md`
- Stateful incremental sync: after first run, only new Zotero items are processed

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

Output is written only to:

```text
/absolute/path/to/output/
```

State file:

```text
/absolute/path/to/output/.zotero_state.json
```
