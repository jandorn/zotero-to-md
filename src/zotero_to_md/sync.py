from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Literal

from zotero_to_md.errors import SyncError
from zotero_to_md.extract_pdf import extract_pdf_text
from zotero_to_md.extract_web import extract_web_text
from zotero_to_md.markdown_writer import (
    item_fingerprint,
    render_markdown,
    resolve_output_path,
)
from zotero_to_md.models import (
    AppConfig,
    ExtractionResult,
    PruneStats,
    StateEntry,
    StatusReport,
    SyncStats,
    ZoteroItem,
)
from zotero_to_md.state_store import SCHEMA_VERSION, StateStore
from zotero_to_md.zotero_client import ZoteroClient

LogFn = Callable[[str], None]
ProgressFn = Callable[[int, int, str | None], None]
SyncDecision = Literal["new", "changed", "retry-error", "ok"]


@dataclass(slots=True)
class _SyncContext:
    config: AppConfig
    client: ZoteroClient
    root_collection_key: str
    items: list[ZoteroItem]
    item_by_key: dict[str, ZoteroItem]
    state: StateStore
    state_data: dict[str, object]


def run_sync(
    config: AppConfig,
    *,
    client: ZoteroClient | None = None,
    log: LogFn | None = None,
    progress: ProgressFn | None = None,
) -> SyncStats:
    stats = SyncStats()
    logger = log or (lambda _message: None)
    progress_update = progress or (lambda _current, _total, _label: None)
    context = _load_sync_context(config, client=client)

    stats.discovered = len(context.items)
    total_items = len(context.items)
    progress_update(0, total_items, "starting")

    if not config.dry_run:
        config.output_root.mkdir(parents=True, exist_ok=True)

    for idx, item in enumerate(context.items, start=1):
        fingerprint = item_fingerprint(item)
        decision = _classify_item(
            context.state.get_processed_entry(item.item_key), fingerprint
        )

        if decision == "ok":
            existing_entry = context.state.get_processed_entry(item.item_key)
            seen_at = _utc_now_iso()
            stats.skipped_existing += 1
            if not config.dry_run:
                _save_state_entry(
                    context,
                    item=item,
                    fingerprint=fingerprint,
                    processed_at=_as_optional_str(existing_entry.get("processed_at"))
                    or seen_at,
                    source_kind=_source_kind_from_state(existing_entry),
                    status="ok",
                    output_path=_output_path_from_state(context.config, existing_entry),
                    last_seen_at=seen_at,
                )
            progress_update(idx, total_items, "skipped")
            continue

        if config.dry_run:
            stats.would_process += 1
            progress_update(idx, total_items, f"would-{decision}")
            continue

        try:
            output_path = _process_item(
                context, item=item, fingerprint=fingerprint, force_canonical_path=False
            )
            stats.processed += 1
            stats.written_files.append(output_path)
            if (
                context.state.get_processed_entry(item.item_key)
                and decision == "retry-error"
            ):
                logger(f"retried {item.item_key} -> {output_path}")
            elif config.verbose:
                logger(f"processed {item.item_key} -> {output_path}")
            current_entry = context.state.get_processed_entry(item.item_key)
            if current_entry and current_entry.get("status") == "error":
                stats.errors += 1
            progress_update(idx, total_items, "processed")
        except Exception as exc:
            processed_at = _utc_now_iso()
            existing_entry = context.state.get_processed_entry(item.item_key)
            _save_state_entry(
                context,
                item=item,
                fingerprint=fingerprint,
                processed_at=processed_at,
                source_kind=_source_kind_from_state(existing_entry),
                status="error",
                output_path=_output_path_from_state(context.config, existing_entry),
            )
            stats.errors += 1
            logger(f"error processing {item.item_key}: {exc}")
            progress_update(idx, total_items, "error")

    if not config.dry_run:
        context.state.save(
            root_collection_key=context.root_collection_key, last_run_at=_utc_now_iso()
        )

    if total_items == 0:
        progress_update(1, 1, "done")
    else:
        progress_update(total_items, total_items, "done")

    return stats


def get_status_report(
    config: AppConfig, *, client: ZoteroClient | None = None
) -> StatusReport:
    context = _load_sync_context(config, client=client)
    return _build_status_report(context)


