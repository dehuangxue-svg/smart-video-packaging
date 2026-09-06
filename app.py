from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from functools import lru_cache
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from editing import normalize_clips, edit_duration, edit_key, prepare_edited_video
from review_queue import ReviewQueue, QueueConflict, atomic_json, revision

from core import (
    ROOT, load_config, probe_video, product_name_from_filename, project_id,
    read_json, run, safe_stem, sound_marker_target, suggest_sound_markers, validate_project, write_ass, write_json,
)


CONFIG = load_config()
PROJECTS = Path(CONFIG["projects_dir"])
JOBS_DIR = Path(CONFIG["jobs_dir"])
TRAINING = Path(CONFIG["training_dir"])
TEMP = Path(CONFIG["temp_dir"])
CACHE = Path(CONFIG.get("cache_dir", ROOT / "data" / "cache"))
EXPORTS = Path(CONFIG["exports_dir"])
WORKER_PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PYTHON = WORKER_PYTHON if WORKER_PYTHON.is_file() else Path(sys.executable)
JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()
MODEL_LOCK = threading.Lock()
EXPORT_LOCK = threading.Lock()
REVIEW = ReviewQueue(PROJECTS)
PIPELINE_VERSION = "multilingual-word-timestamps-v4-paraformer-fa-zh-alignment"
AsrLanguage = Literal["auto", "zh", "en", "yue", "ja", "ko"]

app = FastAPI(title="剪辑智能包装", version="0.2.0")


@app.exception_handler(QueueConflict)
async def queue_conflict_handler(request, exc):
    return JSONResponse(status_code=409, content={'detail': str(exc)})


class VideoRequest(BaseModel):
    video: str
    language: AsrLanguage = "auto"
    video_clips: list[dict[str, Any]] | None = None


class BatchRequest(BaseModel):
    folder: str
    recursive: bool = False
    language: AsrLanguage = "auto"


class ProjectRequest(BaseModel):
    video: str
    revision: str | None = None
    video_clips: list[dict[str, Any]] | None = None
    product_name: str = ""
    subtitles: list[dict[str, Any]] = Field(default_factory=list)
    speech_segments: list[dict[str, Any]] = Field(default_factory=list)
    sound_markers: list[dict[str, Any]] = Field(default_factory=list)
    visual: dict[str, Any] = Field(default_factory=dict)
    asr_quality: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    model_output: dict[str, Any] = Field(default_factory=dict)


class ReviewSelection(BaseModel):
    ids: list[str] = Field(default_factory=list)
    language: AsrLanguage = 'auto'
    reprocess: bool = False


class ReviewApproval(BaseModel):
    id: str
    revision: str
    reviewed: bool = True


def project_path(video: Path) -> Path:
    return PROJECTS / f"{project_id(video)}.json"


def ensure_video(path: str) -> Path:
    video = Path(path).expanduser().resolve()
    if not video.is_file():
        raise HTTPException(404, f"视频不存在：{video}")
    return video


def dependency_status() -> dict[str, Any]:
    paths = {
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
        "sensevoice": CONFIG["sensevoice_model"],
        "tokens": CONFIG["sensevoice_tokens"],
        "vad": CONFIG["silero_vad"],
        "fallback_asr": CONFIG.get("faster_whisper_model", ""),
        "paraformer": CONFIG.get("paraformer_model", ""),
        "paraformer_vad": CONFIG.get("paraformer_vad_model", ""),
        "paraformer_punc": CONFIG.get("paraformer_punc_model", ""),
        "paraformer_align": CONFIG.get("paraformer_align_model", ""),
        "punctuation": CONFIG["punctuation_model"],
        "face": CONFIG["face_model"],
        "qwen": CONFIG["qwen_model"],
        "llama": CONFIG["llama_cli"],
    }
    return {key: {"ready": bool(value and Path(value).exists()), "path": str(value or "")} for key, value in paths.items()}


def installed_font_families() -> list[str]:
    """Return Windows font families for the editor without loading font files."""
    preferred = [
        "华文琥珀", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC", "MiSans",
        "HarmonyOS Sans SC", "SimHei", "DengXian", "KaiTi", "FangSong",
        "方正姚体", "方正舒体", "幼圆", "华文行楷", "Arial",
    ]
    names: set[str] = set(preferred)
    if os.name == "nt":
        try:
            import winreg
            locations = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            ]
            for hive, key_name in locations:
                try:
                    with winreg.OpenKey(hive, key_name) as key:
                        index = 0
                        while True:
                            try:
                                value_name = str(winreg.EnumValue(key, index)[0])
                            except OSError:
                                break
                            index += 1
                            label = re.sub(r"\s*\((?:TrueType|OpenType)\)\s*$", "", value_name, flags=re.I)
                            for part in re.split(r"\s*&\s*", label):
                                family = part.replace("_", " ").strip()
                                family = re.sub(
                                    r"(?:[ -](?:Regular|Bold|Italic|Light|Medium|Semibold|Semilight|Black))+$",
                                    "", family, flags=re.I,
                                ).strip()
                                if family and "All res" not in family and len(family) <= 80:
                                    names.add(family)
                except OSError:
                    continue
        except (ImportError, OSError):
            pass
    priority = {name: index for index, name in enumerate(preferred)}
    return sorted(names, key=lambda name: (priority.get(name, len(preferred)), name.casefold()))


def update_job(job_id: str, **changes: Any) -> None:
    with JOBS_LOCK:
        JOBS[job_id].update(changes)
        JOBS[job_id]["updated_at"] = time.time()
        write_json(JOBS_DIR / f"{job_id}.json", JOBS[job_id])


def execute_worker(job_id: str, stage: str, command: list[str], output: Path, progress: int) -> dict[str, Any]:
    update_job(job_id, stage=stage, message=stage, progress=progress)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=flags, cwd=ROOT,
    )
    if process.returncode:
        raise RuntimeError((process.stderr or process.stdout or f"{stage}失败")[-4000:])
    result = read_json(output)
    if not isinstance(result, dict):
        raise RuntimeError(f"{stage}没有生成有效结果")
    return result


