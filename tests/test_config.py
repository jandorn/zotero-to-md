from pathlib import Path

import pytest

from zotero_to_md.config import load_config
from zotero_to_md.errors import ConfigError


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZOTERO_API_KEY", "secret")
    monkeypatch.setenv("ZOTERO_USER_ID", "12345")


def test_load_config_requires_absolute_target_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)

    with pytest.raises(ConfigError, match="must be absolute"):
        load_config(
            target_destination_path=Path("relative/output"),
            root_collection="Root Collection",
            recursive=True,
            dry_run=False,
            verbose=False,
        )


def test_load_config_rejects_empty_root_collection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_env(monkeypatch)

    with pytest.raises(ConfigError, match="must not be empty"):
        load_config(
            target_destination_path=tmp_path / "output",
            root_collection="   ",
            recursive=True,
            dry_run=False,
            verbose=False,
        )
