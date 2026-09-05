from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from bisect import bisect_left, insort
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG_FILE = ROOT / "config.json"


def load_config() -> dict[str, Any]:
    data = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8-sig"))
    if CONFIG_FILE.is_file():
        data.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig")))
    path_keys = ("projects_dir", "jobs_dir", "training_dir", "temp_dir", "cache_dir",
                 "exports_dir", "recent_videos_dir", "highlight_library", "sensevoice_model",
                 "sensevoice_tokens", "silero_vad", "faster_whisper_model", "punctuation_model",
                 "face_model", "qwen_model", "llama_cli")
    for key in path_keys:
        if data.get(key):
            path = Path(data[key]).expanduser()
            data[key] = str(path if path.is_absolute() else (ROOT / path).resolve())
    for key in ("projects_dir", "jobs_dir", "training_dir", "temp_dir", "cache_dir", "exports_dir", "recent_videos_dir"):
        Path(data[key]).mkdir(parents=True, exist_ok=True)
    return data


def run(args: list[str], *, cwd: Path | None = None) -> str:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    if process.returncode:
        message = (process.stderr or process.stdout or "命令执行失败").strip()
        raise RuntimeError(message[-4000:])
    return process.stdout.strip()


def safe_stem(path: Path) -> str:
    stem = re.sub(r'[<>:"/\\|?*]+', "_", path.stem).strip(" ._")
    return stem[:100] or "video"


def project_id(video: Path) -> str:
    digest = hashlib.sha1(str(video.resolve()).lower().encode("utf-8")).hexdigest()[:10]
    return f"{safe_stem(video)}_{digest}"


def product_name_from_filename(video: Path) -> str:
    name = video.stem
    name = re.sub(r"^\d{4}[.-]\d{1,2}[.-]\d{1,2}", "", name)
    name = re.sub(r"^\d+_", "", name)
    name = re.sub(r"_(功效|卖点)精剪.*$", "", name)
    name = re.sub(r"_v\d+.*$", "", name, flags=re.I)
    for suffix in ("_插入实拍", "_字幕版", "_智能包装", "-1", "-2", "-3"):
        name = name.replace(suffix, "")
    return name.strip("_ -（）()")


def probe_video(video: Path) -> dict[str, Any]:
    raw = run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=index,codec_type,codec_name,width,height,r_frame_rate",
        "-of", "json", str(video),
    ])
    data = json.loads(raw)
    streams = data.get("streams", [])
    v = next((x for x in streams if x.get("codec_type") == "video"), {})
    a = next((x for x in streams if x.get("codec_type") == "audio"), {})
    return {
        "duration": round(float(data.get("format", {}).get("duration", 0)), 3),
        "width": v.get("width", 0),
        "height": v.get("height", 0),
        "fps": v.get("r_frame_rate", ""),
        "video_codec": v.get("codec_name", ""),
        "audio_codec": a.get("codec_name", ""),
    }


def normalize_subtitle_text(text: str) -> str:
    text = re.sub(r"<\|[^>]+\|>", "", str(text))
    text = re.sub(r"\s+", " ", text).strip()
    # CJK token separators are not word spaces; Latin/Korean spaces are.
    text = re.sub(r"(?<=[\u3400-\u9fff\u3040-\u30ff]) +(?=[\u3400-\u9fff\u3040-\u30ff])", "", text)
    return re.sub(r" +([，。！？；、,.!?;:])", r"\1", text)


def is_word_character(char: str) -> bool:
    return bool(char and char.isalnum() and not re.match(r"[\u3400-\u9fff\u3040-\u30ff]", char))


def word_continues(left: str, right: str, separator: str) -> bool:
    return (is_word_character(left) and is_word_character(right)
            and (not separator or separator in ("'", "’", "-")
                 or (separator == "." and left.isdigit() and right.isdigit())))


def subtitle_text_limit(text: str, cjk_limit: int = 13) -> int:
    latin = len(re.findall(r"[A-Za-z]", text))
    cjk = len(re.findall(r"[\u3400-\u9fff\u3040-\u30ff]", text))
    return max(42, cjk_limit) if latin > cjk else cjk_limit


