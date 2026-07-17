#!/usr/bin/env python3
"""Thin wrapper kept for muscle memory: forwards to the ingestion CLI.

    python scripts/run_live_scraper.py [--source granicus] [--since DATE]

Equivalent to: cd backend && python -m app.cli ingest ...
"""

import os
import subprocess
import sys

if __name__ == "__main__":
    backend = os.path.join(os.path.dirname(__file__), "..", "backend")
    cmd = [sys.executable, "-m", "app.cli", "ingest", *sys.argv[1:]]
    sys.exit(subprocess.call(cmd, cwd=backend))