def video_cache_dir(video: Path, language: str = "auto") -> Path:
    stat = video.stat()
    token = f"{project_id(video)}_{stat.st_size}_{stat.st_mtime_ns}_{PIPELINE_VERSION}_{language}"
    return CACHE / token


def execute_cached_worker(
    job_id: str, stage: str, command: list[str], output: Path, progress: int, cached: Path,
) -> dict[str, Any]:
    if cached.is_file():
        update_job(job_id, stage=stage, message=f"{stage}（使用稳定缓存）", progress=progress)
        shutil.copy2(cached, output)
        result = read_json(output)
        if isinstance(result, dict):
            return result
    result = execute_worker(job_id, stage, command, output, progress)
    cached.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output, cached)
    return result


def run_auto_job(job_id: str, video: Path, language: str = "auto", video_clips=None) -> None:
    job_dir = JOBS_DIR / job_id
    try:
        job_dir.mkdir(parents=True, exist_ok=True)
        cache_dir = video_cache_dir(video, language)
        REVIEW.processing(video, 'processing')
        with MODEL_LOCK:
            clips = normalize_clips(video_clips, float(probe_video(video)["duration"]))
            if not clips:
                raise ValueError("时间轴没有视频片段")
            if video_clips is not None:
                cache_dir = cache_dir / ("edit_" + edit_key(clips))
                update_job(job_id, stage="正在准备剪辑后的视频", message="正在准备剪辑后的视频", progress=5)
            prepared = prepare_edited_video(video, clips, cache_dir / "prepared", CONFIG.get("threads", 2))
            status = dependency_status()
            missing_asr = [key for key in ("sensevoice", "tokens", "vad", "punctuation") if not status[key]["ready"]]
            if missing_asr:
                raise RuntimeError("缺少轻量ASR模型，请先双击“下载轻量模型.bat”：" + "、".join(missing_asr))
            paraformer_ready = language in ("auto", "zh") and all(
                Path(CONFIG.get(key, "")).is_dir()
                for key in ("paraformer_model", "paraformer_vad_model", "paraformer_punc_model")
            )
            if paraformer_ready:
                asr_out = job_dir / "asr_paraformer.json"
                try:
                    asr = execute_cached_worker(job_id, "正在用Paraformer-zh识别字幕", [
                        str(PYTHON), str(ROOT / "workers" / "paraformer_worker.py"),
                        "--video", str(prepared), "--output", str(asr_out),
                        "--model", CONFIG["paraformer_model"],
                        "--vad", CONFIG["paraformer_vad_model"],
                        "--punc", CONFIG["paraformer_punc_model"],
                        "--align-model", CONFIG.get("paraformer_align_model", ""),
                        "--threads", str(CONFIG.get("threads", 2)),
                    ], asr_out, 15, cache_dir / "asr_paraformer.json")
                except Exception:
                    asr_out = job_dir / "asr.json"
                    asr = execute_cached_worker(job_id, "Paraformer失败，回退SenseVoice识别字幕", [
                        str(PYTHON), str(ROOT / "workers" / "asr_worker.py"),
                        "--video", str(prepared), "--output", str(asr_out),
                        "--model", CONFIG["sensevoice_model"], "--tokens", CONFIG["sensevoice_tokens"],
                        "--vad", CONFIG["silero_vad"], "--threads", str(CONFIG.get("threads", 2)),
                        "--punctuation", CONFIG["punctuation_model"],
                        "--fallback-model", CONFIG.get("faster_whisper_model", ""),
                        "--align-all", "--language", language,
                    ], asr_out, 15, cache_dir / "asr.json")
            else:
                asr_out = job_dir / "asr.json"
                asr = execute_cached_worker(job_id, "正在用SenseVoice识别字幕", [
                    str(PYTHON), str(ROOT / "workers" / "asr_worker.py"),
                    "--video", str(prepared), "--output", str(asr_out),
                    "--model", CONFIG["sensevoice_model"], "--tokens", CONFIG["sensevoice_tokens"],
                    "--vad", CONFIG["silero_vad"], "--threads", str(CONFIG.get("threads", 2)),
                    "--punctuation", CONFIG["punctuation_model"],
                    "--fallback-model", CONFIG.get("faster_whisper_model", ""),
                    "--align-all", "--language", language,
                ], asr_out, 15, cache_dir / "asr.json")

            analysis_in = job_dir / "analysis_input.json"
            analysis_out = job_dir / "analysis.json"
            write_json(analysis_in, asr)
            analysis = execute_cached_worker(job_id, "正在识别功效、卖点和高亮词", [
                str(PYTHON), str(ROOT / "workers" / "analyze_worker.py"),
                "--input", str(analysis_in), "--output", str(analysis_out),
                "--llama", CONFIG["llama_cli"], "--model", CONFIG["qwen_model"],
                "--threads", str(CONFIG.get("threads", 2)),
            ], analysis_out, 58, cache_dir / "analysis.json")

            visual_out = job_dir / "visual.json"
            face_model = Path(CONFIG["face_model"])
            try:
                face_model_arg = str(face_model.relative_to(ROOT))
            except ValueError:
                face_model_arg = str(face_model)
            visual = execute_cached_worker(job_id, "正在抽帧检查主播和文字板风险", [
                str(PYTHON), str(ROOT / "workers" / "visual_worker.py"),
                "--video", str(prepared), "--output", str(visual_out),
                "--interval", str(CONFIG.get("visual_interval", 2.0)),
                "--face-model", face_model_arg,
            ], visual_out, 78, cache_dir / "visual.json")

        subtitles = analysis.get("subtitles") or asr.get("subtitles", [])
        hook_candidate = next((s for s in subtitles if s.get("label") in ("benefit", "selling_point") and 3 <= float(s.get("end", 0)) - float(s.get("start", 0)) <= 10), None)
        hook_end = min(10.0, max(3.0, float(hook_candidate.get("end", 8.0)))) if hook_candidate else 8.0
        video_duration = edit_duration(clips)
        sound_markers = suggest_sound_markers(subtitles, hook_end, video_duration=video_duration)
        for marker in sound_markers:
            marker.setdefault("duration", sfx_source_duration(str(marker.get("type", "pop"))))
        project = {
            "video": str(video), "product_name": asr.get("product_name", product_name_from_filename(video)),
            "video_clips": clips if video_clips is not None else None,
            "subtitles": subtitles, "speech_segments": asr.get("speech_segments", []),
            "sound_markers": sound_markers, "visual": visual,
            "asr_quality": asr.get("quality", {}),
            "settings": {
                "font": "华文琥珀", "font_size": 54, "margin_v": 180,
                "text_color": "#FFFFFF", "highlight_color": "#FFD43B",
                "outline_color": "#101010", "hook_end": round(hook_end, 2), "sfx_volume": 0.50,
                "subtitle_x": 50, "subtitle_y": 90,
                "sfx_target_count": sound_marker_target(video_duration),
                "asr_language": language,
            },
            "model_output": {"asr": asr, "analysis": analysis, "visual": visual, "video_clips": clips},
        }
        project['revision'] = REVIEW.save(project, analysis=True)
        # Keep an immutable model-output snapshot for local training from the
        # first automatic analysis; later human saves create additional
        # before/after snapshots through the normal save endpoint.
        save_training_snapshot(project)
        quality = asr.get("quality", {})
        needs_review = quality.get("status") == "needs_review"
        update_job(
            job_id, status="done", stage="完成",
            message="识别完成，存在需回听的语音区间" if needs_review else "自动分析完成，时间戳质检通过",
            progress=100, quality_status="needs_review" if needs_review else "ok", result=project,
        )
    except Exception as exc:
        REVIEW.processing(video, 'error', str(exc))
        update_job(job_id, status="error", stage="失败", message=str(exc), progress=100)


