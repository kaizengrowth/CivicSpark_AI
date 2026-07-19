#!/usr/bin/env python3
"""Enrich a transcript: translate to Spanish and analyze into platform
categories — using the same free OpenAI-compatible LLM the platform runs
on (Llama on Groq by default).

Runs in the media-sync workflow after transcription:

  python scripts/enrich_transcript.py \
      --transcript transcript.json \
      --meeting-id 42 \
      [--languages es] \
      [--api-url https://civicspark-api.onrender.com \
       --api-token $TRANSCRIPT_INGEST_TOKEN]

Environment: LLM_API_KEY (+ optional LLM_BASE_URL, LLM_MODEL) for
translation/analysis. Without an LLM key the script uploads the plain
transcript unchanged, so transcription never blocks on enrichment.
"""

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
TRANSLATE_BATCH = 25
LANGUAGE_NAMES = {"es": "Spanish"}


def get_llm_client():
    """OpenAI-compatible client from env, or None when unconfigured"""
    api_key = os.environ.get("LLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, None
    from openai import OpenAI

    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL)
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    if os.environ.get("OPENAI_API_KEY") and not os.environ.get("LLM_API_KEY"):
        base_url = "https://api.openai.com/v1"
        model = os.environ.get("LLM_MODEL", "gpt-4.1-mini")
    return OpenAI(api_key=api_key, base_url=base_url), model


def _chat_json(client, model, system: str, user: str):
    """One JSON-mode chat call; returns parsed JSON or None"""
    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0.0,
            max_tokens=4000,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:  # noqa: BLE001 - enrichment is best-effort
        print(f"LLM call failed: {e}", file=sys.stderr)
        return None


def translate_segments(client, model, segments: list, language: str) -> int:
    """Add translations[language] to segments in place; returns count"""
    language_name = LANGUAGE_NAMES.get(language, language)
    translated = 0
    for offset in range(0, len(segments), TRANSLATE_BATCH):
        batch = segments[offset : offset + TRANSLATE_BATCH]
        numbered = "\n".join(
            f"{i}: {segment['text']}" for i, segment in enumerate(batch)
        )
        result = _chat_json(
            client,
            model,
            (
                f"You translate city-council meeting transcript lines into "
                f"{language_name}. Translate each numbered line faithfully - "
                "no summarizing, no additions. Return JSON: "
                '{"translations": {"0": "...", "1": "..."}}'
            ),
            numbered,
        )
        if not result:
            continue
        mapping = result.get("translations", {})
        for i, segment in enumerate(batch):
            text = mapping.get(str(i))
            if text:
                segment.setdefault("translations", {})[language] = text.strip()
                translated += 1
        print(
            f"Translated {min(offset + TRANSLATE_BATCH, len(segments))}"
            f"/{len(segments)} segments to {language}",
            file=sys.stderr,
        )
    return translated


def fetch_categories(api_url: str) -> list:
    """Platform topic taxonomy, so analysis lands in known categories"""
    try:
        import requests

        response = requests.get(
            f"{api_url.rstrip('/')}/api/v1/meetings/categories/", timeout=30
        )
        response.raise_for_status()
        return [category["name"] for category in response.json()]
    except Exception as e:  # noqa: BLE001
        print(f"Could not fetch categories: {e}", file=sys.stderr)
        return []


def analyze_transcript(client, model, segments: list, categories: list):
    """Summary + platform-category classification from the transcript"""
    # Sample the transcript to stay inside context: beginning, middle, end.
    text = " ".join(segment["text"] for segment in segments)
    if len(text) > 24000:
        third = 8000
        text = f"{text[:third]}\n[...]\n{text[len(text) // 2 - third // 2 : len(text) // 2 + third // 2]}\n[...]\n{text[-third:]}"

    category_list = ", ".join(categories) if categories else "(none provided)"
    return _chat_json(
        client,
        model,
        (
            "You analyze city-council meeting transcripts for a civic "
            "transparency platform. Only state what the transcript "
            "supports; do not invent votes or figures. Return JSON: "
            '{"summary": "2-3 sentences", '
            '"detailed_summary": "one paragraph", '
            '"topics": ["only names from the allowed list"], '
            '"keywords": ["5-10 short phrases"]}'
        ),
        f"Allowed topic categories: {category_list}\n\nTranscript:\n{text}",
    )


def upload(api_url: str, api_token: str, path: str, meeting_id: int, body: dict):
    import requests

    response = requests.post(
        f"{api_url.rstrip('/')}/api/v1/meetings/{meeting_id}/{path}",
        json=body,
        headers={"X-Ingest-Token": api_token},
        timeout=120,
    )
    response.raise_for_status()
    print(f"Uploaded {path}: {response.json()}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript", required=True, help="transcript JSON path")
    parser.add_argument("--meeting-id", required=True, type=int)
    parser.add_argument("--languages", default="es", help="comma-separated codes")
    parser.add_argument("--api-url", default=None)
    parser.add_argument("--api-token", default=None)
    args = parser.parse_args()

    payload = json.loads(Path(args.transcript).read_text())
    segments = payload["segments"]

    client, model = get_llm_client()
    analysis = None
    if client is None:
        print("No LLM configured; skipping translation/analysis.", file=sys.stderr)
    else:
        for language in [c.strip() for c in args.languages.split(",") if c.strip()]:
            count = translate_segments(client, model, segments, language)
            print(f"{language}: {count} segments translated", file=sys.stderr)

        categories = fetch_categories(args.api_url) if args.api_url else []
        analysis = analyze_transcript(client, model, segments, categories)
        if analysis:
            print(
                f"Analysis: topics={analysis.get('topics')}",
                file=sys.stderr,
            )

    Path(args.transcript).write_text(json.dumps(payload, indent=2))

    if args.api_url and args.api_token:
        upload(args.api_url, args.api_token, "transcript", args.meeting_id, payload)
        if analysis:
            upload(
                args.api_url,
                args.api_token,
                "analysis",
                args.meeting_id,
                {
                    "summary": analysis.get("summary"),
                    "detailed_summary": analysis.get("detailed_summary"),
                    "topics": analysis.get("topics") or [],
                    "keywords": analysis.get("keywords") or [],
                },
            )
    else:
        print("API upload skipped (no --api-url/--api-token).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
