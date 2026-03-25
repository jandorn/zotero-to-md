from zotero_to_md.zotero_client import ZoteroClient


class FakePyzoteroClient:
    def __init__(self) -> None:
        self.collections_calls = 0

    def collections(self):
        self.collections_calls += 1
        return [
            {"key": "ROOT", "data": {"name": "Masterarbeit", "parentCollection": None}},
            {
                "key": "DEMAND",
                "data": {"name": "Demand Response", "parentCollection": "ROOT"},
            },
        ]

    def collection_items(self, _collection_key: str):
        return [
            {
                "key": "ATTACH1",
                "data": {
                    "key": "ATTACH1",
                    "itemType": "attachment",
                    "parentItem": "ITEM1",
                    "contentType": "application/pdf",
                },
            },
            {
                "key": "ITEM1",
                "data": {
                    "key": "ITEM1",
                    "itemType": "journalArticle",
                    "title": "Paper",
                    "creators": [
                        {
                            "creatorType": "author",
                            "firstName": "Jane",
                            "lastName": "Doe",
                        }
                    ],
                    "collections": ["DEMAND"],
                    "tags": [{"tag": "tag-a"}],
                    "DOI": "10.1000/example",
                    "abstractNote": "Abstract",
                    "url": "https://example.com",
                },
                "library": {"key": "LIB1"},
            },
        ]


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


def test_get_all_collections_uses_cache() -> None:
    fake = FakePyzoteroClient()
    client = ZoteroClient(user_id="123", api_key="secret", client=fake)

    first = client.get_all_collections()
    second = client.get_all_collections()

    assert len(first) == 2
    assert len(second) == 2
    assert fake.collections_calls == 1


def test_fetch_items_indexes_pdf_attachments_without_children_calls() -> None:
    client = ZoteroClient(user_id="123", api_key="secret", client=FakePyzoteroClient())

    items = client.fetch_items({"ROOT": "", "DEMAND": "Demand Response"})

    assert len(items) == 1
    item = items[0]
    assert item.pdf_attachment_key == "ATTACH1"
    assert item.tags == ["tag-a"]
    assert item.doi == "10.1000/example"
    assert item.abstract == "Abstract"
    assert item.zotero_library_key == "LIB1"