def run_batch_job(job_id: str, videos: list[Path], language: str = "auto") -> None:
    """Process a folder serially so a 4GB machine never holds two models at once."""
    results: list[dict[str, Any]] = []
    total = len(videos)
    for position, video in enumerate(videos, start=1):
        update_job(
            job_id, stage=f"第{position}/{total}个视频", message=f"正在处理：{video.name}",
            progress=min(98, int((position - 1) / max(total, 1) * 100)),
        )
        child_id = uuid.uuid4().hex
        child = {
            "id": child_id, "kind": "auto", "parent_id": job_id, "video": str(video),
            "status": "running", "stage": "排队", "message": "等待开始", "progress": 0,
            "created_at": time.time(),
        }
        with JOBS_LOCK:
            JOBS[child_id] = child
            write_json(JOBS_DIR / f"{child_id}.json", child)
        run_auto_job(child_id, video, language)
        with JOBS_LOCK:
            finished = copy.deepcopy(JOBS.get(child_id, {}))
        results.append({
            "video": str(video), "job_id": child_id,
            "status": finished.get("status", "error"),
            "quality_status": finished.get("quality_status", "error"),
            "message": finished.get("message", "未知结果"),
            "project": str(project_path(video)) if project_path(video).is_file() else "",
        })

    completed = sum(item["status"] == "done" for item in results)
    review = sum(item["quality_status"] == "needs_review" for item in results)
    failed = total - completed
    summary = {"total": total, "completed": completed, "needs_review": review, "failed": failed, "items": results}
    message = f"批量完成：{completed}/{total}，需回听{review}，失败{failed}"
    update_job(job_id, status="done", stage="批量完成", message=message, progress=100, result=summary)


def save_training_snapshot(project: dict[str, Any]) -> Path:
    video = Path(project["video"])
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    snapshot = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "video": str(video), "product_name": project.get("product_name", ""),
        "model_output": project.get("model_output", {}),
        "human_edited": {"subtitles": project.get("subtitles", []), "sound_markers": project.get("sound_markers", []), "settings": project.get("settings", {}), "video_clips": project.get("video_clips")},
        "time_basis": "Each version uses its own edited timeline; video_clips maps it back to the original video.",
        "positive_definition": "人工保留、修正或标为功效/卖点的字幕",
        "negative_definition": "人工取消选中或标为remove的字幕",
    }
    path = TRAINING / "snapshots" / f"{project_id(video)}_{stamp}.json"
    write_json(path, snapshot)
    return path