def run_resync(
    config: AppConfig,
    *,
    client: ZoteroClient | None = None,
    item_key: str | None = None,
    all_items: bool = False,
    log: LogFn | None = None,
) -> SyncStats:
    if not all_items and not item_key:
        raise SyncError("Choose either --all or --item-key for resync.")
    if all_items and item_key:
        raise SyncError("Use either --all or --item-key, not both.")

    logger = log or (lambda _message: None)
    context = _load_sync_context(config, client=client)
    selected_items = (
        context.items if all_items else [context.item_by_key.get(item_key or "")]
    )

    if not all_items and selected_items == [None]:
        raise SyncError(
            f'Item "{item_key}" was not found under the selected root collection.'
        )

    stats = SyncStats(discovered=len(context.items))
    for selected in selected_items:
        assert selected is not None
        fingerprint = item_fingerprint(selected)
        try:
            output_path = _process_item(
                context,
                item=selected,
                fingerprint=fingerprint,
                force_canonical_path=True,
            )
            stats.processed += 1
            stats.written_files.append(output_path)
            if config.verbose:
                logger(f"resynced {selected.item_key} -> {output_path}")
            current_entry = context.state.get_processed_entry(selected.item_key)
            if current_entry and current_entry.get("status") == "error":
                stats.errors += 1
        except Exception as exc:
            _save_state_entry(
                context,
                item=selected,
                fingerprint=fingerprint,
                processed_at=_utc_now_iso(),
                source_kind=_source_kind_from_state(
                    context.state.get_processed_entry(selected.item_key)
                ),
                status="error",
                output_path=_output_path_from_state(
                    context.config,
                    context.state.get_processed_entry(selected.item_key),
                ),
            )
            stats.errors += 1
            logger(f"error resyncing {selected.item_key}: {exc}")

    context.state.save(
        root_collection_key=context.root_collection_key, last_run_at=_utc_now_iso()
    )
    return stats


def run_prune(
    config: AppConfig,
    *,
    client: ZoteroClient | None = None,
    apply: bool = False,
) -> PruneStats:
    context = _load_sync_context(config, client=client)
    current_keys = set(context.item_by_key)
    stale_keys = sorted(
        key for key in context.state.iter_processed_items() if key not in current_keys
    )
    stats = PruneStats(stale_item_keys=stale_keys)

    if not apply:
        return stats

    for stale_key in stale_keys:
        entry = context.state.get_processed_entry(stale_key)
        output_path = _output_path_from_state(context.config, entry)
        if output_path is not None and output_path.exists():
            try:
                output_path.unlink()
                stats.deleted_files += 1
            except OSError as exc:
                raise SyncError(
                    f"Failed to delete stale file {output_path}: {exc}"
                ) from exc
        context.state.remove_processed(stale_key)
        stats.removed_state_entries += 1

    context.state.save(
        root_collection_key=context.root_collection_key, last_run_at=_utc_now_iso()
    )
    return stats


def _load_sync_context(
    config: AppConfig, *, client: ZoteroClient | None = None
) -> _SyncContext:
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

    state = StateStore(config.state_path)
    state_data = state.load()
    state_root_key = state_data.get("root_collection_key")
    if state_root_key and state_root_key != root_collection_key:
        raise SyncError(
            "State file was created for a different root collection. "
            "Use a different target path or reset the state file."
        )

    return _SyncContext(
        config=config,
        client=zotero_client,
        root_collection_key=root_collection_key,
        items=items,
        item_by_key={item.item_key: item for item in items},
        state=state,
        state_data=state_data,
    )


def _build_status_report(context: _SyncContext) -> StatusReport:
    report = StatusReport(
        root_collection=context.config.root_collection,
        state_schema_version=int(
            context.state_data.get("schema_version", SCHEMA_VERSION)
        ),
        last_run_at=_as_optional_str(context.state_data.get("last_run_at")),
    )
    current_keys = set(context.item_by_key)
    state_entries = context.state.iter_processed_items()

    for item in context.items:
        fingerprint = item_fingerprint(item)
        decision = _classify_item(state_entries.get(item.item_key), fingerprint)
        if decision == "new":
            report.new += 1
        elif decision == "changed":
            report.changed += 1
        elif decision == "retry-error":
            report.errored += 1
        else:
            report.ok += 1

    report.stale = len([key for key in state_entries if key not in current_keys])
    return report


def _classify_item(
    state_entry: dict[str, object] | None, fingerprint: str
) -> SyncDecision:
    if state_entry is None:
        return "new"
    if state_entry.get("status") == "error":
        return "retry-error"
    if state_entry.get("fingerprint") != fingerprint:
        return "changed"
    return "ok"


