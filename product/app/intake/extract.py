"""Text extraction from stored CVs (phase 2 design section 3).

- PDF: pdfminer.six (MIT) layout analysis, so two column pages read column by column.
  Page limit 20. Fewer than MIN_TEXT_CHARS readable characters = no text layer
  (scanned CV): no model call, the candidate goes to review.
- DOCX: python-docx (MIT): header, body paragraphs and tables in document order, footer.
Hidden text (phase 3 design section 5) is removed and counted: PDF characters filled white
(unless they sit on a dark filled shape, such as a coloured header band) or under 3 pt;
DOCX runs with the hidden (vanish) property or a white font colour. Invisible claims can
then never be quoted as evidence by the scorer.
Extraction runs in a worker thread with a time limit so a hostile file cannot hang the
worker.
"""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass
from typing import Any, Literal

MAX_PAGES = 20
MIN_TEXT_CHARS = 100
TIME_LIMIT_SECONDS = 20.0
MIN_VISIBLE_PT = 3.0
WHITE_MIN = 0.95  # every RGB or grey channel at least this: treated as white

Status = Literal["ok", "no_text_layer", "failed"]
Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Extracted:
    status: Status
    text: str
    detail: str = ""
    hidden_chars: int = 0


def _is_white(color: Any) -> bool:
    if color is None:
        return False
    vals = color if isinstance(color, (list, tuple)) else (color,)
    try:
        nums = [float(v) for v in vals]
    except (TypeError, ValueError):
        return False  # pattern or named colour space: assume visible
    if len(nums) == 1:
        return nums[0] >= WHITE_MIN
    if len(nums) == 3:
        return all(v >= WHITE_MIN for v in nums)
    if len(nums) == 4:  # CMYK: white is no ink
        return all(v <= 1 - WHITE_MIN for v in nums)
    return False


def _dark_shapes(page: Any) -> list[Box]:
    from pdfminer.layout import LTContainer, LTCurve

    found: list[Box] = []

    def walk(item: Any) -> None:
        if (
            isinstance(item, LTCurve)
            and getattr(item, "fill", False)
            and not _is_white(getattr(item, "non_stroking_color", None))
        ):
            found.append(item.bbox)
        if isinstance(item, LTContainer):
            for child in item:
                walk(child)

    walk(page)
    return found


def _on_dark(bbox: Box, shapes: list[Box]) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return any(x0 <= cx <= x1 and y0 <= cy <= y1 for x0, y0, x1, y1 in shapes)


def _pdf_hidden(ch: Any, shapes: list[Box]) -> bool:
    if ch.size < MIN_VISIBLE_PT:
        return True
    color = getattr(getattr(ch, "graphicstate", None), "ncolor", None)
    return _is_white(color) and not _on_dark(ch.bbox, shapes)


def _pdf(data: bytes) -> tuple[str, int]:
    """Same output as pdfminer's extract_text, minus hidden characters."""
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTChar, LTContainer, LTText, LTTextBox

    out: list[str] = []
    hidden = 0

    def render(item: Any, shapes: list[Box]) -> None:
        nonlocal hidden
        if isinstance(item, LTContainer):
            for child in item:
                render(child, shapes)
        elif isinstance(item, LTChar):
            if _pdf_hidden(item, shapes):
                hidden += len(item.get_text().strip())
            else:
                out.append(item.get_text())
        elif isinstance(item, LTText):
            out.append(item.get_text())
        if isinstance(item, LTTextBox):
            out.append("\n")

    for page in extract_pages(io.BytesIO(data), maxpages=MAX_PAGES, laparams=LAParams()):
        render(page, _dark_shapes(page))
        out.append("\f")
    # a line whose characters were all hidden leaves only spaces behind
    text = re.sub(r"[ \t]+\n", "\n", "".join(out))
    return text, hidden


def _run_hidden(run: Any) -> bool:
    font = run.font
    if font.hidden:
        return True
    try:
        rgb = font.color.rgb if font.color is not None and font.color.type is not None else None
    except (AttributeError, ValueError):
        rgb = None
    return rgb is not None and str(rgb).upper() in {"FFFFFF", "FEFEFE"}


def _para_text(p: Any) -> tuple[str, int]:
    from docx.text.hyperlink import Hyperlink
    from docx.text.run import Run

    parts: list[str] = []
    hidden = 0
    for item in p.iter_inner_content():
        if isinstance(item, Hyperlink):
            runs = list(item.runs)
        elif isinstance(item, Run):
            runs = [item]
        else:
            runs = []
        for run in runs:
            if _run_hidden(run):
                hidden += len(run.text.strip())
            else:
                parts.append(run.text)
    return "".join(parts), hidden


def _docx(data: bytes) -> tuple[str, int]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(io.BytesIO(data))
    parts: list[str] = []
    hidden = 0

    def paras(ps: Any) -> None:
        nonlocal hidden
        for p in ps:
            t, h = _para_text(p)
            hidden += h
            if t.strip():
                parts.append(t)

    for section in doc.sections:
        paras(section.header.paragraphs)
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            paras([block])
        elif isinstance(block, Table):
            for row in block.rows:
                cells: list[str] = []
                for cell in row.cells:
                    texts = []
                    for p in cell.paragraphs:
                        t, h = _para_text(p)
                        hidden += h
                        texts.append(t)
                    t = "\n".join(texts).strip()
                    if t and t not in cells:  # merged cells repeat their text
                        cells.append(t)
                if cells:
                    parts.append(" | ".join(cells))
    for section in doc.sections:
        paras(section.footer.paragraphs)
    return "\n".join(parts), hidden


def _readable_chars(text: str) -> int:
    return sum(ch.isalnum() for ch in text)


def extract_sync(data: bytes, media_type: str) -> Extracted:
    try:
        if media_type == "application/pdf":
            text, hidden = _pdf(data)
        elif media_type.endswith("wordprocessingml.document"):
            text, hidden = _docx(data)
        else:
            return Extracted("failed", "", f"unsupported type {media_type}")
    except Exception as exc:  # broken, encrypted or hostile files
        return Extracted("failed", "", f"could not read the CV: {type(exc).__name__}")
    text = text.replace("\x00", "").replace("\f", "\n")
    if _readable_chars(text) < MIN_TEXT_CHARS:
        return Extracted("no_text_layer", "", "no text layer (scanned CV)", hidden)
    return Extracted("ok", text, hidden_chars=hidden)


async def extract(data: bytes, media_type: str) -> Extracted:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(extract_sync, data, media_type), TIME_LIMIT_SECONDS
        )
    except TimeoutError:
        return Extracted(
            "failed", "", f"text extraction took longer than {TIME_LIMIT_SECONDS:.0f} s"
        )