def split_subtitle(start: float, end: float, text: str, limit: int = 13) -> list[dict[str, Any]]:
    text = normalize_subtitle_text(text)
    text = re.sub(r"<\|[^>]+\|>", "", text).strip("，。！？；,.!?; ")
    if not text or end <= start:
        return []
    limit = subtitle_text_limit(text, limit)
    clauses = [x for x in re.split(r"(?<=[，。！？；,!?;])|(?<=\.)(?!\d)", text) if x]
    if not clauses:
        clauses = [text]
    chunks: list[str] = []
    for clause in clauses:
        clause = clause.strip()
        while len(clause) > limit:
            cut = max((clause.rfind(mark, 0, limit + 1) + 1 for mark in "，；、"), default=0)
            if cut < 4:
                cut = limit
                for word in re.finditer(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+|\.\d+)*", clause):
                    if word.start() < cut < word.end():
                        cut = word.end()
                        break
                while cut < len(clause) and word_continues(clause[cut - 1], clause[cut], ""):
                    cut += 1
            chunks.append(clause[:cut].strip("，；、 "))
            clause = clause[cut:]
        if clause.strip("，。！？；,.!?; "):
            chunks.append(clause.strip())
    total_chars = max(sum(len(x) for x in chunks), 1)
    cursor = start
    result: list[dict[str, Any]] = []
    for chunk in chunks:
        piece = (end - start) * len(chunk) / total_chars
        item_end = min(end, cursor + piece)
        result.append({
            "start": round(cursor, 3), "end": round(item_end, 3), "text": chunk,
            "label": "other", "score": 0.0, "highlight_words": [], "selected": True,
        })
        cursor = item_end
    if result:
        result[-1]["end"] = round(end, 3)
    return result


def sound_marker_target(duration: float) -> int:
    """Short-video tiers, then seven effects per minute without a length cap."""
    if not math.isfinite(duration) or duration <= 0:
        return 0
    if duration < 60:
        return max(1, math.ceil(duration / 6))
    if duration <= 75:
        return 10
    if duration <= 100:
        return 12
    if duration <= 120:
        return 14
    return math.ceil(duration * 7 / 60)


ENGLISH_SIGNALS = {
    "benefit": r"moisturi[sz](?:e|es|ing)|hydrat(?:e|es|ing|ion)|soft(?:er|ness)?|smooth(?:er)?|cleans?|cleaning|fresh(?:ness)?|long[- ]lasting|easy to use|comfortable|delicious|tasty|crisp[y]?|oil control|repair[s]?|improve[s]?|relief|scent|fragrance",
    "selling_point": r"ingredients?|formula|material[s]?|design|patent(?:ed)?|certified|organic|sugar[- ]free|low sugar|capacity|stainless steel|cotton|packaging|individually wrapped",
    "remove": r"subscribe|follow me|buy now|order now|click the link|add to cart|limited stock",
    "price": r"price|discount|save|sale|dollars?|pounds?|euros?|deal",
    "action": r"click|order now|add to cart|buy now",
    "complete": r"complete|all done|finished|bundle|set of",
    "surprise": r"amazing|surpris(?:e|ing)|incredible|wow|unbelievable",
}


def english_caption_signals(text: str) -> dict[str, list[str]]:
    return {kind: [match.group(0) for match in re.finditer(r"\b(?:" + pattern + r")\b", text, re.I)]
            for kind, pattern in ENGLISH_SIGNALS.items()}


