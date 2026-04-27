"""
doc_extractor.py
────────────────
Utility functions for extracting text content from uploaded files
(PDF and DOCX) so the LLM can ingest historical R&D claim data.

Supports:
  - PDF  → via PyPDF2
  - DOCX → via docx2txt
  - TXT  → plain UTF-8 decode

All functions accept raw bytes (from st.file_uploader.read()) and return
a plain-text string.
"""

from __future__ import annotations

import io


def extract_text_from_upload(file_bytes: bytes, file_name: str) -> str:
    """
    Detect file type by extension and extract readable text.

    Args:
        file_bytes: Raw bytes from the uploaded file.
        file_name:  Original filename (used for extension detection).

    Returns:
        Extracted plain-text string.  Returns an error message string
        (rather than raising) if the format is unsupported or a library
        is missing, so callers can display it in the UI without crashing.
    """
    name_lower = file_name.lower() if file_name else ""

    if name_lower.endswith(".pdf"):
        return _extract_pdf(file_bytes)
    elif name_lower.endswith(".docx"):
        return _extract_docx(file_bytes)
    elif name_lower.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="replace")
    else:
        return (
            f"[Unsupported file type: '{file_name}'. "
            "Please upload a PDF, DOCX, or TXT file.]"
        )


def _extract_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF using PyPDF2."""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        return "[Error: PyPDF2 is not installed. Run: pip install PyPDF2]"

    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text)
    return "\n\n".join(pages_text) if pages_text else "[No extractable text found in the PDF.]"


def _extract_docx(file_bytes: bytes) -> str:
    """Extract text from a DOCX using docx2txt."""
    try:
        import docx2txt
    except ImportError:
        return "[Error: docx2txt is not installed. Run: pip install docx2txt]"

    text = docx2txt.process(io.BytesIO(file_bytes))
    return text.strip() if text else "[No extractable text found in the DOCX.]"
