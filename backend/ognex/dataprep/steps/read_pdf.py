"""PDF extraction with per-page provenance tags.

Every page starts with ``<reference>file.pdf, page N</reference>``. Those tags
survive chunking, are stripped before the prompt is built, and are turned back
into the reference list shown under each answer.
"""

from __future__ import annotations

import os
import re

import pymupdf

from ognex.dataprep.common.text import normalize_text


def extract_pages(pdf_path: str) -> list[str]:
    file_name = os.path.basename(pdf_path)
    pages: list[str] = []

    document = pymupdf.open(pdf_path)
    try:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text", sort=True) or ""
            text = _strip_running_headers(text)
            reference = f"<reference>{file_name}, page {page_number}</reference>"
            pages.append(f"{reference}\n{text}".strip())
    finally:
        document.close()

    return pages


def _strip_running_headers(text: str) -> str:
    """Remove obvious repeated page furniture (page numbers, blank lines)."""
    lines = [line.strip() for line in text.splitlines()]
    kept = [line for line in lines if line and not re.fullmatch(r"[-–—\s]*\d{1,4}[-–—\s]*", line)]
    return "\n".join(kept)


def combine_pages(pages: list[str]) -> str:
    return normalize_text("\n".join(pages))