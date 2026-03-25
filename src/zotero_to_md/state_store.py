from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from zotero_to_md.errors import SyncError
from zotero_to_md.models import StateEntry

SCHEMA_VERSION = 2


def _default_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "root_collection_key": None,
        "processed_items": {},
        "last_run_at": None,
    }


class StateStore:
    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path
        self.state: dict[str, Any] = _default_state()

    def load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            self.state = _default_state()
            return self.state
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SyncError(f"Invalid state file {self.state_path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise SyncError(
                f"Invalid state file {self.state_path}: expected a JSON object."
            )

        merged = _default_state()
        merged.update(raw)
        processed_items = raw.get("processed_items", {})
        if not isinstance(processed_items, dict):
            raise SyncError(
                f"Invalid state file {self.state_path}: processed_items must be a JSON object."
            )
        merged["processed_items"] = self._migrate_processed_items(processed_items)
        merged["schema_version"] = SCHEMA_VERSION
        self.state = merged
        return self.state

    def is_processed(self, item_key: str) -> bool:
        entry = self.get_processed_entry(item_key)
        return entry is not None and entry.get("status") == "ok"

    def get_processed_entry(self, item_key: str) -> dict[str, Any] | None:
        processed_items: dict[str, Any] = self.state.get("processed_items", {})
        entry = processed_items.get(item_key)
        return dict(entry) if isinstance(entry, dict) else None

    def mark_processed(self, item_key: str, entry: StateEntry) -> None:
        self.state.setdefault("processed_items", {})
        self.state["processed_items"][item_key] = {
            "output_path": entry.output_path,
            "processed_at": entry.processed_at,
            "source_kind": entry.source_kind,
            "status": entry.status,
            "fingerprint": entry.fingerprint,
            "last_seen_at": entry.last_seen_at,
        }

    def remove_processed(self, item_key: str) -> None:
        processed_items: dict[str, Any] = self.state.get("processed_items", {})
        processed_items.pop(item_key, None)

    def iter_processed_items(self) -> dict[str, dict[str, Any]]:
        processed_items: dict[str, Any] = self.state.get("processed_items", {})
        return {
            item_key: dict(entry)
            for item_key, entry in processed_items.items()
            if isinstance(item_key, str) and isinstance(entry, dict)
        }

    def save(self, *, root_collection_key: str, last_run_at: str) -> None:
        self.state["schema_version"] = SCHEMA_VERSION
        self.state["root_collection_key"] = root_collection_key
        self.state["last_run_at"] = last_run_at

        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.state_path.parent,
            prefix=".zotero_state.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            json.dump(self.state, tmp, ensure_ascii=True, indent=2)
            tmp.write("\n")
            temp_path = Path(tmp.name)
        temp_path.replace(self.state_path)

    @staticmethod
    def _migrate_processed_items(
        processed_items: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        migrated: dict[str, dict[str, Any]] = {}
        for item_key, raw_entry in processed_items.items():
            if not isinstance(item_key, str) or not isinstance(raw_entry, dict):
                continue
            migrated[item_key] = {
                "output_path": raw_entry.get("output_path"),
                "processed_at": raw_entry.get("processed_at"),
                "source_kind": raw_entry.get("source_kind", "none"),
                "status": raw_entry.get("status", "error"),
                "fingerprint": raw_entry.get("fingerprint"),
                "last_seen_at": raw_entry.get("last_seen_at")
                or raw_entry.get("processed_at"),
            }
        return migrated
