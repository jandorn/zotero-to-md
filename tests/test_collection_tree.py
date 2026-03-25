from zotero_to_md.collection_tree import build_collection_path_map


def test_build_collection_path_map_recursive() -> None:
    collections = [
        {"key": "root", "data": {"name": "Masterarbeit", "parentCollection": None}},
        {
            "key": "intro",
            "data": {"name": "1. Introduction", "parentCollection": "root"},
        },
        {"key": "rw", "data": {"name": "2. Related Work", "parentCollection": "root"}},
        {"key": "sub", "data": {"name": "Subfolder", "parentCollection": "intro"}},
        {"key": "other", "data": {"name": "Other Root", "parentCollection": None}},
    ]

    result = build_collection_path_map(collections, root_key="root", recursive=True)

    assert result == {
        "root": "",
        "intro": "1. Introduction",
        "rw": "2. Related Work",
        "sub": "1. Introduction/Subfolder",
    }


def test_build_collection_path_map_non_recursive() -> None:
    collections = [
        {"key": "root", "data": {"name": "Masterarbeit", "parentCollection": None}},
        {"key": "child", "data": {"name": "Child", "parentCollection": "root"}},
    ]

    result = build_collection_path_map(collections, root_key="root", recursive=False)

    assert result == {"root": ""}
