"""Topic classification constrained to the canonical taxonomy.

Primary path: one gpt-4.1-mini call per meeting, labeling every agenda
item in a batch (cheap, cacheable by content hash upstream). Fallback
path when OpenAI is not configured: keyword matching against the
taxonomy's keyword lists, so ingestion never blocks on the LLM.
"""

import json
import logging
from pathlib import Path

from openai import OpenAI

from app.core.config import Settings

logger = logging.getLogger(__name__)

TAXONOMY_PATH = Path(__file__).resolve().parents[1] / "data" / "topic_taxonomy.json"
CLASSIFY_MODEL = "gpt-4.1-mini"


def load_taxonomy() -> list[dict]:
    return json.loads(TAXONOMY_PATH.read_text())["topics"]


def keyword_classify(text: str, taxonomy: list[dict], max_labels: int = 3) -> list[str]:
    text_lower = text.lower()
    scored = []
    for topic in taxonomy:
        hits = sum(1 for kw in topic.get("keywords", []) if kw.lower() in text_lower)
        if hits:
            scored.append((hits, topic["name"]))
    scored.sort(reverse=True)
    return [name for _, name in scored[:max_labels]]


class TopicClassifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.taxonomy = load_taxonomy()
        self.valid_names = {t["name"] for t in self.taxonomy}
        self.client = (
            OpenAI(api_key=settings.openai_api_key)
            if settings.is_openai_configured
            else None
        )

    def classify_items(self, items: list[dict]) -> dict[str, list[str]]:
        """items: [{"key": item_hash, "text": "..."}] -> key -> labels.

        Labels outside the taxonomy are dropped, never invented.
        """
        if not items:
            return {}
        if not self.client:
            return {
                item["key"]: keyword_classify(item["text"], self.taxonomy)
                for item in items
            }

        label_list = ", ".join(sorted(self.valid_names))
        payload = [{"id": item["key"], "text": item["text"][:1500]} for item in items]
        prompt = (
            "Label each Tulsa city-government agenda item with 1-3 topics "
            f"from this fixed list (use names verbatim): {label_list}\n\n"
            "Reply with JSON only: "
            '{"labels": {"<id>": ["topic", ...], ...}}\n\n'
            f"Items:\n{json.dumps(payload)}"
        )
        try:
            response = self.client.chat.completions.create(
                model=CLASSIFY_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = json.loads(response.choices[0].message.content or "{}")
            labels = raw.get("labels", {})
            return {
                item["key"]: [
                    label
                    for label in labels.get(item["key"], [])
                    if label in self.valid_names
                ]
                or keyword_classify(item["text"], self.taxonomy)
                for item in items
            }
        except Exception as e:
            logger.error(f"LLM topic classification failed, using keywords: {e}")
            return {
                item["key"]: keyword_classify(item["text"], self.taxonomy)
                for item in items
            }
