import json
from pathlib import Path

import pytest

from zotero_to_md.errors import SyncError
from zotero_to_md.models import AppConfig, ZoteroItem
from zotero_to_md.sync import get_status_report, run_prune, run_resync, run_sync


class FakeZoteroClient:
    def __init__(
        self, items: list[ZoteroItem], collection_map: dict[str, str] | None = None
    ) -> None:
        self.items = items
        self.collection_map = collection_map or {"ROOT": "", "INTRO": "1. Introduction"}

    def find_collection_by_name(self, name: str) -> dict[str, str]:
        assert name == "Masterarbeit"
        return {"key": "ROOT"}

    def build_collection_path_map(
        self, *, root_key: str, recursive: bool
    ) -> dict[str, str]:
        assert root_key == "ROOT"
        return self.collection_map if recursive else {"ROOT": ""}

    def fetch_items(self, collection_path_map: dict[str, str]) -> list[ZoteroItem]:
        return list(self.items)

    def download_pdf_attachment(
        self, attachment_key: str, destination_path: Path
    ) -> Path:
        destination_path.write_bytes(b"%PDF-1.7 fake content")
        return destination_path


def _make_config(
    tmp_path: Path, dry_run: bool = False, verbose: bool = False
) -> AppConfig:
    target_destination = tmp_path / "target"
    target_destination.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        zotero_user_id="12345",
        zotero_api_key="secret",
        target_destination_path=target_destination,
        root_collection="Masterarbeit",
        recursive=True,
        dry_run=dry_run,
        verbose=verbose,
    )


def test_sync_is_incremental_for_unchanged_items(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("zotero_to_md.sync.extract_pdf_text", lambda _path: "pdf text")
    monkeypatch.setattr(
        "zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None)
    )

    items = [
        ZoteroItem(
            item_key="ITEM_PDF",
            title="PDF Paper",
            authors=["Jane Doe"],
            year="2026",
            url=None,
            collection_path="1. Introduction",
            pdf_attachment_key="ATTACH_PDF",
        ),
        ZoteroItem(
            item_key="ITEM_WEB",
            title="Web Paper",
            authors=["John Doe"],
            year="2025",
            url="https://example.com/article",
            collection_path="2. Related Work",
            pdf_attachment_key=None,
        ),
    ]
    client = FakeZoteroClient(items)
    config = _make_config(tmp_path)

    first_stats = run_sync(config, client=client)
    second_stats = run_sync(config, client=client)

    assert first_stats.processed == 2
    assert second_stats.processed == 0
    assert second_stats.skipped_existing == 2


def test_sync_processes_only_new_items_after_first_run(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("zotero_to_md.sync.extract_pdf_text", lambda _path: "pdf text")
    monkeypatch.setattr(
        "zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None)
    )

    client = FakeZoteroClient(
        [
            ZoteroItem(
                item_key="ITEM_A",
                title="Paper A",
                authors=["Alice"],
                year="2026",
                url=None,
                collection_path="",
                pdf_attachment_key="ATTACH_A",
            )
        ]
    )
    config = _make_config(tmp_path)

    run_sync(config, client=client)
    client.items.append(
        ZoteroItem(
            item_key="ITEM_B",
            title="Paper B",
            authors=["Bob"],
            year="2025",
            url="https://example.com/b",
            collection_path="",
            pdf_attachment_key=None,
        )
    )
    stats = run_sync(config, client=client)

    assert stats.processed == 1
    assert stats.skipped_existing == 1
    state_data = json.loads(config.state_path.read_text(encoding="utf-8"))
    assert set(state_data["processed_items"]) == {"ITEM_A", "ITEM_B"}


def test_sync_retries_error_items(monkeypatch, tmp_path: Path) -> None:
    responses = iter([(None, "paywall"), ("web text", None)])
    monkeypatch.setattr(
        "zotero_to_md.sync.extract_web_text", lambda _url: next(responses)
    )

    item = ZoteroItem(
        item_key="ITEM_WEB_FAIL",
        title="Blocked Web Paper",
        authors=["Carol"],
        year="2024",
        url="https://example.com/paywalled",
        collection_path="Demand Response",
        pdf_attachment_key=None,
    )
    client = FakeZoteroClient([item])
    config = _make_config(tmp_path)

    first_stats = run_sync(config, client=client)
    second_stats = run_sync(config, client=client)

    assert first_stats.processed == 1
    assert first_stats.errors == 1
    assert second_stats.processed == 1
    assert second_stats.errors == 0
    content = next((config.output_root / "Demand Response").glob("*.md")).read_text(
        encoding="utf-8"
    )
    assert content.endswith("web text\n")


def test_sync_persists_checkpoint_when_later_item_fails(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None)
    )

    def exploding_render(*args, **kwargs):  # noqa: ANN002, ANN003
        item = kwargs["item"]
        if item.item_key == "ITEM_2":
            raise RuntimeError("boom")
        from zotero_to_md.markdown_writer import render_markdown as real_render

        return real_render(*args, **kwargs)

    monkeypatch.setattr("zotero_to_md.sync.render_markdown", exploding_render)

    client = FakeZoteroClient(
        [
            ZoteroItem(
                item_key="ITEM_1",
                title="Paper 1",
                authors=["A"],
                year="2026",
                url="https://example.com/1",
                collection_path="",
                pdf_attachment_key=None,
            ),
            ZoteroItem(
                item_key="ITEM_2",
                title="Paper 2",
                authors=["B"],
                year="2026",
                url="https://example.com/2",
                collection_path="",
                pdf_attachment_key=None,
            ),
        ]
    )
    config = _make_config(tmp_path, verbose=True)
    messages: list[str] = []

    stats = run_sync(config, client=client, log=messages.append)

    assert stats.processed == 1
    assert stats.errors == 1
    state_data = json.loads(config.state_path.read_text(encoding="utf-8"))
    assert state_data["processed_items"]["ITEM_1"]["status"] == "ok"
    assert state_data["processed_items"]["ITEM_2"]["status"] == "error"
    assert any("error processing ITEM_2" in message for message in messages)


def test_sync_rewrites_changed_items_in_existing_path(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None)
    )

    item = ZoteroItem(
        item_key="ITEM_1",
        title="Original Title",
        authors=["Jane Doe"],
        year="2026",
        url="https://example.com/1",
        collection_path="Old Folder",
        pdf_attachment_key=None,
    )
    client = FakeZoteroClient([item], collection_map={"ROOT": "", "OLD": "Old Folder"})
    config = _make_config(tmp_path)

    run_sync(config, client=client)
    original_path = next(config.output_root.rglob("*.md"))

    client.items[0] = ZoteroItem(
        item_key="ITEM_1",
        title="New Title",
        authors=["Jane Doe"],
        year="2026",
        url="https://example.com/1",
        collection_path="New Folder",
        pdf_attachment_key=None,
    )
    stats = run_sync(config, client=client)

    assert stats.processed == 1
    assert original_path.exists()
    assert not (config.output_root / "New Folder" / "Jane Doe - New Title.md").exists()
    content = original_path.read_text(encoding="utf-8")
    assert "title: New Title" in content
    assert "collection_path: New Folder" in content