def suggest_sound_markers(
    subtitles: list[dict[str, Any]], hook_end: float, *, max_markers: int | None = None, min_spacing: float = 4.0,
    video_duration: float | None = None,
) -> list[dict[str, Any]]:
    """Spread meaningful effects across the full video, keeping the opening clear."""

    def effect_for(text: str, label: str, index: int) -> tuple[str, str]:
        english = english_caption_signals(text)
        if english["price"] or re.search(r"到手|价格|优惠|便宜|省钱|立减|\d+[块元]|单买|补货", text):
            return ("cash" if re.search(r"到手|优惠|立减|补货", text) else "coin", "价格信息")
        if english["action"] or re.search(r"点击|上车|链接|开拍|下单|拍下|抢", text):
            return ("click", "操作提示")
        if english["selling_point"] or re.search(r"配料|成分|用料|含有|添加|材质|工艺", text):
            return ("chime", "产品细节")
        if english["benefit"] or re.search(r"香|留香|清洁|干净|亮|白|控油|保湿|修护|改善|好吃|口感", text):
            return (("shine", "效果强调") if index % 2 == 0 else ("ding", "效果强调"))
        if english["complete"] or re.search(r"全部|一套|组合|完成|搞定|最后|收尾", text):
            return ("success", "组合或收尾")
        if english["surprise"] or re.search(r"真的|居然|竟然|这么|特别|非常|太[大好香]|没想到", text):
            return ("surprise", "惊喜强调")
        if label == "selling_point":
            return (("shine", "重点强调") if index % 2 == 0 else ("chime", "重点强调"))
        if label == "benefit":
            return (("pop", "效果强调") if index % 2 == 0 else ("ding", "效果强调"))
        fallback = ("pop", "snap", "tap", "bounce")
        return (fallback[index % len(fallback)], "节奏强调")

    duration = float(video_duration) if video_duration is not None else max(
        (float(item.get("end", item.get("start", 0))) for item in subtitles), default=0.0,
    )
    target = max_markers if max_markers is not None else sound_marker_target(duration)
    target = max(0, int(target))
    if not target or duration <= hook_end + 0.3:
        return []
    ordered = sorted(subtitles, key=lambda item: float(item.get("start", 0)))
    candidates: list[dict[str, Any]] = []
    for index, sub in enumerate(ordered):
        label = str(sub.get("label", "other"))
        text = str(sub.get("text", "")).strip()
        start = float(sub.get("start", 0))
        if not sub.get("selected", True) or label == "remove" or not hook_end + 0.3 <= start < duration:
            continue
        is_primary = label in ("benefit", "selling_point")
        has_signal = any(english_caption_signals(text).values()) or bool(sub.get("highlight_words")) or bool(re.search(
            r"到手|价格|优惠|便宜|省钱|立减|块|元|点击|上车|链接|下单|配料|成分|用料|工艺|"
            r"香|清洁|干净|亮|白|控油|保湿|修护|改善|好吃|口感|全部|套装|组合|真的|特别|非常",
            text,
        ))
        if not is_primary and (len(text) < 4 or not has_signal):
            continue
        score = (4.0 if is_primary else 1.0) + (1.0 if sub.get("highlight_words") else 0.0) + min(len(text), 20) / 100
        kind, reason = effect_for(text, label, index)
        candidates.append({"time": start, "type": kind, "reason": reason, "score": score})

    selected: list[dict[str, Any]] = []
    selected_times: list[float] = []

    def available(at: float, spacing: float) -> bool:
        index = bisect_left(selected_times, at)
        return ((index == 0 or at - selected_times[index - 1] >= spacing)
                and (index == len(selected_times) or selected_times[index] - at >= spacing))

    def select(candidate: dict[str, Any]) -> None:
        selected.append(candidate)
        insort(selected_times, candidate["time"])

    # Allocate one preferred event per time window before filling spare slots.
    # Otherwise equal scores can consume the entire quota near the beginning.
    origin = hook_end + 0.3
    window_size = (duration - origin) / target
    windows: dict[int, list[dict[str, Any]]] = {}
    for candidate in candidates:
        slot = min(target - 1, int((candidate["time"] - origin) / window_size))
        windows.setdefault(slot, []).append(candidate)
    for slot, options in sorted(windows.items()):
        center = origin + (slot + 0.5) * window_size
        for candidate in sorted(options, key=lambda item: (-item["score"], abs(item["time"] - center))):
            if available(candidate["time"], min_spacing):
                select(candidate)
                break

    for candidate in sorted(candidates, key=lambda item: (-item["score"], item["time"])):
        if len(selected) >= target:
            break
        if available(candidate["time"], min_spacing):
            select(candidate)

    if len(selected) < target:
        supplemental = []
        chosen_times = {item["time"] for item in selected}
        for index, sub in enumerate(ordered):
            text = str(sub.get("text", "")).strip()
            label = str(sub.get("label", "other"))
            start = float(sub.get("start", 0))
            if (not sub.get("selected", True) or label == "remove" or len(text) < 4
                    or not hook_end + 0.3 <= start < duration or start in chosen_times):
                continue
            kind, reason = effect_for(text, label, index)
            supplemental.append({"time": start, "type": kind, "reason": reason, "score": 0.0})
        while supplemental and len(selected) < target:
            viable = [item for item in supplemental if available(item["time"], min_spacing)]
            while not viable and min_spacing > 3.0:
                min_spacing = max(3.0, min_spacing - 0.5)
                viable = [item for item in supplemental if available(item["time"], min_spacing)]
            if not viable:
                break
            def nearest_distance(item: dict[str, Any]) -> float:
                at = item["time"]
                index = bisect_left(selected_times, at)
                return min((abs(at - other) for other in selected_times[max(0, index - 1):index + 1]), default=duration)
            best = max(viable, key=nearest_distance)
            select(best)
            supplemental.remove(best)

    return [
        {
            "time": round(item["time"], 2), "type": item["type"], "enabled": True, "volume": 1.0,
            "reason": item["reason"], "source": "auto",
        }
        for item in sorted(selected, key=lambda item: item["time"])[:target]
    ]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, centiseconds = divmod(centiseconds, 360000)
    minutes, centiseconds = divmod(centiseconds, 6000)
    secs, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def ass_color(html_color: str) -> str:
    value = re.sub(r"[^0-9A-Fa-f]", "", html_color).ljust(6, "F")[:6]
    r, g, b = value[0:2], value[2:4], value[4:6]
    return f"&H00{b}{g}{r}".upper()


