#!/usr/bin/env python3
"""Optimize video clips from build/video into videos/ for web delivery."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

BUILD_DIR = Path(__file__).resolve().parent
ROOT = BUILD_DIR.parent
SOURCE_DIR = BUILD_DIR / "video"
TARGET_DIR = ROOT / "videos"
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpeg", ".mpg"}
DEFAULT_CRF = 30
DEFAULT_MAX_WIDTH = 720
AUDIO_BITRATE = "96k"
PRESET = "slow"


def find_video_files() -> list[Path]:
    if not SOURCE_DIR.exists():
        return []
    return sorted(
        path
        for path in SOURCE_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def target_path(source: Path) -> Path:
    return TARGET_DIR / f"{source.stem}.mp4"


def is_up_to_date(source: Path, target: Path) -> bool:
    return target.exists() and source.stat().st_mtime_ns <= target.stat().st_mtime_ns


def check_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError(
            "ffmpeg executable not found on PATH. Install ffmpeg and retry."
        )
    return ffmpeg


def optimize_video(
    source: Path,
    target: Path,
    ffmpeg: str,
    faststart: bool = True,
    crf: int = DEFAULT_CRF,
    max_width: int = DEFAULT_MAX_WIDTH,
    audio_bitrate: str = AUDIO_BITRATE,
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)

    scale_filter = f"scale='if(gt(iw,{max_width}),{max_width},iw)':-2"
    movflags = "+faststart" if faststart else ""
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-preset",
        PRESET,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-vf",
        scale_filter,
        "-c:a",
        "aac",
        "-b:a",
        audio_bitrate,
    ]
    if movflags:
        command.extend(["-movflags", movflags])
    command.append(str(target))

    subprocess.run(command, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Optimize videos in build/video for web delivery and copy them to videos/."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-generate optimized output even if the target already exists and is newer.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which videos would be optimized without running ffmpeg.",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=DEFAULT_CRF,
        help=f"Video quality CRF value (higher is smaller, default {DEFAULT_CRF}).",
    )
    parser.add_argument(
        "--max-width",
        type=int,
        default=DEFAULT_MAX_WIDTH,
        help=f"Maximum video width in pixels for web output (default {DEFAULT_MAX_WIDTH}).",
    )
    parser.add_argument(
        "--audio-bitrate",
        default=AUDIO_BITRATE,
        help=f"Audio bitrate for optimized output (default {AUDIO_BITRATE}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ffmpeg = check_ffmpeg()

    videos = find_video_files()
    if not videos:
        print(f"No videos found in {SOURCE_DIR}")
        return 0

    print(f"Found {len(videos)} video(s) in {SOURCE_DIR}")
    skipped = 0
    optimized = 0

    for source in videos:
        target = target_path(source)
        if not args.force and is_up_to_date(source, target):
            print(f"Skipping up-to-date video: {source.name}")
            skipped += 1
            continue

        print(f"Optimizing {source.name} -> {target.relative_to(ROOT)}")
        if args.dry_run:
            optimized += 1
            continue

        optimize_video(
            source,
            target,
            ffmpeg,
            crf=args.crf,
            max_width=args.max_width,
            audio_bitrate=args.audio_bitrate,
        )
        optimized += 1

    print(
        f"Done. Optimized: {optimized}, skipped: {skipped}, output directory: {TARGET_DIR}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
