from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("output")
    parser.add_argument("--min-bytes", type=int, default=1024)
    args = parser.parse_args()
    output = Path(args.output)
    if output.is_file() and output.stat().st_size >= args.min_bytes:
        print(f"Already exists: {output}")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".download")
    request = urllib.request.Request(args.url, headers={"User-Agent": "SmartVideoPackaging-Installer/1.0"})
    downloaded = 0
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as target:
        total = int(response.headers.get("Content-Length") or 0)
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            target.write(block)
            downloaded += len(block)
            if downloaded % (32 * 1024 * 1024) < len(block):
                percent = downloaded * 100 / total if total else 0
                print(f"{downloaded / 1024 / 1024:.0f} MB {percent:.0f}%", flush=True)
    if downloaded < args.min_bytes or (total and downloaded != total):
        raise RuntimeError(f"Incomplete download: {downloaded} bytes; expected at least {args.min_bytes}")
    os.replace(temporary, output)
    print(f"Saved: {output} ({downloaded / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    main()
