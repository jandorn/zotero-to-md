import json
from pathlib import Path

from zotero_to_md.models import StateEntry
from zotero_to_md.state_store import StateStore


def test_state_store_roundtrip(tmp_path: Path) -> None:
    state_path = tmp_path / ".cursor" / "papers" / ".zotero_state.json"
    store = StateStore(state_path)
    store.load()
    store.mark_processed(
        "ITEM1",
        StateEntry(
            output_path=".cursor/papers/1. Introduction/Jane - Paper.md",
            processed_at="2026-03-02T10:00:00+00:00",
            source_kind="pdf",
            status="ok",
        ),
    )
    store.save(root_collection_key="ROOT1", last_run_at="2026-03-02T10:01:00+00:00")

    loaded = json.loads(state_path.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == 1
    assert loaded["root_collection_key"] == "ROOT1"
    assert "ITEM1" in loaded["processed_items"]

    reloaded_store = StateStore(state_path)
    reloaded_store.load()
    assert reloaded_store.is_processed("ITEM1")

