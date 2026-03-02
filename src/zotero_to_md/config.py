from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from zotero_to_md.errors import ConfigError
from zotero_to_md.models import AppConfig


def load_config(
    *,
    target_repo_path: Path,
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

    resolved_target = target_repo_path.expanduser().resolve()
    if not resolved_target.exists():
        raise ConfigError(f"Target repo path does not exist: {resolved_target}")
    if not resolved_target.is_dir():
        raise ConfigError(f"Target repo path is not a directory: {resolved_target}")

    root_name = root_collection.strip()
    if not root_name:
        raise ConfigError("Root collection name must not be empty.")

    return AppConfig(
        zotero_user_id=zotero_user_id,
        zotero_api_key=zotero_api_key,
        target_repo_path=resolved_target,
        root_collection=root_name,
        recursive=recursive,
        dry_run=dry_run,
        verbose=verbose,
    )

