from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from zotero_to_md.models import ExtractionResult, ZoteroItem

INVALID_PATH_CHARS_PATTERN = re.compile(r'[\\/:*?"<>|]+')
WHITESPACE_PATTERN = re.compile(r"\s+")


def sanitize_path_component(value: str) -> str:
    candidate = INVALID_PATH_CHARS_PATTERN.sub("-", value.strip())
    candidate = WHITESPACE_PATTERN.sub(" ", candidate).strip()
    candidate = candidate.strip(".")
    return candidate or "untitled"


def select_primary_author(authors: list[str]) -> str:
    if not authors:
        return "unknown-author"
    return sanitize_path_component(authors[0]) or "unknown-author"


def resolve_output_path(base_dir: Path, *, collection_path: str, title: str, authors: list[str]) -> Path:
    directory = base_dir
    for component in Path(collection_path).parts:
        if component in {"", "."}:
            continue
        directory = directory / sanitize_path_component(component)
    directory.mkdir(parents=True, exist_ok=True)

    author = select_primary_author(authors)
    safe_title = sanitize_path_component(title) or "untitled"
    base_name = f"{author} - {safe_title}"
    output = directory / f"{base_name}.md"

    suffix = 2
    while output.exists():
        output = directory / f"{base_name}-{suffix}.md"
        suffix += 1
    return output


def render_markdown(
    *,
    item: ZoteroItem,
    extraction: ExtractionResult,
    processed_at: str,
    source_url: str | None,
    collection_path: str,
) -> str:
    frontmatter: dict[str, Any] = {
        "zotero_item_key": item.item_key,
        "title": item.title,
        "authors": item.authors,
        "year": item.year,
        "source_kind": extraction.source_kind,
        "source_url": source_url,
        "collection_path": collection_path,
        "processed_at": processed_at,
        "status": extraction.status,
    }
    frontmatter_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=False).strip()
    body = extraction.text.strip()
    return f"---\n{frontmatter_yaml}\n---\n\n{body}\n"

