import json
from pathlib import Path

from zotero_to_md.models import AppConfig, ZoteroItem
from zotero_to_md.sync import run_sync


class FakeZoteroClient:
    def __init__(self, items: list[ZoteroItem], collection_map: dict[str, str] | None = None) -> None:
        self.items = items
        self.collection_map = collection_map or {"ROOT": "", "INTRO": "1. Introduction"}

    def find_collection_by_name(self, name: str) -> dict[str, str]:
        assert name == "Masterarbeit"
        return {"key": "ROOT"}

    def build_collection_path_map(self, *, root_key: str, recursive: bool) -> dict[str, str]:
        assert root_key == "ROOT"
        return self.collection_map if recursive else {"ROOT": ""}

    def fetch_items(self, collection_path_map: dict[str, str]) -> list[ZoteroItem]:
        return list(self.items)

    def download_pdf_attachment(self, attachment_key: str, destination_path: Path) -> Path:
        destination_path.write_bytes(b"%PDF-1.7 fake content")
        return destination_path


def _make_config(tmp_path: Path, dry_run: bool = False) -> AppConfig:
    target_destination = tmp_path / "target"
    target_destination.mkdir(parents=True, exist_ok=True)
    return AppConfig(
        zotero_user_id="12345",
        zotero_api_key="secret",
        target_destination_path=target_destination,
        root_collection="Masterarbeit",
        recursive=True,
        dry_run=dry_run,
        verbose=False,
    )


def test_sync_is_incremental_for_existing_items(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("zotero_to_md.sync.extract_pdf_text", lambda _path: "pdf text")
    monkeypatch.setattr("zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None))

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

    assert first_stats.discovered == 2
    assert first_stats.processed == 2
    assert first_stats.skipped_existing == 0
    assert second_stats.processed == 0
    assert second_stats.skipped_existing == 2

    state_data = json.loads(config.state_path.read_text(encoding="utf-8"))
    assert set(state_data["processed_items"]) == {"ITEM_PDF", "ITEM_WEB"}


def test_sync_processes_only_new_items_after_first_run(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("zotero_to_md.sync.extract_pdf_text", lambda _path: "pdf text")
    monkeypatch.setattr("zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None))

    initial_items = [
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
    client = FakeZoteroClient(initial_items)
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


def test_web_failure_still_creates_markdown_and_error_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("zotero_to_md.sync.extract_web_text", lambda _url: (None, "paywall"))

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

    stats = run_sync(config, client=client)

    assert stats.processed == 1
    assert stats.errors == 1
    markdown_files = list((config.output_root / "Demand Response").glob("*.md"))
    assert markdown_files
    content = markdown_files[0].read_text(encoding="utf-8")
    assert "Content extraction failed" in content

    state_data = json.loads(config.state_path.read_text(encoding="utf-8"))
    assert state_data["processed_items"]["ITEM_WEB_FAIL"]["status"] == "error"


def test_sync_reports_progress_updates(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("zotero_to_md.sync.extract_web_text", lambda _url: ("web text", None))

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

    run_sync(config, client=client, progress=lambda current, total, label: events.append((current, total, label)))

    assert events[0] == (0, 2, "starting")
    assert events[-1] == (2, 2, "done")
