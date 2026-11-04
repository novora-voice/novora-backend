"""Document parsing, normalization, and chunking pipeline."""
from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
import xml.etree.ElementTree as ET
from typing import List, Optional

logger = logging.getLogger(__name__)


def extract_text_from_file(content: bytes, filename: str, mime_type: str = "text/plain") -> str:
    """Extract clean raw text from uploaded document bytes based on filename extension and MIME type."""
    fn_lower = filename.lower()

    if fn_lower.endswith(".pdf") or "pdf" in mime_type:
        return _extract_pdf(content)
    elif fn_lower.endswith(".docx") or "wordprocessingml" in mime_type or "docx" in mime_type:
        return _extract_docx(content)
    elif fn_lower.endswith(".csv") or "csv" in mime_type:
        return _extract_csv(content)
    else:
        # Default to plain text / Markdown
        return _extract_plaintext(content)


def _extract_pdf(content: bytes) -> str:
    """Extract text from PDF using pypdf."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(content))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages).strip()
    except Exception as exc:
        logger.warning("pypdf parsing failed (%s); attempting fallback text extraction", exc)
        # Fallback stream text extraction
        text = re.sub(rb"[^\x20-\x7E\n\r\t]", b" ", content).decode("ascii", errors="ignore")
        return normalize_text(text)


def _extract_docx(content: bytes) -> str:
    """Extract text from DOCX by reading word/document.xml from the zip archive."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as docx_zip:
            xml_content = docx_zip.read("word/document.xml")
            tree = ET.fromstring(xml_content)
            # Find all text elements (w:t)
            texts: List[str] = []
            for node in tree.iter():
                if node.tag.endswith("}t") and node.text:
                    texts.append(node.text)
                elif node.tag.endswith("}p"):
                    texts.append("\n")
            return "".join(texts).strip()
    except Exception as exc:
        logger.warning("DOCX parsing failed: %s", exc)
        return _extract_plaintext(content)


def _extract_csv(content: bytes) -> str:
    """Extract text from CSV as structured readable lines."""
    try:
        text_stream = io.StringIO(content.decode("utf-8", errors="replace"))
        reader = csv.reader(text_stream)
        rows: List[str] = []
        headers: Optional[List[str]] = None
        for i, row in enumerate(reader):
            if not row:
                continue
            if i == 0:
                headers = row
                rows.append(", ".join(row))
            else:
                if headers and len(headers) == len(row):
                    rows.append("; ".join(f"{h}: {val}" for h, val in zip(headers, row)))
                else:
                    rows.append(", ".join(row))
        return "\n".join(rows).strip()
    except Exception as exc:
        logger.warning("CSV parsing failed: %s", exc)
        return _extract_plaintext(content)


def _extract_plaintext(content: bytes) -> str:
    """Extract text from plain text or Markdown with multi-encoding fallback."""
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return content.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace").strip()


def normalize_text(text: str) -> str:
    """Normalize extracted text: strip zero-width characters, excessive whitespace, and carriage returns."""
    if not text:
        return ""
    # Strip zero-width spaces and control chars except newlines/tabs
    cleaned = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    # Strip spaces around newlines
    cleaned = re.sub(r"[ \t]*\n[ \t]*", "\n", cleaned)
    # Collapse multiple consecutive newlines to maximum 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    # Collapse multiple consecutive spaces/tabs on the same line
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def chunk_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> List[str]:
    """Split text into overlapping chunks respecting sentence / paragraph boundaries where possible."""
    normalized = normalize_text(text)
    if not normalized:
        return []

    if len(normalized) <= chunk_size:
        return [normalized]

    chunks: List[str] = []
    start = 0
    total_len = len(normalized)

    while start < total_len:
        end = start + chunk_size

        if end >= total_len:
            chunk = normalized[start:].strip()
            if chunk:
                chunks.append(chunk)
            break

        # Look for natural break point (paragraph break, sentence end, or whitespace)
        candidate_end = end
        paragraph_break = normalized.rfind("\n\n", start, end)
        if paragraph_break > start + (chunk_size // 2):
            candidate_end = paragraph_break + 2
        else:
            sentence_break = max(
                normalized.rfind(". ", start, end),
                normalized.rfind("? ", start, end),
                normalized.rfind("! ", start, end),
            )
            if sentence_break > start + (chunk_size // 2):
                candidate_end = sentence_break + 2
            else:
                space_break = normalized.rfind(" ", start, end)
                if space_break > start + (chunk_size // 2):
                    candidate_end = space_break + 1

        chunk = normalized[start:candidate_end].strip()
        if chunk:
            chunks.append(chunk)

        # Advance start by candidate_end - chunk_overlap
        start = max(start + 1, candidate_end - chunk_overlap)

    return chunks
