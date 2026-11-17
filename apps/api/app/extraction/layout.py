"""Positioned words and line grouping, independent of the PDF library.

The parser works on `Page` objects so tests can feed it word lists (with coordinates) without a PDF.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float


@dataclass
class Line:
    words: list[Word]

    @property
    def top(self) -> float:
        return min(w.top for w in self.words)

    @property
    def bottom(self) -> float:
        return max(w.bottom for w in self.words)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class Page:
    width: float
    height: float
    words: list[Word] = field(default_factory=list)

    def lines(self, tolerance: float = 2.0) -> list[Line]:
        return group_lines(self.words, tolerance)


class PdfReadError(Exception):
    """The bytes could not be opened as a PDF."""


def group_lines(words: list[Word], tolerance: float = 2.0) -> list[Line]:
    """Group words whose `top` is within `tolerance` points into lines, top to bottom, left to right."""
    lines: list[Line] = []
    current: list[Word] = []
    current_top = 0.0
    for word in sorted(words, key=lambda w: (w.top, w.x0)):
        if current and abs(word.top - current_top) > tolerance:
            lines.append(Line(sorted(current, key=lambda w: w.x0)))
            current = []
        if not current:
            current_top = word.top
        current.append(word)
    if current:
        lines.append(Line(sorted(current, key=lambda w: w.x0)))
    return lines


def read_pdf_pages(pdf_bytes: bytes) -> list[Page]:
    """Open a PDF and return its pages as positioned words. Raises PdfReadError on unreadable input."""
    import pdfplumber  # local import keeps the parser importable without touching pdfminer

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages: list[Page] = []
            for page in pdf.pages:
                words = [
                    Word(
                        text=w["text"],
                        x0=float(w["x0"]),
                        x1=float(w["x1"]),
                        top=float(w["top"]),
                        bottom=float(w["bottom"]),
                    )
                    for w in page.extract_words()
                ]
                pages.append(Page(width=float(page.width), height=float(page.height), words=words))
            return pages
    except Exception as exc:  # pdfminer raises a variety of exception types for broken input
        raise PdfReadError(str(exc) or type(exc).__name__) from exc


def normalize(text: str) -> str:
    """Upper-case, strip accents and collapse whitespace (for comparing labels and titles)."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip().upper()


_ACCENT_CLASSES = {
    "a": "aá",
    "e": "eé",
    "i": "ií",
    "o": "oó",
    "u": "uúü",
    "n": "nñ",
}


def label_pattern(label: str) -> str:
    """Regex source for a printed label, tolerant of accents and spacing. Use with re.IGNORECASE."""
    parts: list[str] = []
    for char in label:
        lower = char.lower()
        base = normalize(lower).lower() or lower
        if char.isspace():
            parts.append(r"\s*")
        elif base in _ACCENT_CLASSES:
            parts.append(f"[{_ACCENT_CLASSES[base]}]")
        else:
            parts.append(re.escape(char))
    return "".join(parts)
