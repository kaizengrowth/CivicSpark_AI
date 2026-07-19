#!/usr/bin/env python3
"""Transcribe a council meeting video with Whisper on CPU — for free.

Designed to run inside the GitHub Actions workflow
(.github/workflows/transcribe.yml) on a standard free runner:
ffmpeg extracts a 16kHz mono audio track, faster-whisper (CTranslate2,
int8) transcribes it, and the timestamped segments are written to JSON
and optionally POSTed to the CivicSpark API.

Usage:
  python scripts/transcribe_meeting.py \
      --video-url https://.../meeting.mp4 \
      --meeting-id 42 \
      --model base.en \
      --output transcript.json \
      [--api-url https://civicspark-api.onrender.com \
       --api-token $TRANSCRIPT_INGEST_TOKEN]

Dependencies (workflow-only, not part of backend requirements):
  apt: ffmpeg
  pip: faster-whisper requests
"""

import argparse
import json
import subprocess  # nosec B404 - ffmpeg invocation with fixed args
import sys
import tempfile
from pathlib import Path


def extract_audio(video_url: str, output_path: str) -> None:
    """Download/extract a 16kHz mono wav from the video URL via ffmpeg"""
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        video_url,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        output_path,
    ]
    subprocess.run(command, check=True)  # nosec B603


def transcribe(audio_path: str, model_name: str) -> list:
    """Run faster-whisper over the audio; returns [{start, end, text}]"""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments_iter, info = model.transcribe(
        audio_path,
        vad_filter=True,
        beam_size=5,
    )
    print(
        f"Detected language {info.language} "
        f"(p={info.language_probability:.2f}), duration {info.duration:.0f}s",
        file=sys.stderr,
    )

    segments = []
    for segment in segments_iter:
        text = segment.text.strip()
        if not text:
            continue
        segments.append(
            {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": text,
            }
        )
        # Progress heartbeat for long meetings in the Actions log.
        if len(segments) % 100 == 0:
            print(
                f"... {len(segments)} segments ({segment.end / 60:.0f} min)",
                file=sys.stderr,
            )
    return segments


def upload(api_url: str, api_token: str, meeting_id: int, payload: dict) -> None:
    import requests

    response = requests.post(
        f"{api_url.rstrip('/')}/api/v1/meetings/{meeting_id}/transcript",
        json=payload,
        headers={"X-Ingest-Token": api_token},
        timeout=120,
    )
    response.raise_for_status()
    print(f"Uploaded: {response.json()}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-url", required=True)
    parser.add_argument("--meeting-id", required=True, type=int)
    parser.add_argument("--model", default="base.en")
    parser.add_argument("--output", default="transcript.json")
    parser.add_argument("--api-url", default=None)
    parser.add_argument("--api-token", default=None)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = str(Path(tmp) / "audio.wav")
        print(f"Extracting audio from {args.video_url} ...", file=sys.stderr)
        extract_audio(args.video_url, audio_path)

        print(f"Transcribing with faster-whisper/{args.model} ...", file=sys.stderr)
        segments = transcribe(audio_path, args.model)

    if not segments:
        print("No speech found; nothing to store.", file=sys.stderr)
        return 1

    payload = {
        "video_url": args.video_url,
        "source_model": f"faster-whisper/{args.model}",
        "segments": segments,
    }
    Path(args.output).write_text(json.dumps(payload, indent=2))
    print(f"Wrote {len(segments)} segments to {args.output}", file=sys.stderr)

    if args.api_url and args.api_token:
        upload(args.api_url, args.api_token, args.meeting_id, payload)
    else:
        print(
            "API upload skipped (set --api-url/--api-token to ingest).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