SFX_CATALOG = [
    {"id": "pop", "label": "轻弹", "group": "强调", "duration": 0.16},
    {"id": "shine", "label": "闪光", "group": "重点", "duration": 0.28},
    {"id": "whoosh", "label": "轻转场", "group": "转场", "duration": 0.42},
    {"id": "click", "label": "点击", "group": "节奏", "duration": 0.10},
    {"id": "tap", "label": "轻敲", "group": "节奏", "duration": 0.14},
    {"id": "bell", "label": "提示铃", "group": "提示", "duration": 0.70},
    {"id": "chime", "label": "清脆和弦", "group": "重点", "duration": 0.54},
    {"id": "coin", "label": "金币", "group": "价格", "duration": 0.23},
    {"id": "success", "label": "完成提示", "group": "提示", "duration": 0.83},
    {"id": "bounce", "label": "弹跳", "group": "活泼", "duration": 0.50},
    {"id": "snap", "label": "脆响", "group": "强调", "duration": 0.38},
    {"id": "impact", "label": "低频强调", "group": "重点", "duration": 0.54},
    {"id": "ding", "label": "清脆叮", "group": "提示", "duration": 0.29},
    {"id": "water_drop", "label": "水滴", "group": "自然", "duration": 0.19},
    {"id": "bubble", "label": "气泡", "group": "活泼", "duration": 0.10},
    {"id": "swipe", "label": "滑动", "group": "转场", "duration": 0.60},
    {"id": "whoosh_fast", "label": "快速呼啸", "group": "转场", "duration": 0.31},
    {"id": "whoosh_soft", "label": "柔和呼啸", "group": "转场", "duration": 0.50},
    {"id": "riser", "label": "上升揭晓", "group": "氛围", "duration": 1.15},
    {"id": "magic", "label": "魔法闪现", "group": "氛围", "duration": 0.63},
    {"id": "camera", "label": "相机快门", "group": "生活", "duration": 0.30},
    {"id": "typing", "label": "键盘输入", "group": "生活", "duration": 1.00},
    {"id": "cash", "label": "收银提示", "group": "价格", "duration": 1.41},
    {"id": "drum", "label": "鼓点", "group": "节奏", "duration": 0.57},
    {"id": "boom", "label": "爆炸冲击", "group": "强调", "duration": 0.54},
    {"id": "error", "label": "错误提示", "group": "提示", "duration": 0.53},
    {"id": "heartbeat", "label": "心跳", "group": "氛围", "duration": 0.46},
    {"id": "clap", "label": "掌声", "group": "综艺", "duration": 1.20},
    {"id": "surprise", "label": "惊讶提示", "group": "综艺", "duration": 0.44},
]

SFX_LIBRARY_VERSION = "cc0-curated-v2"
SFX_CC0_SOURCES = {
    "pop": "interface-sounds/Audio/pluck_002.ogg",
    "shine": "interface-sounds/Audio/glass_001.ogg",
    "whoosh": "digital-audio/Audio/phaserUp2.ogg",
    "click": "interface-sounds/Audio/click_001.ogg",
    "tap": "impact-sounds/Audio/impactGeneric_light_003.ogg",
    "bell": "impact-sounds/Audio/impactBell_heavy_002.ogg",
    "chime": "interface-sounds/Audio/confirmation_002.ogg",
    "coin": "casino-audio/Audio/chips-collide-2.ogg",
    "success": "digital-audio/Audio/threeTone1.ogg",
    "bounce": "freesound-cc0/boing_161122_clip.wav",
    "snap": "interface-sounds/Audio/select_003.ogg",
    "impact": "impact-sounds/Audio/impactPunch_medium_002.ogg",
    "ding": "interface-sounds/Audio/confirmation_001.ogg",
    "water_drop": "interface-sounds/Audio/drop_003.ogg",
    "bubble": "interface-sounds/Audio/pluck_001.ogg",
    "swipe": "casino-audio/Audio/card-slide-3.ogg",
    "whoosh_fast": "digital-audio/Audio/phaserUp5.ogg",
    "whoosh_soft": "digital-audio/Audio/phaserDown3.ogg",
    "riser": "digital-audio/Audio/powerUp3.ogg",
    "magic": "digital-audio/Audio/pepSound4.ogg",
    "camera": "freesound-cc0/camera_170229_clip.wav",
    "typing": "interface-sounds/Audio/scroll_004.ogg",
    "cash": "freesound-cc0/cash_794903_clip.wav",
    "drum": "impact-sounds/Audio/impactSoft_heavy_002.ogg",
    "boom": "impact-sounds/Audio/impactPunch_heavy_001.ogg",
    "error": "interface-sounds/Audio/error_003.ogg",
    "heartbeat": "freesound-cc0/heartbeat_670465_clip.wav",
    "clap": "freesound-cc0/applause_462362_clip.wav",
    "surprise": "digital-audio/Audio/pepSound3.ogg",
}


