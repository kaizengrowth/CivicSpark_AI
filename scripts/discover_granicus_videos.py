#!/usr/bin/env python3
"""Discover new Granicus (TGOV) meeting videos and pair them with
CivicSpark meetings that still lack a transcript.

Tulsa publishes council video through Granicus at tulsa-ok.granicus.com.
Granicus exposes an RSS/podcast feed per view with direct media
enclosures:

  {base}/ViewPublisherRSS.php?view_id={id}&mode=vpodcast

This adapter reads those feeds, matches items to the API's
/meetings/media/pending list by meeting date (same calendar day), and
emits a JSON matrix for the workflow's transcription jobs.

Usage:
  python scripts/discover_granicus_videos.py \
      --api-url https://civicspark-api.onrender.com \
      [--granicus-base https://tulsa-ok.granicus.com] \
      [--view-ids 4,7] \
      [--max-jobs 2] \
      --output matrix.json
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET  # nosec B405 - parsing trusted city feed
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests


def fetch_feed_items(granicus_base: str, view_id: str) -> list:
    """RSS items for one Granicus view: [{title, date, video_url}]"""
    url = f"{granicus_base.rstrip('/')}/ViewPublisherRSS.php"
    response = requests.get(
        url, params={"view_id": view_id, "mode": "vpodcast"}, timeout=60
    )
    response.raise_for_status()

    items = []
    root = ET.fromstring(response.content)  # nosec B314 - city-published feed
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        enclosure = item.find("enclosure")
        video_url = enclosure.get("url") if enclosure is not None else None
        pub_date = None
        raw_date = item.findtext("pubDate")
        if raw_date:
            try:
                pub_date = parsedate_to_datetime(raw_date)
            except (TypeError, ValueError):
                pass
        if video_url:
            items.append({"title": title, "date": pub_date, "video_url": video_url})
    return items


def fetch_pending_meetings(api_url: str) -> list:
    response = requests.get(
        f"{api_url.rstrip('/')}/api/v1/meetings/media/pending",
        params={"days": 30, "limit": 25},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["pending"]


def match(videos: list, pending: list) -> list:
    """Pair feed videos to pending meetings by calendar day.

    A meeting that already carries a video_url keeps it (re-discovery
    after a failed transcription run); otherwise the feed item published
    on the meeting's date wins.
    """
    jobs = []
    used_videos = set()

    for meeting in pending:
        if meeting.get("video_url"):
            jobs.append(
                {
                    "meeting_id": meeting["meeting_id"],
                    "video_url": meeting["video_url"],
                    "title": meeting["title"],
                }
            )
            continue

        meeting_day = (meeting.get("meeting_date") or "")[:10]
        if not meeting_day:
            continue
        for video in videos:
            if video["video_url"] in used_videos or video["date"] is None:
                continue
            if video["date"].strftime("%Y-%m-%d") == meeting_day:
                used_videos.add(video["video_url"])
                jobs.append(
                    {
                        "meeting_id": meeting["meeting_id"],
                        "video_url": video["video_url"],
                        "title": meeting["title"],
                    }
                )
                break
    return jobs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument(
        "--granicus-base", default="https://tulsa-ok.granicus.com"
    )
    parser.add_argument(
        "--view-ids",
        default="4",
        help="Comma-separated Granicus view ids (4 = Tulsa council archive)",
    )
    parser.add_argument("--max-jobs", type=int, default=2)
    parser.add_argument("--output", default="matrix.json")
    args = parser.parse_args()

    videos = []
    for view_id in [v.strip() for v in args.view_ids.split(",") if v.strip()]:
        try:
            found = fetch_feed_items(args.granicus_base, view_id)
            print(f"View {view_id}: {len(found)} feed items", file=sys.stderr)
            videos.extend(found)
        except Exception as e:  # noqa: BLE001 - one bad view must not stop others
            print(f"View {view_id} failed: {e}", file=sys.stderr)

    pending = fetch_pending_meetings(args.api_url)
    print(f"{len(pending)} meetings pending transcripts", file=sys.stderr)

    jobs = match(videos, pending)[: args.max_jobs]
    Path(args.output).write_text(json.dumps({"include": jobs}))
    print(
        f"Matched {len(jobs)} job(s): "
        + ", ".join(f"meeting {j['meeting_id']}" for j in jobs),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
