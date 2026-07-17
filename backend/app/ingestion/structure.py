"""Structure-aware parsing of Tulsa agenda/minutes PDFs.

Replaces fixed-token-window chunking ("chunk soup"): the unit of
retrieval is the agenda item. Each parsed item keeps its item number,
title, full text, and page span; chunks are only split further when an
item exceeds the token budget, and every chunk is prefixed with its
parent context (body, meeting date, item number, title) so no chunk
ever loses its legislative identity.
"""

import hashlib
import io
import logging
import re
from dataclasses import dataclass, field

import pdfplumber

logger = logging.getLogger(__name__)

try:
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover - tiktoken ships in requirements
    _ENCODING = None

# Item headings in Tulsa council agendas/minutes. Ordered: most specific
# first. Examples matched:
#   "4.a. 25-123-2 Ordinance amending Title 42 ..."
#   "2.B."  /  "12." / "3)" section items
ITEM_PATTERNS = [
    re.compile(r"^\s*(\d{1,3}\.[a-zA-Z](?:\.\d{1,3})?)[.)]?\s+(.*)"),
    re.compile(r"^\s*(\d{1,3})[.)]\s+(.{4,})"),
]

# Section banners that group items (kept as item context, not items)
SECTION_RE = re.compile(
    r"^\s*(CONSENT AGENDA|UNFINISHED BUSINESS|NEW BUSINESS|PUBLIC HEARING[S]?|"
    r"MAYOR'S ITEMS|COUNCIL ITEMS|CITY COUNCIL ANNOUNCEMENTS|ADJOURNMENT)\b",
    re.I,
)

ORDINANCE_RE = re.compile(
    r"\b(?:Ordinance|Resolution)\s+(?:No\.?\s*)?(\d{4,6})\b", re.I
)


@dataclass
class ParsedItem:
    item_number: str
    title: str
    text: str
    page_start: int
    page_end: int
    section: str | None = None
    ordinance_numbers: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    pages: list[str]
    items: list[ParsedItem]
    preamble: str  # Text before the first item (notice, call to order...)


def extract_pages(pdf_bytes: bytes) -> list[str]:
    """Per-page text via pdfplumber (layout-preserving enough for
    line-based grammar)."""
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return pages


def item_hash(external_id: str, item_number: str, title: str) -> str:
    """Stable identity across re-scrapes."""
    normalized = re.sub(r"\s+", " ", title).strip().lower()
    return hashlib.sha256(
        f"{external_id}|{item_number}|{normalized}".encode()
    ).hexdigest()


def _match_item(line: str) -> tuple[str, str] | None:
    for pattern in ITEM_PATTERNS:
        m = pattern.match(line)
        if m:
            number, rest = m.group(1), m.group(2).strip()
            # Guard against prose lines that start with a number
            # ("2025 budget includes...") — require a short number token.
            if len(number) <= 8:
                return number, rest
    return None


def parse_structure(pages: list[str]) -> ParsedDocument:
    """Line-based grammar over per-page text -> agenda-item tree."""
    items: list[ParsedItem] = []
    preamble_lines: list[str] = []
    current: ParsedItem | None = None
    current_section: str | None = None

    for page_index, page_text in enumerate(pages, start=1):
        for line in page_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            section_match = SECTION_RE.match(stripped)
            if section_match:
                current_section = section_match.group(1).title()
                continue

            matched = _match_item(stripped)
            if matched:
                if current:
                    items.append(current)
                number, title = matched
                current = ParsedItem(
                    item_number=number.rstrip("."),
                    title=title,
                    text=stripped,
                    page_start=page_index,
                    page_end=page_index,
                    section=current_section,
                )
            elif current:
                current.text += "\n" + stripped
                current.page_end = page_index
            else:
                preamble_lines.append(stripped)

    if current:
        items.append(current)

    for item in items:
        item.ordinance_numbers = list(dict.fromkeys(ORDINANCE_RE.findall(item.text)))

    return ParsedDocument(pages=pages, items=items, preamble="\n".join(preamble_lines))


def _token_count(text: str) -> int:
    if _ENCODING:
        return len(_ENCODING.encode(text))
    return max(1, len(text) // 4)


def _split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


@dataclass
class ItemChunk:
    content: str
    item_number: str | None
    page_start: int | None
    page_end: int | None
    chunk_index: int


def chunk_items(
    parsed: ParsedDocument,
    context_header: str,
    max_tokens: int = 1200,
) -> list[ItemChunk]:
    """One or more chunks per agenda item, each carrying parent context.

    context_header example:
      "City Council — Regular Meeting, 2026-07-01"
    Every chunk starts with the header + item number + title so it
    remains self-identifying wherever retrieval surfaces it.
    """
    chunks: list[ItemChunk] = []
    index = 0

    if parsed.preamble.strip():
        content = f"{context_header}\n{parsed.preamble.strip()}"
        chunks.append(
            ItemChunk(
                content=content,
                item_number=None,
                page_start=1,
                page_end=1,
                chunk_index=index,
            )
        )
        index += 1

    for item in parsed.items:
        header = f"{context_header}\nItem {item.item_number}: {item.title}"
        if item.section:
            header += f" ({item.section})"
        body = item.text

        if _token_count(f"{header}\n{body}") <= max_tokens:
            parts = [body]
        else:
            parts = []
            piece: list[str] = []
            for sentence in _split_sentences(body):
                candidate = " ".join([*piece, sentence])
                if piece and _token_count(f"{header}\n{candidate}") > max_tokens:
                    parts.append(" ".join(piece))
                    piece = [sentence]
                else:
                    piece.append(sentence)
            if piece:
                parts.append(" ".join(piece))

        for part in parts:
            chunks.append(
                ItemChunk(
                    content=f"{header}\n{part}",
                    item_number=item.item_number,
                    page_start=item.page_start,
                    page_end=item.page_end,
                    chunk_index=index,
                )
            )
            index += 1

    return chunks
