from pathlib import Path

from zotero_to_md.markdown_writer import render_markdown, resolve_output_path, sanitize_path_component
from zotero_to_md.models import ExtractionResult, ZoteroItem


def test_resolve_output_path_uses_numeric_suffix_for_collisions(tmp_path: Path) -> None:
    base_dir = tmp_path / ".cursor" / "papers"
    base_dir.mkdir(parents=True)

    existing = base_dir / "Jane Doe - Great Paper.md"
    existing.write_text("already here", encoding="utf-8")

    result = resolve_output_path(
        base_dir,
        collection_path="1. Introduction",
        title="Great Paper",
        authors=["Jane Doe"],
    )

    assert result.name == "Jane Doe - Great Paper.md"
    # Existing file is in root; this one lands in collection folder.
    assert result.parent.name == "1. Introduction"

    existing_in_collection = result
    existing_in_collection.parent.mkdir(parents=True, exist_ok=True)
    existing_in_collection.write_text("existing", encoding="utf-8")

    second = resolve_output_path(
        base_dir,
        collection_path="1. Introduction",
        title="Great Paper",
        authors=["Jane Doe"],
    )
    assert second.name == "Jane Doe - Great Paper-2.md"


def test_sanitize_path_component_replaces_invalid_chars() -> None:
    assert sanitize_path_component('a/b:c*?"<>| d') == "a-b-c- d"


def test_sanitize_path_component_avoids_windows_reserved_names() -> None:
    assert sanitize_path_component("con") == "con-file"


def test_resolve_output_path_truncates_long_windows_paths(monkeypatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "papers"
    base_dir.mkdir(parents=True)
    monkeypatch.setattr("zotero_to_md.markdown_writer._running_on_windows", lambda: True)
    monkeypatch.setattr(
        "zotero_to_md.markdown_writer.WINDOWS_MAX_PATH_LENGTH",
        len(str(base_dir)) + 48,
    )

    result = resolve_output_path(
        base_dir,
        collection_path="",
        title="Dynamic and explainable machine learning prediction of mortality in patients in the intensive care unit",
        authors=["Hans-Christian Thorsen-Meyer"],
    )

    assert len(str(result)) <= len(str(base_dir)) + 48
    assert result.suffix == ".md"
    assert result.name.endswith(".md")


def test_render_markdown_contains_frontmatter_and_text() -> None:
    item = ZoteroItem(
        item_key="ABCD1234",
        title="Paper Title",
        authors=["Jane Doe", "John Doe"],
        year="2025",
        url="https://example.com",
        collection_path="1. Introduction",
        pdf_attachment_key="ATTACH1",
    )
    extraction = ExtractionResult(source_kind="pdf", status="ok", text="Body text")

    markdown = render_markdown(
        item=item,
        extraction=extraction,
        processed_at="2026-03-02T10:00:00+00:00",
        source_url=item.url,
        collection_path=item.collection_path,
    )

    assert markdown.startswith("---\n")
    assert "zotero_item_key: ABCD1234" in markdown
    assert "source_kind: pdf" in markdown
    assert "fingerprint:" in markdown
    assert "item_type: null" in markdown
    assert markdown.endswith("Body text\n")
