from __future__ import annotations

import logging
import re

from lxml import html
from readability import Document
import trafilatura

READABILITY_LOGGER = logging.getLogger("readability.readability")
CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def extract_web_text(url: str) -> tuple[str | None, str | None]:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None, "failed to download webpage content"
    safe_downloaded = _sanitize_html_payload(downloaded)
    if not safe_downloaded:
        return None, "downloaded webpage content is empty after sanitization"

    extracted = trafilatura.extract(
        safe_downloaded,
        include_comments=False,
        include_tables=False,
        include_links=False,
    )
    if extracted and extracted.strip():
        return extracted.strip(), None

    try:
        was_disabled = READABILITY_LOGGER.disabled
        READABILITY_LOGGER.disabled = True
        readable_html = Document(safe_downloaded).summary()
        readable_text = html.fromstring(readable_html).text_content().strip()
    except Exception as exc:
        return None, f"readability fallback failed: {exc}"
    finally:
        READABILITY_LOGGER.disabled = was_disabled
    if readable_text:
        return readable_text, None
    return None, "no readable article text found on webpage"


def _sanitize_html_payload(payload: str | bytes) -> str:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="ignore")
    return CONTROL_CHARS_PATTERN.sub("", payload)