def test_sync_reprocesses_items_when_only_metadata_changes(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None)
    )

    item = ZoteroItem(
        item_key="ITEM_META",
        title="Metadata Paper",
        authors=["Jane Doe"],
        year="2026",
        url="https://example.com/metadata",
        collection_path="",
        pdf_attachment_key=None,
        tags=["alpha"],
        abstract="Original abstract",
        doi="10.1000/original",
    )
    client = FakeZoteroClient([item])
    config = _make_config(tmp_path)

    first_stats = run_sync(config, client=client)
    output_path = next(config.output_root.rglob("*.md"))

    client.items[0] = ZoteroItem(
        item_key="ITEM_META",
        title="Metadata Paper",
        authors=["Jane Doe"],
        year="2026",
        url="https://example.com/metadata",
        collection_path="",
        pdf_attachment_key=None,
        tags=["alpha", "beta"],
        abstract="Updated abstract",
        doi="10.1000/updated",
    )

    second_stats = run_sync(config, client=client)

    assert first_stats.processed == 1
    assert second_stats.processed == 1
    assert second_stats.skipped_existing == 0
    content = output_path.read_text(encoding="utf-8")
    assert "abstract: Updated abstract" in content
    assert "doi: 10.1000/updated" in content
    assert "- beta" in content


def test_resync_moves_item_to_canonical_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None)
    )

    client = FakeZoteroClient(
        [
            ZoteroItem(
                item_key="ITEM_1",
                title="Original Title",
                authors=["Jane Doe"],
                year="2026",
                url="https://example.com/1",
                collection_path="Old Folder",
                pdf_attachment_key=None,
            )
        ],
        collection_map={"ROOT": "", "OLD": "Old Folder"},
    )
    config = _make_config(tmp_path)

    run_sync(config, client=client)
    old_path = next(config.output_root.rglob("*.md"))

    client.items[0] = ZoteroItem(
        item_key="ITEM_1",
        title="New Title",
        authors=["Jane Doe"],
        year="2026",
        url="https://example.com/1",
        collection_path="New Folder",
        pdf_attachment_key=None,
    )

    stats = run_resync(config, client=client, item_key="ITEM_1")

    new_path = config.output_root / "New Folder" / "Jane Doe - New Title.md"
    assert stats.processed == 1
    assert not old_path.exists()
    assert new_path.exists()
    state_data = json.loads(config.state_path.read_text(encoding="utf-8"))
    assert (
        state_data["processed_items"]["ITEM_1"]["output_path"]
        == "New Folder/Jane Doe - New Title.md"
    )


