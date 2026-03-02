from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable

from zotero_to_md.errors import SyncError
from zotero_to_md.extract_pdf import extract_pdf_text
from zotero_to_md.extract_web import extract_web_text
from zotero_to_md.markdown_writer import render_markdown, resolve_output_path
from zotero_to_md.models import AppConfig, ExtractionResult, StateEntry, SyncStats, ZoteroItem
from zotero_to_md.state_store import StateStore
from zotero_to_md.zotero_client import ZoteroClient

LogFn = Callable[[str], None]


def run_sync(config: AppConfig, *, client: ZoteroClient | None = None, log: LogFn | None = None) -> SyncStats:
    stats = SyncStats()
    logger = log or (lambda _message: None)

    zotero_client = client or ZoteroClient(
        user_id=config.zotero_user_id,
        api_key=config.zotero_api_key,
    )

    root_collection = zotero_client.find_collection_by_name(config.root_collection)
    root_collection_key = root_collection["key"]
    collection_path_map = zotero_client.build_collection_path_map(
        root_key=root_collection_key,
        recursive=config.recursive,
    )
    items = zotero_client.fetch_items(collection_path_map)
    stats.discovered = len(items)

    state = StateStore(config.state_path)
    state_data = state.load()
    state_root_key = state_data.get("root_collection_key")
    if state_root_key and state_root_key != root_collection_key:
        raise SyncError(
            "State file was created for a different root collection. "
            "Use a different target path or reset the state file."
        )

    if not config.dry_run:
        config.papers_root.mkdir(parents=True, exist_ok=True)

    for item in items:
        if state.is_processed(item.item_key):
            stats.skipped_existing += 1
            continue

        if config.dry_run:
            stats.would_process += 1
            continue

        extraction = _extract_item_content(item=item, client=zotero_client)
        processed_at = _utc_now_iso()
        output_path = resolve_output_path(
            config.papers_root,
            collection_path=item.collection_path,
            title=item.title,
            authors=item.authors,
        )
        markdown = render_markdown(
            item=item,
            extraction=extraction,
            processed_at=processed_at,
            source_url=item.url,
            collection_path=item.collection_path,
        )
        output_path.write_text(markdown, encoding="utf-8")

        state.mark_processed(
            item.item_key,
            StateEntry(
                output_path=str(output_path.relative_to(config.target_repo_path)),
                processed_at=processed_at,
                source_kind=extraction.source_kind,
                status=extraction.status,
            ),
        )
        stats.processed += 1
        if extraction.status == "error":
            stats.errors += 1
        stats.written_files.append(output_path)
        if config.verbose:
            logger(f"processed {item.item_key} -> {output_path}")

    if not config.dry_run:
        state.save(root_collection_key=root_collection_key, last_run_at=_utc_now_iso())

    return stats


def _extract_item_content(*, item: ZoteroItem, client: ZoteroClient) -> ExtractionResult:
    if item.pdf_attachment_key:
        try:
            with TemporaryDirectory(prefix="zotero-to-md-") as temp_dir:
                downloaded_pdf = client.download_pdf_attachment(
                    item.pdf_attachment_key,
                    Path(temp_dir) / f"{item.item_key}.pdf",
                )
                extracted = extract_pdf_text(downloaded_pdf)
                if extracted.strip():
                    return ExtractionResult(source_kind="pdf", status="ok", text=extracted.strip())
                pdf_error = "PDF extracted but had no readable text."
        except Exception as exc:
            pdf_error = f"PDF extraction failed: {exc}"

        if item.url:
            web_text, web_error = extract_web_text(item.url)
            if web_text:
                return ExtractionResult(source_kind="web", status="ok", text=web_text.strip())
            error_text = _error_body(web_error or "Web extraction failed.", url=item.url)
            return ExtractionResult(
                source_kind="web",
                status="error",
                text=f"{error_text}\n\nPDF fallback error: {pdf_error}",
                error_message=web_error or pdf_error,
            )

        return ExtractionResult(
            source_kind="pdf",
            status="error",
            text=_error_body(pdf_error, url=item.url),
            error_message=pdf_error,
        )

    if item.url:
        web_text, web_error = extract_web_text(item.url)
        if web_text:
            return ExtractionResult(source_kind="web", status="ok", text=web_text.strip())
        return ExtractionResult(
            source_kind="web",
            status="error",
            text=_error_body(web_error or "Web extraction failed.", url=item.url),
            error_message=web_error,
        )

    error_text = "No PDF attachment and no URL found for this Zotero item."
    return ExtractionResult(
        source_kind="none",
        status="error",
        text=_error_body(error_text, url=None),
        error_message=error_text,
    )


def _error_body(message: str, *, url: str | None) -> str:
    body_lines = [
        "# Content extraction failed",
        "",
        f"Reason: {message}",
    ]
    if url:
        body_lines.extend(["", f"Source URL: {url}"])
    return "\n".join(body_lines)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

