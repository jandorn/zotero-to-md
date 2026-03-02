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


@dataclass(slots=True)
class ExtractionResult:
    source_kind: SourceKind
    status: ProcessingStatus
    text: str
    error_message: str | None = None


@dataclass(slots=True)
class StateEntry:
    output_path: str
    processed_at: str
    source_kind: SourceKind
    status: ProcessingStatus


@dataclass(slots=True)
class SyncStats:
    discovered: int = 0
    processed: int = 0
    skipped_existing: int = 0
    errors: int = 0
    would_process: int = 0
    written_files: list[Path] = field(default_factory=list)