def make_sfx_files() -> dict[str, Path]:
    import math
    import random
    import struct
    import wave

    directory = ROOT / "assets" / "sfx"
    directory.mkdir(parents=True, exist_ok=True)
    sample_rate = 44100

    # Build redistributable effects from Kenney's CC0 source packs. The version
    # marker forces a one-time replacement when the curated mapping changes.
    source_root = ROOT / "assets" / "sfx_sources"
    version_path = directory / ".library-version"
    current_version = version_path.read_text(encoding="utf-8").strip() if version_path.exists() else ""
    rebuild_cc0 = current_version != SFX_LIBRARY_VERSION
    if rebuild_cc0:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            for spec in SFX_CATALOG:
                name = str(spec["id"])
                source = source_root / SFX_CC0_SOURCES[name]
                destination = directory / f"{name}.wav"
                if not source.is_file():
                    continue
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                converted = subprocess.run(
                    [ffmpeg, "-y", "-v", "error", "-i", str(source),
                     "-af", "aformat=sample_fmts=s16:channel_layouts=mono,alimiter=limit=0.92",
                     "-ar", str(sample_rate), "-ac", "1", str(destination)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    creationflags=flags, cwd=ROOT,
                )
                if converted.returncode != 0:
                    destination.unlink(missing_ok=True)
            if all((directory / f"{spec['id']}.wav").is_file() for spec in SFX_CATALOG):
                version_path.write_text(SFX_LIBRARY_VERSION, encoding="utf-8")

    def sine(freq: float, t: float) -> float:
        return math.sin(2 * math.pi * freq * t)

    for spec in SFX_CATALOG:
        name, duration = str(spec["id"]), float(spec["duration"])
        path = directory / f"{name}.wav"
        if path.exists():
            continue
        rng = random.Random(20260905 + sum(ord(char) for char in name))
        frames = []
        total = int(sample_rate * duration)
        for i in range(total):
            t = i / sample_rate
            x = i / max(1, total - 1)
            fade = max(0.0, 1.0 - x)
            if name == "pop":
                value = sine(720 - 390 * x, t) * fade ** 4
            elif name == "shine":
                value = (sine(880, t) + .55 * sine(1320, t) + .28 * sine(1760, t)) * fade ** 2 / 1.83
            elif name == "whoosh":
                value = rng.uniform(-1, 1) * math.sin(math.pi * x) ** 1.6 * .52
            elif name == "click":
                value = (sine(1850, t) + .35 * sine(2600, t)) * fade ** 10 / 1.35
            elif name == "tap":
                value = (sine(245, t) + .32 * sine(490, t)) * fade ** 7 / 1.32
            elif name == "bell":
                value = (sine(740, t) + .48 * sine(1110, t) + .22 * sine(1850, t)) * fade ** 2.2 / 1.7
            elif name == "chime":
                value = 0.0
                for offset, freq in ((0.0, 659.25), (.12, 783.99), (.24, 987.77)):
                    if t >= offset:
                        local = t - offset
                        value += sine(freq, local) * math.exp(-5.0 * local) * .52
            elif name == "coin":
                first = sine(1568, t) * math.exp(-14 * t)
                second_t = max(0.0, t - .09)
                second = sine(2093, second_t) * math.exp(-12 * second_t) if t >= .09 else 0.0
                value = .65 * first + .72 * second
            elif name == "success":
                value = 0.0
                for offset, freq in ((0.0, 523.25), (.13, 659.25), (.26, 783.99)):
                    if t >= offset:
                        local = t - offset
                        value += sine(freq, local) * math.exp(-5.6 * local) * .55
            elif name == "bounce":
                value = sine(820 - 520 * x, t) * fade ** 3 * (.7 + .3 * math.cos(2 * math.pi * 5 * t))
            elif name == "snap":
                value = (rng.uniform(-1, 1) * .55 + sine(1250, t) * .45) * fade ** 13
            elif name == "impact":
                value = (sine(82 - 24 * x, t) * .78 + rng.uniform(-1, 1) * .16) * fade ** 5
            elif name == "ding":
                value = (sine(1175, t) + .38 * sine(1762, t)) * math.exp(-7.2 * t) / 1.38
            elif name == "water_drop":
                value = (sine(980 - 540 * x, t) + .18 * sine(1470 - 810 * x, t)) * math.exp(-8.5 * t) / 1.18
            elif name == "bubble":
                value = sine(330 + 780 * x, t) * math.sin(math.pi * x) ** 1.4 * .82
            elif name == "swipe":
                value = rng.uniform(-1, 1) * math.sin(math.pi * x) ** 1.7 * (.30 + .30 * sine(700 + 900 * x, t))
            elif name == "whoosh_fast":
                value = rng.uniform(-1, 1) * math.sin(math.pi * x) ** 1.25 * .62
            elif name == "whoosh_soft":
                value = rng.uniform(-1, 1) * math.sin(math.pi * x) ** 2.2 * .36
            elif name == "riser":
                value = (sine(150 + 1050 * x, t) * .42 + rng.uniform(-1, 1) * .18) * math.sin(math.pi * x) ** 1.15
            elif name == "magic":
                value = 0.0
                for offset, freq in ((0.0, 784), (.10, 1047), (.21, 1319), (.34, 1568)):
                    if t >= offset:
                        local = t - offset
                        value += sine(freq, local) * math.exp(-7.0 * local) * .34
            elif name == "camera":
                shutter = (t < .035) or (.085 <= t < .145)
                value = (rng.uniform(-1, 1) * .72 + sine(130, t) * .28) * (1.0 if shutter else 0.0)
            elif name == "typing":
                value = 0.0
                for offset in (0.0, .08, .17, .27, .38):
                    local = t - offset
                    if 0 <= local < .045:
                        value += (rng.uniform(-1, 1) * .45 + sine(900, local) * .30) * math.exp(-55 * local)
            elif name == "cash":
                value = 0.0
                for offset, freq in ((0.0, 1319), (.12, 1760), (.25, 2093)):
                    if t >= offset:
                        local = t - offset
                        value += sine(freq, local) * math.exp(-9.0 * local) * .42
            elif name == "drum":
                value = (sine(105 - 52 * x, t) + .22 * rng.uniform(-1, 1)) * math.exp(-13 * t) * .86
            elif name == "boom":
                value = (sine(62 - 20 * x, t) * .78 + sine(124 - 36 * x, t) * .18 + rng.uniform(-1, 1) * .12) * fade ** 3.4
            elif name == "error":
                value = 0.0
                for offset, freq in ((0.0, 420), (.19, 315)):
                    local = t - offset
                    if 0 <= local < .22:
                        value += sine(freq, local) * math.sin(math.pi * local / .22) * .60
            elif name == "heartbeat":
                value = 0.0
                for offset, strength in ((0.0, .78), (.18, .55), (.50, .70)):
                    local = t - offset
                    if 0 <= local < .13:
                        value += sine(72, local) * math.exp(-25 * local) * strength
            elif name == "clap":
                value = 0.0
                for offset, strength in ((0.0, .80), (.055, .48), (.105, .30)):
                    local = t - offset
                    if 0 <= local < .10:
                        value += rng.uniform(-1, 1) * math.exp(-28 * local) * strength
            elif name == "surprise":
                value = 0.0
                for offset, freq in ((0.0, 523), (.13, 784), (.28, 1175)):
                    if t >= offset:
                        local = t - offset
                        value += sine(freq, local) * math.exp(-8 * local) * .42
            else:
                value = (sine(82, t) * .8 + rng.uniform(-1, 1) * .2) * fade ** 5
            frames.append(struct.pack("<h", int(max(-1, min(1, value)) * 14500)))
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b"".join(frames))
    return {str(spec["id"]): directory / f"{spec['id']}.wav" for spec in SFX_CATALOG}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/desktop-health")
def desktop_health() -> dict[str, Any]:
    with JOBS_LOCK:
        active = sum(job.get("status") == "running" for job in JOBS.values())
    return {"application": "smart-video-packaging", "protocol": 1,
            "root": str(ROOT.resolve()), "active_jobs": active, 'version': '0.2.0'}


