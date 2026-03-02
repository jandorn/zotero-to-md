from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from zotero_to_md.models import StateEntry

SCHEMA_VERSION = 1


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
        raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        merged = _default_state()
        merged.update(raw)
        merged["processed_items"] = dict(raw.get("processed_items", {}))
        self.state = merged
        return self.state

    def is_processed(self, item_key: str) -> bool:
        processed_items: dict[str, Any] = self.state.get("processed_items", {})
        return item_key in processed_items

    def mark_processed(self, item_key: str, entry: StateEntry) -> None:
        self.state.setdefault("processed_items", {})
        self.state["processed_items"][item_key] = {
            "output_path": entry.output_path,
            "processed_at": entry.processed_at,
            "source_kind": entry.source_kind,
            "status": entry.status,
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

