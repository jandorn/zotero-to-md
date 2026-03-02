from __future__ import annotations

from lxml import html
from readability import Document
import trafilatura


def extract_web_text(url: str) -> tuple[str | None, str | None]:
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        return None, "failed to download webpage content"

    extracted = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=False,
        include_links=False,
    )
    if extracted and extracted.strip():
        return extracted.strip(), None

    try:
        readable_html = Document(downloaded).summary()
        readable_text = html.fromstring(readable_html).text_content().strip()
    except Exception as exc:
        return None, f"readability fallback failed: {exc}"
    if readable_text:
        return readable_text, None
    return None, "no readable article text found on webpage"