@app.get("/desktop.js")
def desktop_script():
    return FileResponse(ROOT / "static" / "desktop.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/ui-language.js")
def ui_language_script():
    return FileResponse(ROOT / "static" / "ui-language.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/edit-core.js")
def edit_core_script():
    return FileResponse(ROOT / "static" / "edit-core.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/editor.js")
def editor_script():
    return FileResponse(ROOT / "static" / "editor.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get('/review.js')
def review_script():
    return FileResponse(ROOT / 'static' / 'review.js', media_type='application/javascript', headers={'Cache-Control': 'no-cache'})


@app.get('/review.css')
def review_styles():
    return FileResponse(ROOT / 'static' / 'review.css', media_type='text/css', headers={'Cache-Control': 'no-cache'})


@app.get("/api/config")
def api_config() -> dict[str, Any]:
    recent_dir = Path(CONFIG["recent_videos_dir"])
    videos = sorted(recent_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True) if recent_dir.exists() else []
    return {
        "recent_videos": [str(x) for x in videos[:30]], "default_video": str(videos[0]) if videos else "",
        "exports_dir": str(EXPORTS), "models": dependency_status(), "low_memory": True,
        "fonts": installed_font_families(),
        "sfx_catalog": [dict(item) for item in SFX_CATALOG],
    }


@app.get("/api/sfx/{name}")
def preview_sfx(name: str):
    files = make_sfx_files()
    if name not in files:
        raise HTTPException(404, "音效不存在")
    return FileResponse(files[name], media_type="audio/wav")


def sfx_source_duration(name: str) -> float:
    spec = next((item for item in SFX_CATALOG if str(item["id"]) == name), None)
    return float(spec["duration"]) if spec else 0.3


def atempo_filters(source_duration: float, target_duration: float) -> list[str]:
    """Build an FFmpeg atempo chain that fits an effect into its timeline length."""
    rate = max(0.01, source_duration / max(0.08, target_duration))
    parts: list[str] = []
    while rate < 0.5:
        parts.append("atempo=0.5")
        rate /= 0.5
    while rate > 2.0:
        parts.append("atempo=2.0")
        rate /= 2.0
    parts.append(f"atempo={rate:.6f}")
    return parts


def write_sfx_track(
    output: Path, duration: float, markers: list[dict[str, Any]],
    sources: dict[str, Path], master_volume: float, *, sample_rate: int = 44100,
) -> Path:
    """Stream one float audio track to disk; memory is independent of video length."""
    import numpy as np

    @lru_cache(maxsize=32)
    def decode(kind: str, length: float) -> Any:
        source = sources.get(kind, sources["pop"])
        tempo = ",".join(atempo_filters(sfx_source_duration(kind), length))
        process = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(source), "-af",
             f"apad=pad_dur=0.15,{tempo},atrim=duration={length:.4f},asetpts=N/SR/TB",
             "-ar", str(sample_rate), "-ac", "1", "-f", "f32le", "-"],
            capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if process.returncode:
            raise RuntimeError(process.stderr.decode("utf-8", errors="replace")[-2000:])
        return np.frombuffer(process.stdout, dtype="<f4")

    schedule = []
    master_volume = max(0.0, min(float(master_volume), 1.0))
    for marker in markers:
        if not marker.get("enabled", True):
            continue
        start = max(0.0, float(marker.get("time", 0)))
        gain = master_volume * max(0.0, min(float(marker.get("volume", 1)), 2.0))
        if start >= duration or gain == 0:
            continue
        kind = str(marker.get("type", "pop"))
        if kind not in sources:
            kind = "pop"
        length = max(0.08, min(float(marker.get("duration", sfx_source_duration(kind))), 8.0))
        schedule.append((round(start * sample_rate), kind, length, gain))
    schedule.sort(key=lambda item: item[0])
    total_samples = round(duration * sample_rate)
    active: list[tuple[int, Any, float]] = []
    cursor = 0
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        for block_start in range(0, total_samples, sample_rate):
            block_end = min(total_samples, block_start + sample_rate)
            while cursor < len(schedule) and schedule[cursor][0] < block_end:
                start, kind, length, gain = schedule[cursor]
                active.append((start, decode(kind, length), gain))
                cursor += 1
            block = np.zeros(block_end - block_start, dtype="<f4")
            for start, samples, gain in active:
                left, right = max(block_start, start), min(block_end, start + len(samples))
                if right > left:
                    block[left - block_start:right - block_start] += samples[left - start:right - start] * gain
            handle.write(block.tobytes())
            active = [event for event in active if event[0] + len(event[1]) > block_end]
    return output


@app.get("/api/pick-video")
def pick_video(ui_language: Literal["zh", "en"] = "zh") -> dict[str, str]:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        english = ui_language == "en"
        path = filedialog.askopenfilename(title="Select an edited video" if english else "选择成片", filetypes=[("Videos" if english else "视频", "*.mp4 *.mov *.mkv *.m4v"), ("All files" if english else "全部文件", "*.*")])
        root.destroy()
        return {"video": path}
    except Exception as exc:
        raise HTTPException(500, f"无法打开选择窗口：{exc}")


@app.get("/api/pick-folder")
def pick_folder(ui_language: Literal["zh", "en"] = "zh") -> dict[str, str]:
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        path = filedialog.askdirectory(title="Select a folder of videos to process" if ui_language == "en" else "选择需要批量识别的视频文件夹")
        root.destroy()
        return {"folder": path}
    except Exception as exc:
        raise HTTPException(500, f"无法打开文件夹选择窗口：{exc}")


@app.post("/api/load")
def load_video(req: VideoRequest) -> dict[str, Any]:
    video = ensure_video(req.video)
    REVIEW.add([video])
    saved = read_json(project_path(video))
    if saved:
        saved['revision'] = revision(saved)
    media = probe_video(video)
    return {
        "video": str(video), "media": media, "product_name": product_name_from_filename(video),
        "project": saved, "video_url": f"/api/video?path={video}",
    }


