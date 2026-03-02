# zotero-to-md

CLI tool to sync Zotero entries from the `Masterarbeit` collection to Markdown files in a separate target repository.

## Features

- Sync Zotero `Masterarbeit` collection recursively (including subfolders)
- Extract content from attached PDFs and URL-only entries
- Mirror Zotero folder structure into `.cursor/papers/`
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

Sync into a target repo:

```bash
uv run zotero-to-md sync --target-repo-path /path/to/target-repo
```

Optional flags:

- `--root-collection` (default: `Masterarbeit`)
- `--recursive/--no-recursive` (default: recursive)
- `--dry-run`
- `--verbose`

Output is written only to:

```text
<target_repo>/.cursor/papers/
```

State file:

```text
<target_repo>/.cursor/papers/.zotero_state.json
```
