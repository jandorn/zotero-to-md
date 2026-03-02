from __future__ import annotations

from pathlib import Path

import fitz


def extract_pdf_text(pdf_path: Path) -> str:
    with fitz.open(pdf_path) as document:
        pages = [page.get_text("text") for page in document]
    return "\n\n".join(text.strip() for text in pages if text and text.strip()).strip()