@app.get("/api/video")
def video_file(path: str):
    video = ensure_video(path)
    return FileResponse(video, media_type="video/mp4")


@app.post("/api/start-auto")
def start_auto(req: VideoRequest) -> dict[str, str]:
    video = ensure_video(req.video)
    identities = REVIEW.add([video])
    if not REVIEW.claim_analysis(identities, force=True):
        raise QueueConflict('此视频已有进行中的任务')
    job_id = uuid.uuid4().hex
    job = {"id": job_id, "kind": "auto", "video": str(video), "status": "running", "stage": "排队", "message": "等待开始", "progress": 0, "created_at": time.time()}
    with JOBS_LOCK:
        JOBS[job_id] = job
        write_json(JOBS_DIR / f"{job_id}.json", job)
    threading.Thread(target=run_auto_job, args=(job_id, video, req.language, req.video_clips), daemon=True).start()
    return {"job_id": job_id}


@app.post("/api/start-batch")
def start_batch(req: BatchRequest) -> dict[str, Any]:
    imported = import_review_folder(req)
    result = start_review_analysis(ReviewSelection(ids=imported['ids'], language=req.language))
    return {**result, 'folder': req.folder}


@app.get('/api/review')
def review_listing():
    return {'items': REVIEW.listing(), 'batches': REVIEW.batch_listing(), 'exports_dir': str(EXPORTS)}


@app.post('/api/review/import')
def import_review_folder(req: BatchRequest):
    folder = Path(req.folder)
    if not folder.is_dir():
        raise HTTPException(404, f"文件夹不存在：{folder}")
    extensions = {".mp4", ".mov", ".mkv", ".m4v"}
    iterator = folder.rglob("*") if req.recursive else folder.iterdir()
    videos = sorted((path for path in iterator if path.is_file() and path.suffix.lower() in extensions), key=lambda path: path.name.casefold())
    if not videos:
        raise HTTPException(400, "所选文件夹中没有可处理的视频")
    batch_id, identities = REVIEW.add_batch(videos, folder)
    return {'ids': identities, 'count': len(identities), 'batch_id': batch_id, 'items': REVIEW.listing()}


def check_review_ids(identities):
    available = {item['id'] for item in REVIEW.listing()}
    if any(identity not in available for identity in identities):
        raise HTTPException(404, '待审阅项目不存在，请刷新列表')


@app.post('/api/review/analyze')
def start_review_analysis(req: ReviewSelection):
    check_review_ids(req.ids)
    claimed = REVIEW.claim_analysis(req.ids, force=req.reprocess)
    videos = [Path(item['video']) for item in claimed]
    if not videos:
        return {'job_id': None, 'count': 0}
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id, "kind": "batch", "video_count": len(videos),
        "status": "running", "stage": "排队", "message": f"等待处理{len(videos)}个视频",
        "progress": 0, "created_at": time.time(),
    }
    with JOBS_LOCK:
        JOBS[job_id] = job
        write_json(JOBS_DIR / f"{job_id}.json", job)
    threading.Thread(target=run_batch_job, args=(job_id, videos, req.language), daemon=True).start()
    return {"job_id": job_id, "count": len(videos)}


@app.post('/api/review/approve')
def approve_review(req: ReviewApproval):
    check_review_ids([req.id])
    return REVIEW.approve(req.id, req.revision, req.reviewed)


@app.post('/api/review/remove')
def remove_review(req: ReviewSelection):
    check_review_ids(req.ids)
    REVIEW.remove(req.ids)
    return {'items': REVIEW.listing()}


def run_export_job(job_id, snapshots):
    results = []
    with EXPORT_LOCK:
        for position, snapshot in enumerate(snapshots, 1):
            identity = snapshot['id']
            project = snapshot.get('project') or read_json(Path(snapshot['snapshot_path']))
            REVIEW.export_update(identity, 'exporting')
            update_job(job_id, message=f"正在导出 {position}/{len(snapshots)}：{Path(project['video']).name if project else identity}",
                       progress=int((position - 1) / len(snapshots) * 100))
            try:
                if not project:
                    raise ValueError('导出快照不存在，请重新加入导出队列')
                with MODEL_LOCK:
                    rendered = render_project(ProjectRequest(**project))
                REVIEW.export_update(identity, 'done', exported_revision=snapshot['revision'], output=rendered['output'])
                results.append({'id': identity, 'status': 'done', **rendered})
            except Exception as exc:
                message = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
                REVIEW.export_update(identity, 'error', error=message)
                results.append({'id': identity, 'status': 'error', 'message': message})
            finally:
                if snapshot.get('snapshot_path'):
                    Path(snapshot['snapshot_path']).unlink(missing_ok=True)
            update_job(job_id, result={'items': results}, progress=int(position / len(snapshots) * 100))
    completed = sum(item['status'] == 'done' for item in results)
    update_job(job_id, status='done', progress=100,
               message=f'导出完成：成功 {completed}，失败 {len(results) - completed}',
               result={'items': results, 'completed': completed, 'failed': len(results) - completed})


@app.post('/api/review/export')
def start_review_export(req: ReviewSelection):
    check_review_ids(req.ids)
    job_id = uuid.uuid4().hex
    snapshots = REVIEW.claim_exports(req.ids, JOBS_DIR / job_id / 'snapshots')
    with JOBS_LOCK:
        JOBS[job_id] = {'id': job_id, 'kind': 'export', 'status': 'running', 'progress': 0,
                        'message': '等待顺序导出', 'created_at': time.time(), 'count': len(snapshots)}
        atomic_json(JOBS_DIR / (job_id + '.json'), JOBS[job_id])
    threading.Thread(target=run_export_job, args=(job_id, snapshots), daemon=True).start()
    return {'job_id': job_id, 'count': len(snapshots)}