def highlight_ass_text(text: str, words: list[str], normal: str, accent: str) -> str:
    escaped = ass_escape(text)
    valid = sorted({ass_escape(w.strip()) for w in words if w.strip()}, key=len, reverse=True)
    for word in valid:
        escaped = escaped.replace(word, f"{{\\c{accent}}}{word}{{\\c{normal}}}")
    return escaped


def write_ass(project: dict[str, Any], path: Path, width: int, height: int) -> None:
    settings = project.get("settings", {})
    font = str(settings.get("font", "Microsoft YaHei UI"))
    size = int(settings.get("font_size", 54))
    margin = int(settings.get("margin_v", 180))
    normal = ass_color(str(settings.get("text_color", "#FFFFFF")))
    accent = ass_color(str(settings.get("highlight_color", "#FFD43B")))
    outline = ass_color(str(settings.get("outline_color", "#101010")))
    x_percent = max(0.0, min(100.0, float(settings.get("subtitle_x", 50))))
    default_y = 100.0 - (margin * 100.0 / max(height, 1))
    y_percent = max(0.0, min(100.0, float(settings.get("subtitle_y", default_y))))
    x_position = int(round(width * x_percent / 100.0))
    y_position = int(round(height * y_percent / 100.0))
    position = f"{{\\an2\\pos({x_position},{y_position})}}"
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
        f"Style: Default,{font},{size},{normal},{normal},{outline},&H44000000,-1,0,0,0,100,100,0,0,1,4,1,2,50,50,{margin},1",
        "", "[Events]",
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text",
    ]
    for sub in project.get("subtitles", []):
        if not sub.get("selected", True) or not str(sub.get("text", "")).strip():
            continue
        text = position + highlight_ass_text(str(sub["text"]), list(sub.get("highlight_words", [])), normal, accent)
        lines.append(
            f"Dialogue: 0,{ass_time(float(sub['start']))},{ass_time(float(sub['end']))},Default,,0,0,0,,{text}"
        )
    path.write_text("\n".join(lines), encoding="utf-8-sig")


