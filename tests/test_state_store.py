import json
from pathlib import Path

from zotero_to_md.models import StateEntry
from zotero_to_md.state_store import StateStore


def test_state_store_roundtrip(tmp_path: Path) -> None:
    state_path = tmp_path / "notes" / ".zotero_state.json"
    store = StateStore(state_path)
    store.load()
    store.mark_processed(
        "ITEM1",
        StateEntry(
            output_path="1. Introduction/Jane - Paper.md",
            processed_at="2026-03-02T10:00:00+00:00",
            source_kind="pdf",
            status="ok",
            fingerprint="abc123",
            last_seen_at="2026-03-02T10:00:00+00:00",
        ),
    )
    store.save(root_collection_key="ROOT1", last_run_at="2026-03-02T10:01:00+00:00")

    loaded = json.loads(state_path.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == 2
    assert loaded["root_collection_key"] == "ROOT1"
    assert "ITEM1" in loaded["processed_items"]
    assert loaded["processed_items"]["ITEM1"]["fingerprint"] == "abc123"

    reloaded_store = StateStore(state_path)
    reloaded_store.load()
    assert reloaded_store.is_processed("ITEM1")


def test_state_store_migrates_v1_entries(tmp_path: Path) -> None:
    state_path = tmp_path / ".zotero_state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "root_collection_key": "ROOT1",
                "processed_items": {
                    "ITEM1": {
                        "output_path": "Paper.md",
                        "processed_at": "2026-03-02T10:00:00+00:00",
                        "source_kind": "web",
                        "status": "ok",
                    }
                },
                "last_run_at": "2026-03-02T10:01:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    store = StateStore(state_path)
    state = store.load()

    assert state["schema_version"] == 2
    assert state["processed_items"]["ITEM1"]["output_path"] == "Paper.md"
    assert state["processed_items"]["ITEM1"]["fingerprint"] is None
    assert state["processed_items"]["ITEM1"]["last_seen_at"] == "2026-03-02T10:00:00+00:00"