def _process_item(
    context: _SyncContext,
    *,
    item: ZoteroItem,
    fingerprint: str,
    force_canonical_path: bool,
) -> Path:
    extraction = _extract_item_content(item=item, client=context.client)
    processed_at = _utc_now_iso()
    existing_entry = context.state.get_processed_entry(item.item_key)
    current_output = _output_path_from_state(context.config, existing_entry)
    output_path = _resolve_item_output_path(
        context.config,
        item=item,
        current_output=current_output,
        force_canonical_path=force_canonical_path,
    )
    old_output = current_output if force_canonical_path else None
    if (
        force_canonical_path
        and old_output is not None
        and old_output != output_path
        and old_output.exists()
    ):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        old_output.replace(output_path)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    markdown = render_markdown(
        item=item,
        extraction=extraction,
        processed_at=processed_at,
        source_url=item.url,
        collection_path=item.collection_path,
    )
    try:
        output_path.write_text(markdown, encoding="utf-8")
    except OSError as exc:
        raise SyncError(f"Failed to write output file {output_path}: {exc}") from exc

    _save_state_entry(
        context,
        item=item,
        fingerprint=fingerprint,
        processed_at=processed_at,
        source_kind=extraction.source_kind,
        status=extraction.status,
        output_path=output_path,
    )
    return output_path


def _resolve_item_output_path(
    config: AppConfig,
    *,
    item: ZoteroItem,
    current_output: Path | None,
    force_canonical_path: bool,
) -> Path:
    if not force_canonical_path and current_output is not None:
        return current_output
    return resolve_output_path(
        config.output_root,
        collection_path=item.collection_path,
        title=item.title,
        authors=item.authors,
        allow_existing_path=current_output,
    )


def _save_state_entry(
    context: _SyncContext,
    *,
    item: ZoteroItem,
    fingerprint: str,
    processed_at: str,
    source_kind: Literal["pdf", "web", "none"],
    status: Literal["ok", "error"],
    output_path: Path | None,
    last_seen_at: str | None = None,
) -> None:
    relative_output_path: str | None = None
    if output_path is not None:
        relative_output_path = str(output_path.relative_to(context.config.output_root))
    context.state.mark_processed(
        item.item_key,
        StateEntry(
            output_path=relative_output_path,
            processed_at=processed_at,
            source_kind=source_kind,
            status=status,
            fingerprint=fingerprint,
            last_seen_at=last_seen_at or processed_at,
        ),
    )
    context.state.save(
        root_collection_key=context.root_collection_key, last_run_at=processed_at
    )


def _output_path_from_state(
    config: AppConfig, state_entry: dict[str, object] | None
) -> Path | None:
    if state_entry is None:
        return None
    raw_output_path = state_entry.get("output_path")
    if raw_output_path in {None, ""}:
        return None
    relative_path = Path(str(raw_output_path))
    if relative_path.is_absolute():
        raise SyncError(f"Invalid output path in state file: {relative_path}")
    output_path = (config.output_root / relative_path).resolve()
    try:
        output_path.relative_to(config.output_root)
    except ValueError as exc:
        raise SyncError(f"Invalid output path in state file: {relative_path}") from exc
    return output_path


def _source_kind_from_state(
    state_entry: dict[str, object] | None,
) -> Literal["pdf", "web", "none"]:
    source_kind = state_entry.get("source_kind") if state_entry else None
    if source_kind in {"pdf", "web", "none"}:
        return source_kind
    return "none"


def _extract_item_content(
    *, item: ZoteroItem, client: ZoteroClient
) -> ExtractionResult:
    if item.pdf_attachment_key:
        try:
            with TemporaryDirectory(prefix="zotero-to-md-") as temp_dir:
                downloaded_pdf = client.download_pdf_attachment(
                    item.pdf_attachment_key,
                    Path(temp_dir) / f"{item.item_key}.pdf",
                )
                extracted = extract_pdf_text(downloaded_pdf)
                if extracted.strip():
                    return ExtractionResult(
                        source_kind="pdf", status="ok", text=extracted.strip()
                    )
                pdf_error = "PDF extracted but had no readable text."
        except Exception as exc:
            pdf_error = f"PDF extraction failed: {exc}"

        if item.url:
            web_text, web_error = _safe_extract_web_text(item.url)
            if web_text:
                return ExtractionResult(
                    source_kind="web", status="ok", text=web_text.strip()
                )
            error_text = _error_body(
                web_error or "Web extraction failed.", url=item.url
            )
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
        web_text, web_error = _safe_extract_web_text(item.url)
        if web_text:
            return ExtractionResult(
                source_kind="web", status="ok", text=web_text.strip()
            )
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


def _safe_extract_web_text(url: str) -> tuple[str | None, str | None]:
    try:
        return extract_web_text(url)
    except Exception as exc:
        return None, f"Web extraction failed: {exc}"


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


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
