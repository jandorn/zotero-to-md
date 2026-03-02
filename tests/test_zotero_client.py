from zotero_to_md.zotero_client import ZoteroClient


def test_resolve_item_collection_path_prefers_deeper_path() -> None:
    path = ZoteroClient._resolve_item_collection_path(
        item_collections=["ROOT", "DEMAND"],
        collection_path_map={
            "ROOT": "",
            "DEMAND": "Demand Response",
        },
        fallback_collection_key="ROOT",
    )
    assert path == "Demand Response"


def test_resolve_item_collection_path_uses_fallback_collection_key() -> None:
    path = ZoteroClient._resolve_item_collection_path(
        item_collections=[],
        collection_path_map={
            "ROOT": "",
            "INDUSTRIAL": "industrial flexibility",
        },
        fallback_collection_key="INDUSTRIAL",
    )
    assert path == "industrial flexibility"