def test_prune_reports_and_removes_stale_items(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None)
    )

    item = ZoteroItem(
        item_key="ITEM_STALE",
        title="Stale Paper",
        authors=["Jane Doe"],
        year="2026",
        url="https://example.com/1",
        collection_path="",
        pdf_attachment_key=None,
    )
    client = FakeZoteroClient([item])
    config = _make_config(tmp_path)

    run_sync(config, client=client)
    stale_path = next(config.output_root.rglob("*.md"))
    client.items = []

    dry_run = run_prune(config, client=client, apply=False)

    assert dry_run.stale_item_keys == ["ITEM_STALE"]
    assert stale_path.exists()
    apply_run = run_prune(config, client=client, apply=True)
    assert apply_run.deleted_files == 1
    assert apply_run.removed_state_entries == 1
    assert not stale_path.exists()
    state_data = json.loads(config.state_path.read_text(encoding="utf-8"))
    assert state_data["processed_items"] == {}


def test_status_report_counts_new_changed_errored_stale_and_ok(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None)
    )

    client = FakeZoteroClient(
        [
            ZoteroItem(
                item_key="OK",
                title="Paper OK",
                authors=["Jane Doe"],
                year="2026",
                url="https://example.com/ok",
                collection_path="",
                pdf_attachment_key=None,
            ),
            ZoteroItem(
                item_key="CHANGE",
                title="Paper Change",
                authors=["Jane Doe"],
                year="2026",
                url="https://example.com/change",
                collection_path="",
                pdf_attachment_key=None,
            ),
            ZoteroItem(
                item_key="ERROR",
                title="Paper Error",
                authors=["Jane Doe"],
                year="2026",
                url="https://example.com/error",
                collection_path="",
                pdf_attachment_key=None,
            ),
        ]
    )
    config = _make_config(tmp_path)

    run_sync(config, client=client)
    state_data = json.loads(config.state_path.read_text(encoding="utf-8"))
    state_data["processed_items"]["ERROR"]["status"] = "error"
    state_data["processed_items"]["STALE"] = {
        "output_path": "stale.md",
        "processed_at": "2026-03-02T10:00:00+00:00",
        "source_kind": "web",
        "status": "ok",
        "fingerprint": "stale",
        "last_seen_at": "2026-03-02T10:00:00+00:00",
    }
    config.state_path.write_text(json.dumps(state_data), encoding="utf-8")

    client.items[1] = ZoteroItem(
        item_key="CHANGE",
        title="Paper Changed",
        authors=["Jane Doe"],
        year="2026",
        url="https://example.com/change",
        collection_path="Moved",
        pdf_attachment_key=None,
    )
    client.items.append(
        ZoteroItem(
            item_key="NEW",
            title="Paper New",
            authors=["Jane Doe"],
            year="2026",
            url="https://example.com/new",
            collection_path="",
            pdf_attachment_key=None,
        )
    )

    report = get_status_report(config, client=client)

    assert report.new == 1
    assert report.changed == 1
    assert report.errored == 1
    assert report.stale == 1
    assert report.ok == 1


def test_sync_reports_progress_updates(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None)
    )

    items = [
        ZoteroItem(
            item_key="ITEM_1",
            title="Paper 1",
            authors=["A"],
            year="2026",
            url="https://example.com/1",
            collection_path="",
            pdf_attachment_key=None,
        ),
        ZoteroItem(
            item_key="ITEM_2",
            title="Paper 2",
            authors=["B"],
            year="2026",
            url="https://example.com/2",
            collection_path="",
            pdf_attachment_key=None,
        ),
    ]
    client = FakeZoteroClient(items)
    config = _make_config(tmp_path)
    events: list[tuple[int, int, str | None]] = []

    run_sync(
        config,
        client=client,
        progress=lambda current, total, label: events.append((current, total, label)),
    )

    assert events[0] == (0, 2, "starting")
    assert events[-1] == (2, 2, "done")


def test_sync_truncates_long_windows_output_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None)
    )
    monkeypatch.setattr(
        "zotero_to_md.markdown_writer._running_on_windows", lambda: True
    )

    config = _make_config(tmp_path)
    monkeypatch.setattr(
        "zotero_to_md.markdown_writer.WINDOWS_MAX_PATH_LENGTH",
        len(str(config.output_root)) + 64,
    )

    client = FakeZoteroClient(
        [
            ZoteroItem(
                item_key="ITEM_LONG",
                title="Dynamic and explainable machine learning prediction of mortality in patients in the intensive care unit a retrospective study of high-frequency data in electronic patient records",
                authors=["Hans-Christian Thorsen-Meyer"],
                year="2026",
                url="https://example.com/long",
                collection_path="",
                pdf_attachment_key=None,
            )
        ]
    )

    stats = run_sync(config, client=client)

    assert stats.processed == 1
    assert len(stats.written_files) == 1
    assert len(str(stats.written_files[0])) <= len(str(config.output_root)) + 64


def test_sync_raises_clear_error_for_invalid_state_file(tmp_path: Path) -> None:
    config = _make_config(tmp_path)
    config.state_path.write_text("{invalid json", encoding="utf-8")
    client = FakeZoteroClient([])

    with pytest.raises(SyncError, match="Invalid state file"):
        run_sync(config, client=client)
