from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

import yaml

from zotero_to_md.models import ExtractionResult, ZoteroItem

INVALID_PATH_CHARS_PATTERN = re.compile(r'[\\/:*?"<>|]+')
WHITESPACE_PATTERN = re.compile(r"\s+")
MAX_PATH_COMPONENT_LENGTH = 240
WINDOWS_MAX_PATH_LENGTH = 240
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


def sanitize_path_component(value: str) -> str:
    candidate = INVALID_PATH_CHARS_PATTERN.sub("-", value.strip())
    candidate = WHITESPACE_PATTERN.sub(" ", candidate).strip()
    candidate = candidate.strip(" .")
    candidate = _truncate_component(candidate, MAX_PATH_COMPONENT_LENGTH)
    if candidate.upper() in WINDOWS_RESERVED_NAMES:
        candidate = f"{candidate}-file"
    return candidate or "untitled"


def select_primary_author(authors: list[str]) -> str:
    if not authors:
        return "unknown-author"
    return sanitize_path_component(authors[0]) or "unknown-author"


def resolve_output_path(
    base_dir: Path,
    *,
    collection_path: str,
    title: str,
    authors: list[str],
    allow_existing_path: Path | None = None,
) -> Path:
    directory = base_dir
    for component in Path(collection_path).parts:
        if component in {"", "."}:
            continue
        directory = directory / sanitize_path_component(component)
    directory.mkdir(parents=True, exist_ok=True)

    author = select_primary_author(authors)
    safe_title = sanitize_path_component(title) or "untitled"
    base_name = f"{author} - {safe_title}"
    output = _build_output_path(directory, base_name)

    suffix = 2
    while output.exists() and output != allow_existing_path:
        output = _build_output_path(directory, base_name, suffix=suffix)
        suffix += 1
    return output


def _build_output_path(directory: Path, base_name: str, *, suffix: int | None = None) -> Path:
    suffix_text = "" if suffix is None else f"-{suffix}"
    file_stem = _fit_file_stem(directory, base_name, suffix_text=suffix_text, extension=".md")
    output = directory / f"{file_stem}{suffix_text}.md"
    if _running_on_windows() and len(str(output)) > WINDOWS_MAX_PATH_LENGTH:
        raise ValueError(
            "Output path is too long for Windows. Choose a shorter target path or collection path."
        )
    return output


def _fit_file_stem(directory: Path, base_name: str, *, suffix_text: str, extension: str) -> str:
    max_stem_length = MAX_PATH_COMPONENT_LENGTH - len(suffix_text) - len(extension)
    if _running_on_windows():
        available = WINDOWS_MAX_PATH_LENGTH - len(str(directory)) - 1 - len(suffix_text) - len(extension)
        max_stem_length = min(max_stem_length, available)
    return _truncate_component(base_name, max(1, max_stem_length))


def _truncate_component(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    if max_length <= 3:
        return value[:max_length]
    truncated = value[: max_length - 3].rstrip(" .-")
    if not truncated:
        truncated = value[: max_length - 3]
    return f"{truncated}..."


def _running_on_windows() -> bool:
    return os.name == "nt"


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
        "item_type": item.item_type,
        "tags": item.tags,
        "abstract": item.abstract,
        "doi": item.doi,
        "zotero_library_key": item.zotero_library_key,
        "source_kind": extraction.source_kind,
        "source_url": source_url,
        "collection_path": collection_path,
        "processed_at": processed_at,
        "status": extraction.status,
        "fingerprint": item_fingerprint(item),
    }
    frontmatter_yaml = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=False).strip()
    body = extraction.text.strip()
    return f"---\n{frontmatter_yaml}\n---\n\n{body}\n"


def item_fingerprint(item: ZoteroItem) -> str:
    payload = {
        "item_key": item.item_key,
        "title": item.title,
        "authors": item.authors,
        "year": item.year,
        "url": item.url,
        "collection_path": item.collection_path,
        "pdf_attachment_key": item.pdf_attachment_key,
    }
    normalized = yaml.safe_dump(payload, sort_keys=True, allow_unicode=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
