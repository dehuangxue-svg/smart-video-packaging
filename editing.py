"""Non-destructive single-source edits and bounded-memory FFmpeg preparation."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from core import probe_video, run


def normalize_clips(clips, duration: float) -> list[dict]:
    if clips is None:
        return [{"id": "original", "source_start": 0.0, "source_end": duration}]
    result = []
    for index, clip in enumerate(clips):
        start, end = float(clip["source_start"]), float(clip["source_end"])
        if not all(math.isfinite(x) for x in (start, end)) or start < 0 or start >= duration or end <= start or end > duration + 0.05:
            raise ValueError("视频片段范围无效")
        result.append({"id": str(clip.get("id", index)), "source_start": start, "source_end": min(end, duration)})
    return result


def edit_duration(clips: list[dict]) -> float:
    return sum(x["source_end"] - x["source_start"] for x in clips)


def edit_key(clips: list[dict]) -> str:
    spans = [(round(x["source_start"], 6), round(x["source_end"], 6)) for x in clips]
    return hashlib.sha256(json.dumps(spans).encode()).hexdigest()[:16]


def prepare_edited_video(video: Path, clips: list[dict], directory: Path, threads: int = 2) -> Path:
    if not clips:
        raise ValueError("时间轴没有视频片段")
    media = probe_video(video)
    # Splitting without removing footage does not require an intermediate encode.
    contiguous = abs(clips[0]["source_start"]) < 0.001 and abs(clips[-1]["source_end"] - media["duration"]) < 0.05
    contiguous = contiguous and all(abs(a["source_end"] - b["source_start"]) < 0.001 for a, b in zip(clips, clips[1:]))
    if contiguous and media.get("audio_codec"):
        return video
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / video.name
    if output.exists():
        return output
    pieces = []
    try:
        for index, clip in enumerate(clips):
            piece = directory / f"part-{index:05d}.nut"
            pieces.append(piece)
            duration = clip["source_end"] - clip["source_start"]
            args = ["ffmpeg", "-y", "-v", "error", "-ss", str(clip["source_start"]), "-i", str(video)]
            if not media.get("audio_codec"):
                args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
            args += ["-map", "0:v:0", "-map", "0:a:0" if media.get("audio_codec") else "1:a:0",
                     "-t", str(duration), "-vf", "setpts=PTS-STARTPTS", "-af", "aresample=async=1:first_pts=0,apad",
                     "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                     "-threads", str(max(1, min(threads, 2))), "-bf", "0", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(piece)]
            run(args)
        manifest = directory / "concat.txt"
        manifest.write_text("\n".join(f"file '{piece.name}'" for piece in pieces), encoding="utf-8")
        temporary = directory / "prepared.tmp.mp4"
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(manifest),
             "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(temporary)])
        temporary.replace(output)
        return output
    finally:
        for piece in pieces:
            piece.unlink(missing_ok=True)