def validate_project(project: dict[str, Any], media: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    duration = float(media.get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        issues.append({"level": "error", "message": "视频时长无效，请重新载入有效视频"})
    hook_end = float(project.get("settings", {}).get("hook_end", 0))
    packaging = bool(project.get("model_output", {}).get("asr")) or project.get("video_clips") is None
    if packaging and not 3 <= hook_end <= 10:
        issues.append({"level": "warning" if project.get("video_clips") is not None else "error", "message": "Hook结束时间必须在3–10秒之间"})
    settings = project.get("settings", {})
    font_size = int(settings.get("font_size", 54))
    if not 16 <= font_size <= 160:
        issues.append({"level": "error", "message": "字幕字号必须在16–160之间"})
    for key, label in (("subtitle_x", "横向位置"), ("subtitle_y", "纵向位置")):
        value = float(settings.get(key, 50 if key == "subtitle_x" else 90))
        if not 0 <= value <= 100:
            issues.append({"level": "error", "message": f"字幕{label}必须在0–100%之间"})
    subtitles = [s for s in project.get("subtitles", []) if s.get("selected", True)]
    ordered = sorted(subtitles, key=lambda x: float(x.get("start", 0)))
    for i, sub in enumerate(ordered):
        start, end = float(sub.get("start", 0)), float(sub.get("end", 0))
        if start < 0 or end <= start or end > duration + 0.1:
            issues.append({"level": "error", "message": f"字幕{i + 1}时间不合法：{start:.2f}–{end:.2f}"})
        if i and start < float(ordered[i - 1].get("end", 0)) - 0.02:
            issues.append({"level": "warning", "message": f"字幕{i}和字幕{i + 1}时间重叠"})
        if sub.get("edit_review"):
            issues.append({"level": "warning", "message": f"字幕{i + 1}被剪辑边界截断，请回听并修改文字"})
    asr_quality = project.get("asr_quality", {}) or project.get("model_output", {}).get("asr", {}).get("quality", {})
    if asr_quality:
        uncovered = float(asr_quality.get("uncovered_speech_seconds", 0) or 0)
        if asr_quality.get("timestamp_mode") != "token":
            issues.append({"level": "warning", "message": "当前字幕不是逐字时间戳，请重新识别以避免时间轴漂移"})
        if asr_quality.get("status") == "needs_review" or uncovered > 0.45:
            issues.append({"level": "warning", "message": f"语音覆盖质检发现 {uncovered:.2f} 秒需要回听"})
        if asr_quality.get("fallback_error"):
            issues.append({"level": "warning", "message": "备用识别器未能运行，请检查本地模型"})
    hook_lines = [s for s in ordered if float(s.get("start", 0)) < hook_end]
    if packaging and not any(s.get("label") in ("benefit", "selling_point") for s in hook_lines):
        issues.append({"level": "warning" if project.get("video_clips") is not None else "error", "message": "Hook内没有识别到功效或明确卖点"})
    visual = project.get("visual", {})
    hook_samples = [x for x in visual.get("samples", []) if float(x.get("time", 0)) <= hook_end]
    if hook_samples and any(not x.get("host_visible", False) for x in hook_samples):
        issues.append({"level": "warning", "message": "Hook抽检画面中存在未检测到主播的时刻，请人工确认"})
    if ordered:
        last = re.sub(r"[，。！？；,.!?; ]+$", "", str(ordered[-1].get("text", "")))
        if re.search(r"(因为|所以|然后|但是|如果|而且|或者|就是|这个|那个|让|把|给)$", last):
            issues.append({"level": "error", "message": "最后一句疑似没有说完，请回听并调整结束点"})
    if not issues:
        issues.append({"level": "ok", "message": "硬规则检查通过；导出前仍需人工回听开头和结尾"})
    return issues
