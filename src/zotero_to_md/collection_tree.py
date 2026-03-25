from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


def build_collection_path_map(
    collections: list[dict[str, Any]],
    *,
    root_key: str,
    recursive: bool,
) -> dict[str, str]:
    collection_by_key = {item["key"]: item for item in collections if item.get("key")}
    if root_key not in collection_by_key:
        raise ValueError(f"Root collection key not found: {root_key}")

    path_map: dict[str, str] = {root_key: ""}
    if not recursive:
        return path_map

    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for collection in collections:
        data = collection.get("data", {})
        child_key = collection.get("key")
        parent_key = data.get("parentCollection")
        if child_key and parent_key:
            children_by_parent[parent_key].append(child_key)

    queue: deque[str] = deque([root_key])
    while queue:
        parent_key = queue.popleft()
        child_keys = sorted(
            children_by_parent.get(parent_key, []),
            key=lambda key: collection_by_key[key].get("data", {}).get("name", ""),
        )
        for child_key in child_keys:
            name = (
                collection_by_key[child_key].get("data", {}).get("name")
                or "unnamed-collection"
            )
            parent_path = path_map[parent_key]
            path_map[child_key] = f"{parent_path}/{name}" if parent_path else name
            queue.append(child_key)

    return path_map
