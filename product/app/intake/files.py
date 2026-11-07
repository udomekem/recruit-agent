"""CV file checks. The file's content decides what it is; the name and the browser's
stated type are never trusted.

- PDF: starts with the PDF signature, name ends in .pdf
- DOCX: a zip with a Word document part, not macro enabled, name ends in .docx;
  zip limits stop zip bombs
- size: at most `cv_max_bytes` (5 MB default)
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MAX_ZIP_ENTRIES = 1000
MAX_ZIP_UNCOMPRESSED = 50 * 1024 * 1024


class CVRejected(ValueError):
    pass


@dataclass(frozen=True)
class CheckedCV:
    data: bytes
    media_type: str
    original_name: str


def _safe_name(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
    clean = "".join(ch for ch in base if ch.isalnum() or ch in "._- ")[:200]
    return clean or "cv"


def check_cv(data: bytes, filename: str, max_bytes: int) -> CheckedCV:
    if not data:
        raise CVRejected("the CV file is empty")
    if len(data) > max_bytes:
        raise CVRejected(f"the CV is larger than {max_bytes // (1024 * 1024)} MB")
    name = _safe_name(filename)
    lower = name.lower()
    if data.startswith(b"%PDF-"):
        if not lower.endswith(".pdf"):
            raise CVRejected("the file is a PDF but its name does not end in .pdf")
        return CheckedCV(data, PDF, name)
    if data.startswith(b"PK\x03\x04"):
        if not lower.endswith(".docx"):
            raise CVRejected("only .docx Word files are accepted (not .docm, .doc or other zips)")
        _check_docx(data)
        return CheckedCV(data, DOCX, name)
    raise CVRejected("the CV must be a PDF or a Word .docx file")


def _check_docx(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ZIP_ENTRIES:
                raise CVRejected("the Word file has too many parts")
            if sum(i.file_size for i in infos) > MAX_ZIP_UNCOMPRESSED:
                raise CVRejected("the Word file is too large when unpacked")
            names = {i.filename for i in infos}
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                raise CVRejected("the file is not a Word document")
            types = zf.read("[Content_Types].xml").decode("utf-8", errors="replace")
            if "macroEnabled" in types or "word/vbaProject.bin" in names:
                raise CVRejected("Word files with macros are not accepted")
            if "wordprocessingml.document.main+xml" not in types:
                raise CVRejected("the file is not a Word document")
    except zipfile.BadZipFile as exc:
        raise CVRejected("the Word file is damaged") from exc
