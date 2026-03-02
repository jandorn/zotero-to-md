from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from zotero_to_md.errors import ConfigError
from zotero_to_md.models import AppConfig


def load_config(
    *,
    target_destination_path: Path,
    root_collection: str,
    recursive: bool,
    dry_run: bool,
    verbose: bool,
) -> AppConfig:
    load_dotenv()

    zotero_api_key = os.getenv("ZOTERO_API_KEY", "").strip()
    zotero_user_id = os.getenv("ZOTERO_USER_ID", "").strip()

    if not zotero_api_key:
        raise ConfigError("Missing ZOTERO_API_KEY in environment.")
    if not zotero_user_id:
        raise ConfigError("Missing ZOTERO_USER_ID in environment.")

    expanded_destination = target_destination_path.expanduser()
    if not expanded_destination.is_absolute():
        raise ConfigError("Target destination path must be absolute.")
    resolved_destination = expanded_destination.resolve()
    if resolved_destination.exists() and not resolved_destination.is_dir():
        raise ConfigError(f"Target destination path is not a directory: {resolved_destination}")

    root_name = root_collection.strip()
    if not root_name:
        raise ConfigError("Root collection name must not be empty.")

    return AppConfig(
        zotero_user_id=zotero_user_id,
        zotero_api_key=zotero_api_key,
        target_destination_path=resolved_destination,
        root_collection=root_name,
        recursive=recursive,
        dry_run=dry_run,
        verbose=verbose,
    )
