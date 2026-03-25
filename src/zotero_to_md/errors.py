class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


class ZoteroClientError(Exception):
    """Raised when Zotero API operations fail."""


class SyncError(Exception):
    """Raised for sync pipeline failures."""
