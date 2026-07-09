"""Tests for the web-layer resume file parser. No external APIs are involved —
the parsers run on in-memory bytes we build in the test (a real DOCX round-trip)
or on deliberately malformed bytes for the error paths."""

from __future__ import annotations

import io

import pytest
from docx import Document

from resume_assistant.web.resume_upload import (
    MAX_UPLOAD_BYTES,
    ResumeUploadError,
    extract_resume_text,
)


def _docx_bytes(*paragraphs: str) -> bytes:
    """Build a real .docx in memory so the happy path exercises python-docx."""
    buffer = io.BytesIO()
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


def test_docx_round_trip_extracts_text() -> None:
    data = _docx_bytes("Built a distributed cache in Go", "Shipped a React dashboard")
    text = extract_resume_text("resume.docx", data)
    assert "Built a distributed cache in Go" in text
    assert "Shipped a React dashboard" in text


def test_empty_upload_is_rejected() -> None:
    with pytest.raises(ResumeUploadError, match="empty"):
        extract_resume_text("resume.pdf", b"")


def test_oversized_upload_is_rejected() -> None:
    with pytest.raises(ResumeUploadError, match="10 MB"):
        extract_resume_text("resume.pdf", b"x" * (MAX_UPLOAD_BYTES + 1))


def test_unsupported_extension_is_rejected() -> None:
    with pytest.raises(ResumeUploadError, match="Unsupported file type"):
        extract_resume_text("resume.txt", b"just some text")


def test_unreadable_pdf_is_wrapped_in_friendly_error() -> None:
    with pytest.raises(ResumeUploadError, match="PDF couldn't be read"):
        extract_resume_text("resume.pdf", b"this is not a real pdf")


def test_docx_with_only_whitespace_is_rejected() -> None:
    """A file that parses but yields no usable text is a friendly error, not empty output."""
    with pytest.raises(ResumeUploadError, match="Couldn't read any text"):
        extract_resume_text("resume.docx", _docx_bytes("   ", ""))