@app.get("/api/job/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    with JOBS_LOCK:
        job = copy.deepcopy(JOBS.get(job_id))
    if job is None:
        job = read_json(JOBS_DIR / f"{job_id}.json")
        if job and job.get('status') == 'running':
            job.update(status='error', message='任务被中断，请重新运行')
    if not job:
        raise HTTPException(404, "任务不存在")
    return job


@app.post("/api/save")
def save_project(req: ProjectRequest) -> dict[str, str]:
    video = ensure_video(req.video)
    data = req.model_dump()
    data["video"] = str(video)
    if req.video_clips is not None:
        try:
            data["video_clips"] = normalize_clips(req.video_clips, float(probe_video(video)["duration"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc))
    path = project_path(video)
    previous = read_json(path)
    current_revision = REVIEW.save(data, expected_revision=req.revision)
    snapshot = save_training_snapshot(data) if not previous or revision(previous) != current_revision else ''
    return {"project": str(path), "training_snapshot": str(snapshot), 'revision': current_revision}


@app.post("/api/validate")
def validate(req: ProjectRequest) -> dict[str, Any]:
    video = ensure_video(req.video)
    media = probe_video(video)
    try:
        media["duration"] = edit_duration(normalize_clips(req.video_clips, media["duration"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    return {"issues": validate_project(req.model_dump(), media)}


@app.get("/api/highlights")
def highlights(product: str) -> dict[str, Any]:
    library = Path(CONFIG["highlight_library"])
    if not library.exists() or not product.strip():
        return {"folders": [], "files": []}
    normalized = lambda s: "".join(c.lower() for c in s if c.isalnum())
    query = normalized(product)
    scored = []
    for folder in library.iterdir():
        if not folder.is_dir() or folder.name in ("图片素材", "训练材料"):
            continue
        name = normalized(folder.name)
        common = len(set(query) & set(name))
        score = common / max(len(set(query)), 1)
        if query in name or name in query:
            score += 1
        if score >= 0.32:
            scored.append((score, folder))
    scored.sort(key=lambda x: x[0], reverse=True)
    folders = [x[1] for x in scored[:5]]
    files = []
    for folder in folders:
        for file in folder.rglob("*"):
            if file.suffix.lower() in (".mp4", ".mov", ".jpg", ".jpeg", ".png", ".webp"):
                files.append({"name": file.name, "path": str(file), "product_folder": folder.name})
    return {"folders": [x.name for x in folders], "files": files[:40]}


@app.post("/api/render")
def render(req: ProjectRequest) -> dict[str, Any]:
    saved = save_project(req)
    identity = project_id(Path(req.video))
    REVIEW.approve(identity, saved['revision'])
    snapshots = REVIEW.claim_exports([identity])
    snapshot = snapshots[0]
    try:
        with EXPORT_LOCK, MODEL_LOCK:
            REVIEW.export_update(identity, 'exporting')
            result = render_project(ProjectRequest(**snapshot['project']))
        REVIEW.export_update(identity, 'done', exported_revision=snapshot['revision'], output=result['output'])
        return result
    except Exception as exc:
        REVIEW.export_update(identity, 'error', error=str(exc))
        raise


def render_project(req: ProjectRequest) -> dict[str, Any]:
    video = ensure_video(req.video)
    project = req.model_dump()
    media = probe_video(video)
    try:
        clips = normalize_clips(req.video_clips, media["duration"])
        if not clips:
            raise ValueError("时间轴没有视频片段")
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    media["duration"] = edit_duration(clips)
    issues = validate_project(project, media)
    blocking = [x for x in issues if x["level"] == "error"]
    if blocking:
        raise HTTPException(400, {"message": "存在未解决的硬规则问题", "issues": blocking})
    work = TEMP / 'exports' / uuid.uuid4().hex
    work.mkdir(parents=True, exist_ok=True)
    ass = work / "subtitle.ass"
    write_ass(project, ass, int(media.get("width") or 1080), int(media.get("height") or 1920))
    # Preserve earlier exports and distinguish equal names from different folders.
    output = EXPORTS / f"{safe_stem(video)}_智能包装_{datetime.now():%Y%m%d_%H%M%S_%f}_{project_id(video)[-10:]}.mp4"
    temporary_output = output.with_name(output.stem + '.partial.mp4')
    prepared = prepare_edited_video(video, clips, video_cache_dir(video) / ("export_" + edit_key(clips)), CONFIG.get("threads", 2))
    args = ["ffmpeg", "-y", "-v", "warning", "-i", str(prepared)]
    markers = [m for m in project.get("sound_markers", []) if m.get("enabled", True)]
    sfx = make_sfx_files()
    if markers:
        master_volume = max(0.0, min(float(project.get("settings", {}).get("sfx_volume", 0.50)), 1.0))
        sound_track = write_sfx_track(work / "sound_effects.f32", float(media["duration"]), markers, sfx, master_volume)
        args += ["-f", "f32le", "-ar", "44100", "-ac", "1", "-i", str(sound_track)]
        filters = "[0:v]ass=subtitle.ass[v];[0:a][1:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]"
        args += ["-filter_complex", filters, "-map", "[v]", "-map", "[a]"]
    else:
        args += ["-vf", "ass=subtitle.ass"]
    args += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", str(CONFIG.get("threads", 2)),
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(temporary_output),
    ]
    try:
        run(args, cwd=work)
        rendered_media = probe_video(temporary_output)
        if not rendered_media.get('video_codec') or abs(rendered_media['duration'] - media['duration']) > max(1, media['duration'] * .01):
            raise RuntimeError('导出校验失败：视频时长不完整')
        os.replace(temporary_output, output)
    finally:
        temporary_output.unlink(missing_ok=True)
        if markers:
            sound_track.unlink(missing_ok=True)
    return {"output": str(output), "issues": issues}


if __name__ == "__main__":
    import uvicorn
    make_sfx_files()
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
