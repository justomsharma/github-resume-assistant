"""Turn an uploaded resume file (PDF or DOCX) into plain text.

This is a web-layer input adapter, not business logic: it converts bytes the
browser uploaded into the ``resume_text`` string the engine already expects, so
``core/`` stays untouched and unaware that a file was ever involved
(docs/ARCHITECTURE.md — ``core/`` is pure). Parse failures raise
``ResumeUploadError`` with a friendly message the route can show as-is.
"""

from __future__ import annotations

import os
from io import BytesIO

import docx
from pypdf import PdfReader

# The landing UI advertises a 10 MB cap (mockup); enforce it here so a huge or
# malicious upload never reaches the parsers.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_SUPPORTED_EXTENSIONS = (".pdf", ".docx")


class ResumeUploadError(ValueError):
    """An uploaded resume couldn't be read into usable text."""


def extract_resume_text(filename: str, data: bytes) -> str:
    """Extract the resume's text from an uploaded PDF or DOCX.

    ``filename`` is only used to pick the parser by extension; ``data`` is the
    raw file bytes. Raises ``ResumeUploadError`` for an empty upload, an
    oversized file, an unsupported type, or a file that parses to no text.
    """
    if not data:
        raise ResumeUploadError("The uploaded file is empty. Choose a resume file and try again.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ResumeUploadError("That file is larger than the 10 MB limit. Upload a smaller file.")

    extension = os.path.splitext(filename)[1].lower()
    if extension == ".pdf":
        text = _extract_pdf(data)
    elif extension == ".docx":
        text = _extract_docx(data)
    else:
        raise ResumeUploadError("Unsupported file type. Upload a PDF or DOCX resume.")

    text = text.strip()
    if not text:
        raise ResumeUploadError(
            "Couldn't read any text from that file — it may be a scanned image or empty. "
            "Upload a text-based PDF or DOCX."
        )
    return text


def _extract_pdf(data: bytes) -> str:
    """Join the text of every page in a PDF. Wraps parse errors as friendly ones."""
    try:
        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # pypdf raises a range of errors on malformed PDFs
        raise ResumeUploadError(
            "That PDF couldn't be read. Try re-exporting it, or upload a DOCX."
        ) from exc


def _extract_docx(data: bytes) -> str:
    """Join the text of every paragraph in a DOCX. Wraps parse errors as friendly ones."""
    try:
        document = docx.Document(BytesIO(data))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except Exception as exc:  # python-docx raises on non-DOCX / corrupt archives
        raise ResumeUploadError(
            "That DOCX couldn't be read. Try re-saving it, or upload a PDF."
        ) from exc
