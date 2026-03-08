from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SourceKind = Literal["pdf", "web", "none"]
ProcessingStatus = Literal["ok", "error"]


@dataclass(slots=True)
class AppConfig:
    zotero_user_id: str
    zotero_api_key: str
    target_destination_path: Path
    root_collection: str
    recursive: bool = True
    dry_run: bool = False
    verbose: bool = False

    @property
    def output_root(self) -> Path:
        return self.target_destination_path

    @property
    def state_path(self) -> Path:
        return self.target_destination_path / ".zotero_state.json"


@dataclass(slots=True)
class ZoteroItem:
    item_key: str
    title: str
    authors: list[str]
    year: str | None
    url: str | None
    collection_path: str
    pdf_attachment_key: str | None
    item_type: str | None = None
    tags: list[str] = field(default_factory=list)
    abstract: str | None = None
    doi: str | None = None
    zotero_library_key: str | None = None


@dataclass(slots=True)
class ExtractionResult:
    source_kind: SourceKind
    status: ProcessingStatus
    text: str
    error_message: str | None = None


@dataclass(slots=True)
class StateEntry:
    output_path: str | None
    processed_at: str
    source_kind: SourceKind
    status: ProcessingStatus
    fingerprint: str | None = None
    last_seen_at: str | None = None


@dataclass(slots=True)
class SyncStats:
    discovered: int = 0
    processed: int = 0
    skipped_existing: int = 0
    errors: int = 0
    would_process: int = 0
    written_files: list[Path] = field(default_factory=list)


@dataclass(slots=True)
class StatusReport:
    root_collection: str
    state_schema_version: int
    last_run_at: str | None
    new: int = 0
    changed: int = 0
    errored: int = 0
    stale: int = 0
    ok: int = 0


@dataclass(slots=True)
class PruneStats:
    stale_item_keys: list[str] = field(default_factory=list)
    deleted_files: int = 0
    removed_state_entries: int = 0
