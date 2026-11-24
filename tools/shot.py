#!/usr/bin/env python3
"""Screenshot an HTML file to PNG with a private headless Chrome process.

Usage: tools/shot.py PAGE.html OUT.png [--size 1100x640]

Each call starts its own Chrome with a throwaway profile, so parallel callers never
share a browser, tab or window size (the shared Playwright MCP browser does).
file:// pages load directly; no http server needed.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("page")
    p.add_argument("out")
    p.add_argument("--size", default="1100x640", help="WIDTHxHEIGHT (default 1100x640)")
    a = p.parse_args()
    chrome = next((c for c in CHROME_CANDIDATES if c and os.path.exists(c)), None)
    if chrome is None:
        sys.exit("shot.py: no Chrome or Chromium found")
    w, h = a.size.lower().split("x")
    url = a.page if "://" in a.page else "file://" + os.path.abspath(a.page)
    profile = tempfile.mkdtemp(prefix="shot-chrome-")
    try:
        r = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-first-run",
                            "--hide-scrollbars", f"--user-data-dir={profile}",
                            f"--window-size={w},{h}", f"--screenshot={os.path.abspath(a.out)}", url],
                           capture_output=True, text=True, timeout=60)
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if r.returncode != 0 or not os.path.exists(a.out):
        sys.exit(f"shot.py: chrome failed ({r.returncode}): {r.stderr.strip()[-400:]}")
    print(a.out)


if __name__ == "__main__":
    main()
