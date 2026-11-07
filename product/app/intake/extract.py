"""Text extraction from stored CVs (phase 2 design section 3).

- PDF: pdfminer.six (MIT) layout analysis, so two column pages read column by column.
  Page limit 20. Fewer than MIN_TEXT_CHARS readable characters = no text layer
  (scanned CV): no model call, the candidate goes to review.
- DOCX: python-docx (MIT): header, body paragraphs and tables in document order, footer.
Hidden (white or tiny) text is extracted like any other text: it is data, fenced later.
Extraction runs in a worker thread with a time limit so a hostile file cannot hang the
worker.
"""

from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from typing import Literal

MAX_PAGES = 20
MIN_TEXT_CHARS = 100
TIME_LIMIT_SECONDS = 20.0

Status = Literal["ok", "no_text_layer", "failed"]


@dataclass(frozen=True)
class Extracted:
    status: Status
    text: str
    detail: str = ""


def _pdf(data: bytes) -> str:
    from pdfminer.high_level import extract_text
    from pdfminer.layout import LAParams

    return str(extract_text(io.BytesIO(data), maxpages=MAX_PAGES, laparams=LAParams()))


def _docx(data: bytes) -> str:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(io.BytesIO(data))
    parts: list[str] = []
    for section in doc.sections:
        parts += [p.text for p in section.header.paragraphs if p.text.strip()]
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            if block.text.strip():
                parts.append(block.text)
        elif isinstance(block, Table):
            for row in block.rows:
                cells = []
                for cell in row.cells:
                    t = cell.text.strip()
                    if t and t not in cells:  # merged cells repeat their text
                        cells.append(t)
                if cells:
                    parts.append(" | ".join(cells))
    for section in doc.sections:
        parts += [p.text for p in section.footer.paragraphs if p.text.strip()]
    return "\n".join(parts)


def _readable_chars(text: str) -> int:
    return sum(ch.isalnum() for ch in text)


def extract_sync(data: bytes, media_type: str) -> Extracted:
    try:
        if media_type == "application/pdf":
            text = _pdf(data)
        elif media_type.endswith("wordprocessingml.document"):
            text = _docx(data)
        else:
            return Extracted("failed", "", f"unsupported type {media_type}")
    except Exception as exc:  # broken, encrypted or hostile files
        return Extracted("failed", "", f"could not read the CV: {type(exc).__name__}")
    text = text.replace("\x00", "").replace("\f", "\n")
    if _readable_chars(text) < MIN_TEXT_CHARS:
        return Extracted("no_text_layer", "", "no text layer (scanned CV)")
    return Extracted("ok", text)


async def extract(data: bytes, media_type: str) -> Extracted:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(extract_sync, data, media_type), TIME_LIMIT_SECONDS
        )
    except TimeoutError:
        return Extracted(
            "failed", "", f"text extraction took longer than {TIME_LIMIT_SECONDS:.0f} s"
        )
