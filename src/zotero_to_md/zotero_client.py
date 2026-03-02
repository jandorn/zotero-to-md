from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from pyzotero import zotero

from zotero_to_md.collection_tree import build_collection_path_map
from zotero_to_md.errors import ZoteroClientError
from zotero_to_md.models import ZoteroItem

EXCLUDED_ITEM_TYPES = {"attachment", "note", "annotation"}


class ZoteroClient:
    def __init__(
        self,
        *,
        user_id: str,
        api_key: str,
        library_type: str = "user",
        client: Any | None = None,
    ) -> None:
        self._zot = client or zotero.Zotero(user_id, library_type, api_key)

    def _everything(self, endpoint_result: Any) -> list[dict[str, Any]]:
        everything = getattr(self._zot, "everything", None)
        if callable(everything):
            return list(everything(endpoint_result))
        return list(endpoint_result)

    def get_all_collections(self) -> list[dict[str, Any]]:
        try:
            return self._everything(self._zot.collections())
        except Exception as exc:  # pragma: no cover - external service behavior
            raise ZoteroClientError(f"Failed to fetch Zotero collections: {exc}") from exc

    def find_collection_by_name(self, name: str) -> dict[str, Any]:
        collections = self.get_all_collections()
        matches = [c for c in collections if c.get("data", {}).get("name") == name]
        if not matches:
            raise ZoteroClientError(f'Collection "{name}" not found.')
        if len(matches) > 1:
            raise ZoteroClientError(f'Collection "{name}" is ambiguous ({len(matches)} matches).')
        return matches[0]

    def build_collection_path_map(self, *, root_key: str, recursive: bool) -> dict[str, str]:
        collections = self.get_all_collections()
        try:
            return build_collection_path_map(collections, root_key=root_key, recursive=recursive)
        except ValueError as exc:
            raise ZoteroClientError(str(exc)) from exc

    def fetch_items(self, collection_path_map: dict[str, str]) -> list[ZoteroItem]:
        by_item_key: dict[str, ZoteroItem] = {}
        for collection_key in collection_path_map:
            try:
                raw_items = self._everything(self._zot.collection_items(collection_key))
            except Exception as exc:  # pragma: no cover - external service behavior
                raise ZoteroClientError(
                    f"Failed to fetch collection items for {collection_key}: {exc}"
                ) from exc
            for raw_item in raw_items:
                data = raw_item.get("data", {})
                item_type = data.get("itemType", "")
                if item_type in EXCLUDED_ITEM_TYPES:
                    continue
                item_key = raw_item.get("key") or data.get("key")
                if not item_key:
                    continue

                collection_path = self._resolve_item_collection_path(
                    item_collections=data.get("collections", []),
                    collection_path_map=collection_path_map,
                )
                existing = by_item_key.get(item_key)
                if existing:
                    if self._is_preferred_path(collection_path, existing.collection_path):
                        existing.collection_path = collection_path
                    continue

                by_item_key[item_key] = ZoteroItem(
                    item_key=item_key,
                    title=(data.get("title") or "").strip() or "untitled",
                    authors=_extract_authors(data.get("creators", [])),
                    year=_extract_year(data.get("date")),
                    url=((data.get("url") or "").strip() or None),
                    collection_path=collection_path,
                    pdf_attachment_key=self.find_pdf_attachment_key(item_key),
                )

        return sorted(
            by_item_key.values(),
            key=lambda item: (item.collection_path, item.title.lower(), item.item_key),
        )

    def find_pdf_attachment_key(self, parent_item_key: str) -> str | None:
        try:
            children = self._everything(self._zot.children(parent_item_key))
        except Exception:  # pragma: no cover - external service behavior
            return None
        for child in children:
            data = child.get("data", {})
            if data.get("itemType") != "attachment":
                continue
            content_type = (data.get("contentType") or "").lower()
            if "pdf" not in content_type:
                continue
            return child.get("key") or data.get("key")
        return None

    def download_pdf_attachment(self, attachment_key: str, destination_path: Path) -> Path:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        dump = getattr(self._zot, "dump", None)
        if callable(dump):
            try:
                dump(attachment_key, filename=destination_path.name, path=str(destination_path.parent))
            except TypeError:
                dump(attachment_key, destination_path.name, str(destination_path.parent))
            except Exception:
                pass
            if destination_path.exists():
                return destination_path

        file_fetcher = getattr(self._zot, "file", None)
        if callable(file_fetcher):
            payload = file_fetcher(attachment_key)
            if hasattr(payload, "read"):
                destination_path.write_bytes(payload.read())
                return destination_path
            if isinstance(payload, bytes):
                destination_path.write_bytes(payload)
                return destination_path
            if isinstance(payload, str):
                source_path = Path(payload)
                if source_path.exists():
                    shutil.copyfile(source_path, destination_path)
                    return destination_path

        raise ZoteroClientError(f"Could not download PDF attachment for key {attachment_key}.")

    @staticmethod
    def _resolve_item_collection_path(
        *,
        item_collections: list[str],
        collection_path_map: dict[str, str],
    ) -> str:
        paths = [collection_path_map[key] for key in item_collections if key in collection_path_map]
        if not paths:
            return ""
        return min(paths, key=lambda path: (path.count("/"), len(path), path))

    @staticmethod
    def _is_preferred_path(candidate: str, existing: str) -> bool:
        return (candidate.count("/"), len(candidate), candidate) < (
            existing.count("/"),
            len(existing),
            existing,
        )


def _extract_authors(creators: list[dict[str, Any]]) -> list[str]:
    authors: list[str] = []
    for creator in creators:
        creator_type = creator.get("creatorType")
        if creator_type not in {"author", "editor"}:
            continue
        author = _creator_to_name(creator)
        if author:
            authors.append(author)
    if authors:
        return authors

    for creator in creators:
        author = _creator_to_name(creator)
        if author:
            authors.append(author)
    return authors


def _creator_to_name(creator: dict[str, Any]) -> str | None:
    if creator.get("name"):
        return str(creator["name"]).strip() or None
    first = str(creator.get("firstName", "")).strip()
    last = str(creator.get("lastName", "")).strip()
    if first and last:
        return f"{first} {last}"
    if last:
        return last
    if first:
        return first
    return None


def _extract_year(raw_date: Any) -> str | None:
    if raw_date is None:
        return None
    match = re.search(r"(19|20)\d{2}", str(raw_date))
    return match.group(0) if match else None

