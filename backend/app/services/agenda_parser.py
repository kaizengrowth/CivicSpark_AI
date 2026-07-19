"""Structure-aware parsing of council agendas and minutes.

Fixed-size token windows lose legislative identity — "what did Council
decide on item 2.a?" cannot be answered from anonymous chunk soup. This
parser recovers the agenda tree from extracted text so documents can be
chunked by agenda item, with the item number and title kept as metadata
on every chunk.

The format targeted is the common US council agenda/minutes shape
(Granicus/Legistar exports, which Tulsa's TGOV uses): numbered items
("1.", "2.a.", "3.B)"), optionally grouped under ALL-CAPS section
headings ("CONSENT AGENDA", "PUBLIC HEARINGS"). Parsing is best-effort:
callers fall back to fixed-window chunking when fewer than two items are
found.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

# Numbered item headers: "1.", "12.", "1.a.", "2.B.", "3.a)", "4)" —
# anchored at line start, followed by the item title text.
ITEM_HEADER_RE = re.compile(
    r"^\s{0,8}(?P<number>\d{1,3}(?:\.[A-Za-z0-9]{1,3})*[.)])\s+(?P<title>\S.*)$"
)

# Section headings: a line that is (almost) all caps, reasonably short,
# and not just a number — e.g. "CONSENT AGENDA", "PUBLIC HEARINGS".
SECTION_HEADING_RE = re.compile(r"^\s{0,8}(?P<heading>[A-Z][A-Z0-9\s&/,'\-\.]{5,80})$")

# Lines that look like page furniture rather than content.
PAGE_NOISE_RE = re.compile(r"^\s*(Page \d+( of \d+)?|-+|_+|\d+)\s*$", re.IGNORECASE)


@dataclass
class ParsedAgendaItem:
    """One agenda item recovered from document text"""

    item_number: Optional[str]  # normalized, e.g. "2.a" (None for sections)
    title: str
    text: str = ""
    section: Optional[str] = None  # enclosing section heading, if any
    order: int = 0
    lines: List[str] = field(default_factory=list)


def normalize_item_number(raw: str) -> str:
    """Normalize '2.A.' / '2.a)' → '2.a' for stable matching"""
    return raw.strip().rstrip(".)").lower()


def parse_agenda_items(text: str) -> List[ParsedAgendaItem]:
    """Recover the agenda-item list from extracted agenda/minutes text.

    Returns an empty list when no plausible item structure is found, so
    callers can fall back to fixed-window chunking.
    """
    items: List[ParsedAgendaItem] = []
    current: Optional[ParsedAgendaItem] = None
    current_section: Optional[str] = None
    preamble_lines = 0

    for line in text.splitlines():
        stripped = line.rstrip()
        if not stripped.strip() or PAGE_NOISE_RE.match(stripped):
            continue

        header = ITEM_HEADER_RE.match(stripped)
        if header:
            if current is not None:
                current.text = "\n".join(current.lines).strip()
                items.append(current)
            current = ParsedAgendaItem(
                item_number=normalize_item_number(header.group("number")),
                title=header.group("title").strip(),
                section=current_section,
                order=len(items),
            )
            continue

        section = SECTION_HEADING_RE.match(stripped)
        if section and _plausible_section(section.group("heading")):
            # A section heading closes the current item and scopes the next.
            if current is not None:
                current.text = "\n".join(current.lines).strip()
                items.append(current)
                current = None
            current_section = section.group("heading").strip()
            continue

        if current is not None:
            current.lines.append(stripped.strip())
        else:
            preamble_lines += 1

    if current is not None:
        current.text = "\n".join(current.lines).strip()
        items.append(current)

    numbered = [item for item in items if item.item_number]
    if len(numbered) < 2:
        return []

    return items


def _plausible_section(heading: str) -> bool:
    """Filter ALL-CAPS lines that are shouting text rather than headings"""
    words = heading.split()
    return 1 <= len(words) <= 8 and any(ch.isalpha() for ch in heading)


def item_chunk_title(item: ParsedAgendaItem) -> str:
    """Human-readable chunk section title, e.g. 'Item 2.a: Rezoning ...'"""
    prefix = f"Item {item.item_number}: " if item.item_number else ""
    title = f"{prefix}{item.title}"
    if item.section:
        title = f"{item.section} — {title}"
    return title[:500]
