"""Entity resolution for agenda items.

Resolves councilor names and districts against the canonical
representative data, and extracts ordinance/resolution numbers. Output
shape stored on agenda_items.entities:

  {"councilors": ["Jane Doe"], "districts": [4],
   "ordinances": ["25123"], "resolutions": []}
"""

import re

from app.data.tulsa_districts import DISTRICT_REPRESENTATIVES

ORDINANCE_RE = re.compile(r"\bOrdinance\s+(?:No\.?\s*)?(\d{4,6})\b", re.I)
RESOLUTION_RE = re.compile(r"\bResolution\s+(?:No\.?\s*)?(\d{4,6})\b", re.I)
DISTRICT_RE = re.compile(r"\b(?:Council\s+)?District\s+(\d{1,2})\b", re.I)


def _councilor_names() -> list[str]:
    return [rep["name"] for rep in DISTRICT_REPRESENTATIVES.values() if rep.get("name")]


def extract_entities(text: str) -> dict:
    councilors = []
    for name in _councilor_names():
        # Match on last name with word boundaries; full names rarely
        # survive OCR/layout intact.
        last = name.split()[-1]
        if re.search(rf"\b{re.escape(last)}\b", text, re.I):
            councilors.append(name)

    districts = sorted({int(d) for d in DISTRICT_RE.findall(text) if 1 <= int(d) <= 9})

    return {
        "councilors": councilors,
        "districts": districts,
        "ordinances": list(dict.fromkeys(ORDINANCE_RE.findall(text))),
        "resolutions": list(dict.fromkeys(RESOLUTION_RE.findall(text))),
    }
