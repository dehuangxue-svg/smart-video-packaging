from __future__ import annotations

import argparse
import gc
import re
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import (normalize_subtitle_text, product_name_from_filename, split_subtitle,
                  subtitle_text_limit, word_continues, write_json)


PUNCTUATION = set("，。！？；、,.!?;：:…‘’“”\"'（）()【】[]《》<>—- ")
STRONG_BREAKS = set("，。！？；,.!?;")


def clean_text(text: str) -> str:
    return normalize_subtitle_text(text)


def clean_token(token: str) -> str:
    token = re.sub(r"<\|[^>]+\|>", "", str(token))
    token = token.replace("▁", " ").replace("Ġ", " ")
    return re.sub(r"\s+", " ", token)


def median_step(starts: list[float]) -> float:
    steps = [b - a for a, b in zip(starts, starts[1:]) if 0.035 <= b - a <= 0.8]
    return statistics.median(steps) if steps else 0.18


def timed_characters_from_sensevoice(
    result: Any, segment_start: float, segment_end: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Convert SenseVoice token starts into absolute token and character intervals."""
    tokens = list(getattr(result, "tokens", []) or [])
    timestamps = list(getattr(result, "timestamps", []) or [])
    usable: list[tuple[str, float]] = []
    duration = max(0.0, segment_end - segment_start)
    for token, timestamp in zip(tokens, timestamps):
        text = clean_token(token)
        if not text or not any(char not in PUNCTUATION for char in text):
            continue
        relative = max(0.0, min(duration, float(timestamp)))
        usable.append((text, segment_start + relative))
    if not usable:
        return [], []

    starts = [item[1] for item in usable]
    typical = median_step(starts)
    timed_tokens: list[dict[str, Any]] = []
    timed_chars: list[dict[str, Any]] = []
    for index, (text, start) in enumerate(usable):
        next_start = starts[index + 1] if index + 1 < len(starts) else segment_end
        gap = max(0.0, next_start - start)
        if index + 1 < len(starts) and gap <= 0.5:
            end = next_start
        else:
            end = min(segment_end, start + max(0.12, min(0.38, typical * 1.65)))
        end = max(start + 0.06, min(segment_end, end))
        content = "".join(char for char in text if char not in PUNCTUATION)
        if not content:
            continue
        timed_tokens.append({"text": content, "start": round(start, 3), "end": round(end, 3)})
        width = max(0.001, end - start) / len(content)
        for char_index, char in enumerate(content):
            char_start = start + width * char_index
            char_end = start + width * (char_index + 1)
            timed_chars.append({"text": char, "start": char_start, "end": char_end,
                                "prefix": " " if char_index == 0 and text.startswith(" ") else ""})
    return timed_tokens, timed_chars


def timed_characters_from_whisper(
    segments: list[Any], offset: float, clip_end: float,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    text_parts: list[str] = []
    timed_tokens: list[dict[str, Any]] = []
    timed_chars: list[dict[str, Any]] = []
    for segment in segments:
        text_parts.append(str(segment.text or ""))
        words = list(segment.words or [])
        if not words:
            words = [segment]
        for word in words:
            source_text = str(word.word if hasattr(word, "word") else word.text)
            content = "".join(char for char in clean_text(source_text) if char not in PUNCTUATION)
            if not content:
                continue
            start = max(offset, min(clip_end, offset + float(word.start or 0)))
            end = max(start + 0.06, min(clip_end, offset + float(word.end or word.start or 0) + 0.02))
            timed_tokens.append({"text": content, "start": round(start, 3), "end": round(end, 3)})
            width = max(0.001, end - start) / len(content)
            for char_index, char in enumerate(content):
                timed_chars.append({
                    "text": char,
                    "start": start + width * char_index,
                    "end": start + width * (char_index + 1),
                    "prefix": " " if char_index == 0 and source_text.startswith(" ") else "",
                })
    return clean_text(" ".join(text_parts)), timed_tokens, timed_chars


def punctuation_marks(text: str, expected_chars: str) -> dict[int, str]:
    """Map punctuation to positions in the unpunctuated recognition text."""
    marks: dict[int, str] = {}
    content: list[str] = []
    count = 0
    for char in str(text):
        if char in PUNCTUATION:
            marks[count] = marks.get(count, "") + char
        else:
            content.append(char)
            count += 1
    if "".join(content).casefold() != expected_chars.casefold():
        return {}
    return marks


def subtitles_from_timed_chars(
    timed_chars: list[dict[str, Any]], punctuated_text: str,
    segment_start: float, segment_end: float, limit: int = 13, *, timestamp_source: str = "sensevoice_token",
) -> list[dict[str, Any]]:
    if not timed_chars:
        rows = split_subtitle(segment_start, segment_end, punctuated_text, limit=limit)
        for row in rows:
            row["timestamp_source"] = "estimated_segment"
        return rows
    limit = subtitle_text_limit(punctuated_text, limit)
    expected = "".join(item["text"] for item in timed_chars)
    marks = punctuation_marks(punctuated_text, expected)
    if not marks:
        marks = {index: char["prefix"] for index, char in enumerate(timed_chars) if char.get("prefix")}
    rows: list[dict[str, Any]] = []
    chunk: list[dict[str, Any]] = []
    chunk_text = marks.get(0, "")

    def flush(next_start: float | None = None) -> None:
        nonlocal chunk, chunk_text
        if not chunk:
            return
        start = max(segment_start, float(chunk[0]["start"]) - 0.03)
        end = min(segment_end, float(chunk[-1]["end"]) + 0.12)
        if next_start is not None:
            end = min(end, next_start - 0.03)
        end = min(segment_end, max(start + 0.06, end))
        rows.append({
            "start": round(start, 3), "end": round(end, 3), "text": chunk_text.strip(),
            "label": "other", "score": 0.0, "highlight_words": [], "selected": True,
            "timestamp_source": timestamp_source,
        })
        chunk = []
        chunk_text = ""

    for index, char in enumerate(timed_chars):
        chunk.append(char)
        chunk_text += str(char["text"])
        mark = marks.get(index + 1, "")
        if mark:
            chunk_text += mark
        next_char = timed_chars[index + 1] if index + 1 < len(timed_chars) else None
        gap = (float(next_char["start"]) - float(char["end"])) if next_char else 999.0
        duration = float(char["end"]) - float(chunk[0]["start"])
        strong = any(symbol in STRONG_BREAKS for symbol in mark)
        boundary = next_char is None or not word_continues(str(char["text"]), str(next_char["text"]), mark)
        enough = len(chunk) >= 2
        should_break = (
            (enough and strong)
            or (enough and gap >= 0.38)
            or len(chunk) >= limit
            or (enough and duration >= 4.2)
            or next_char is None
        )
        if should_break and boundary:
            flush(float(next_char["start"]) if next_char else None)

    punctuation_pattern = rf"[{re.escape(''.join(PUNCTUATION))}]"
    if len(rows) >= 2 and len(re.sub(punctuation_pattern, "", rows[-1]["text"])) <= 1:
        tail = rows.pop()
        if len(rows[-1]["text"]) + len(tail["text"]) <= limit + 3:
            separator = " " if re.search(r"[A-Za-z]", rows[-1]["text"][-1:] + tail["text"][:1]) else ""
            rows[-1]["text"] += separator + tail["text"]
            rows[-1]["end"] = tail["end"]
        else:
            rows.append(tail)
    return rows


def decode_sensevoice(
    recognizer: Any, samples: np.ndarray, start: float, end: float, punct: Any | None,
) -> dict[str, Any]:
    stream = recognizer.create_stream()
    stream.accept_waveform(16000, samples)
    recognizer.decode_stream(stream)
    result = stream.result
    raw_text = clean_text(result.text)
    # The installed punctuation model is Chinese. SenseVoice already supplies
    # English punctuation; sending Latin text through CT-Transformer loses spaces.
    text = punct.add_punctuation(raw_text) if punct is not None and raw_text and not re.search(r"[A-Za-z\uac00-\ud7af\u3040-\u30ff]", raw_text) else raw_text
    timed_tokens, timed_chars = timed_characters_from_sensevoice(result, start, end)
    subtitles = subtitles_from_timed_chars(timed_chars, text, start, end)
    model_language = str(getattr(result, "lang", "") or "").replace("<|", "").replace("|>", "")
    # Some exported checkpoints emit a constant language tag. Do not let a
    # conflicting tag force English audio through the Chinese fallback.
    language = model_language
    if re.search(r"[A-Za-z]{2}", raw_text) and not re.search(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", raw_text):
        language = "en"
    return {
        "start": round(start, 3), "end": round(end, 3), "text": text,
        "timed_tokens": timed_tokens, "timed_chars": timed_chars, "subtitles": subtitles,
        "engine": "sensevoice", "has_token_timestamps": bool(timed_chars),
        "language": language, "model_language": model_language,
    }


def candidate_score(candidate: dict[str, Any]) -> tuple[int, int, int]:
    return (
        1 if candidate.get("has_token_timestamps") else 0,
        len(candidate.get("timed_chars", [])),
        len(clean_text(candidate.get("text", ""))),
    )


def needs_fallback(candidate: dict[str, Any]) -> bool:
    duration = max(0.01, float(candidate["end"]) - float(candidate["start"]))
    count = len(candidate.get("timed_chars", []))
    return not candidate.get("text") or not candidate.get("has_token_timestamps") or (duration >= 1.2 and count / duration < 0.45)


def normalize_timeline(rows: list[dict[str, Any]], duration: float | None = None) -> list[dict[str, Any]]:
    rows = sorted((row for row in rows if row.get("text")), key=lambda row: (float(row["start"]), float(row["end"])))
    for index, row in enumerate(rows):
        row["id"] = index
        row["start"] = round(max(0.0, float(row["start"])), 3)
        row["end"] = round(max(row["start"] + 0.2, float(row["end"])), 3)
        if index and row["start"] < rows[index - 1]["end"]:
            boundary = round((row["start"] + rows[index - 1]["end"]) / 2, 3)
            rows[index - 1]["end"] = max(rows[index - 1]["start"] + 0.2, boundary - 0.01)
            row["start"] = boundary
        if duration is not None:
            row["end"] = min(row["end"], duration)
    return rows


def whisper_language(requested: str, detected: str = "") -> str | None:
    # Let Whisper detect the audio itself in auto mode; SenseVoice language
    # tags are not reliable on every converted checkpoint.
    language = requested
    if language == "yue":
        return "zh"
    return language if language in ("zh", "en", "ja", "ko") else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--tokens", required=True)
    parser.add_argument("--vad", required=True)
    parser.add_argument("--punctuation", default="")
    parser.add_argument("--fallback-model", default="")
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--language", choices=("auto", "zh", "en", "yue", "ja", "ko"), default="auto")
    args = parser.parse_args()

    import sherpa_onnx

    video = Path(args.video)
    for required in (Path(args.model), Path(args.tokens), Path(args.vad)):
        if not required.is_file():
            raise FileNotFoundError(f"缺少模型文件：{required}")

    recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
        model=args.model, tokens=args.tokens, num_threads=max(1, min(args.threads, 2)),
        use_itn=True, debug=False, language=args.language,
    )
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = args.vad
    config.silero_vad.threshold = 0.28
    config.silero_vad.min_silence_duration = 0.30
    config.silero_vad.min_speech_duration = 0.20
    config.silero_vad.max_speech_duration = 10
    config.sample_rate = 16000
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=40)

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(video), "-vn",
            "-af", "aresample=async=1:first_pts=0", "-f", "s16le", "-acodec", "pcm_s16le",
            "-ac", "1", "-ar", "16000", "-",
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags,
    )
    if process.returncode:
        raise RuntimeError(process.stderr.decode("utf-8", errors="replace")[-2000:])
    audio = np.frombuffer(process.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    window_size = config.silero_vad.window_size
    for offset in range(0, len(audio), window_size):
        window = audio[offset:offset + window_size]
        if len(window) < window_size:
            window = np.pad(window, (0, window_size - len(window)))
        vad.accept_waveform(window)
    vad.flush()
    segments: list[dict[str, Any]] = []
    while not vad.empty():
        front = vad.front
        start_sample = int(front.start)
        sample_count = len(front.samples)
        segments.append({"start_sample": start_sample, "end_sample": start_sample + sample_count})
        vad.pop()

    punct = None
    punctuation_path = Path(args.punctuation) if args.punctuation else None
    if punctuation_path and punctuation_path.is_file():
        punct_config = sherpa_onnx.OfflinePunctuationConfig(
            model=sherpa_onnx.OfflinePunctuationModelConfig(ct_transformer=str(punctuation_path)),
        )
        punct = sherpa_onnx.OfflinePunctuation(punct_config)

    candidates: list[dict[str, Any]] = []
    retry_count = 0
    for segment_index, segment in enumerate(segments):
        start_sample = max(0, segment["start_sample"] - 3200)
        end_sample = min(len(audio), segment["end_sample"] + 3200)
        if segment_index:
            start_sample = max(start_sample, (segments[segment_index - 1]["end_sample"] + segment["start_sample"]) // 2)
        if segment_index + 1 < len(segments):
            end_sample = min(end_sample, (segment["end_sample"] + segments[segment_index + 1]["start_sample"]) // 2)
        start, end = start_sample / 16000, end_sample / 16000
        candidate = decode_sensevoice(recognizer, audio[start_sample:end_sample], start, end, punct)
        if needs_fallback(candidate):
            retry_start = max(0, start_sample - int(0.25 * 16000))
            retry_end = min(len(audio), end_sample + int(0.25 * 16000))
            retried = decode_sensevoice(
                recognizer, audio[retry_start:retry_end], retry_start / 16000, retry_end / 16000, punct,
            )
            retry_count += 1
            if candidate_score(retried) > candidate_score(candidate):
                candidate = retried
                candidate["engine"] = "sensevoice_retry"
        candidates.append(candidate)

    fallback_pending = [index for index, candidate in enumerate(candidates) if needs_fallback(candidate)]
    fallback_used = 0
    fallback_error = ""
    del recognizer, punct, vad
    gc.collect()

    fallback_path = Path(args.fallback_model) if args.fallback_model else None
    if fallback_pending and fallback_path and fallback_path.exists():
        try:
            from faster_whisper import WhisperModel

            fallback = WhisperModel(
                str(fallback_path), device="cpu", compute_type="int8",
                cpu_threads=max(1, min(args.threads, 2)), num_workers=1, local_files_only=True,
            )
            product = product_name_from_filename(video)
            for index in fallback_pending:
                source = candidates[index]
                clip_start = max(0.0, float(source["start"]) - 0.25)
                clip_end = min(len(audio) / 16000, float(source["end"]) + 0.25)
                clip = audio[int(clip_start * 16000):int(clip_end * 16000)]
                result_segments, info = fallback.transcribe(
                    clip, language=whisper_language(args.language, source.get("language", "")), beam_size=2, word_timestamps=True, vad_filter=False,
                    condition_on_previous_text=False, hotwords=product, temperature=0.0,
                )
                result_segments = list(result_segments)
                text, timed_tokens, timed_chars = timed_characters_from_whisper(result_segments, clip_start, clip_end)
                if text and timed_chars:
                    replacement = {
                        "start": round(clip_start, 3), "end": round(clip_end, 3), "text": text,
                        "timed_tokens": timed_tokens, "timed_chars": timed_chars,
                        "subtitles": subtitles_from_timed_chars(timed_chars, text, clip_start, clip_end, timestamp_source="whisper_word"),
                        "engine": "faster_whisper_base_int8", "has_token_timestamps": True,
                        "language": getattr(info, "language", ""),
                    }
                    if candidate_score(replacement) > candidate_score(source):
                        candidates[index] = replacement
                        fallback_used += 1
            del fallback
            gc.collect()
        except Exception as exc:
            fallback_error = str(exc)[:500]

    subtitles = normalize_timeline([row for candidate in candidates for row in candidate.get("subtitles", [])], len(audio) / 16000)
    speech_segments: list[dict[str, Any]] = []
    timed_tokens: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    speech_duration = 0.0
    recognized_duration = 0.0
    for index, candidate in enumerate(candidates):
        start, end = float(candidate["start"]), float(candidate["end"])
        duration = max(0.0, end - start)
        speech_duration += duration
        if candidate.get("text") and candidate.get("has_token_timestamps"):
            recognized_duration += duration
        else:
            unresolved.append({"segment": index, "start": round(start, 3), "end": round(end, 3), "reason": "语音段未获得可靠文字时间戳"})
        speech_segments.append({
            "start": round(start, 3), "end": round(end, 3), "text": candidate.get("text", ""),
            "engine": candidate.get("engine", "sensevoice"),
            "has_token_timestamps": bool(candidate.get("has_token_timestamps")),
            "language": candidate.get("language", ""),
            "model_language": candidate.get("model_language", ""),
        })
        timed_tokens.extend(candidate.get("timed_tokens", []))

    coverage_ratio = recognized_duration / speech_duration if speech_duration else 1.0
    quality = {
        "status": "ok" if not unresolved and coverage_ratio >= 0.985 else "needs_review",
        "timestamp_mode": "token",
        "vad_segments": len(segments),
        "recognized_segments": len(candidates) - len(unresolved),
        "sensevoice_retries": retry_count,
        "fallback_segments": fallback_used,
        "speech_seconds": round(speech_duration, 3),
        "recognized_speech_seconds": round(recognized_duration, 3),
        "uncovered_speech_seconds": round(max(0.0, speech_duration - recognized_duration), 3),
        "coverage_ratio": round(coverage_ratio, 4),
        "issues": unresolved,
    }
    if fallback_error:
        quality["fallback_error"] = fallback_error

    result = {
        "engine": "SenseVoiceSmall INT8 + Silero VAD + 逐字CTC时间戳" + (" + CT-Transformer标点" if punctuation_path and punctuation_path.is_file() else "") + (" + faster-whisper局部回退" if fallback_used else ""),
        "video": str(video),
        "product_name": product_name_from_filename(video),
        "requested_language": args.language,
        "detected_languages": sorted({item.get("language", "") for item in candidates} - {""}),
        "speech_segments": speech_segments,
        "timed_tokens": timed_tokens,
        "subtitles": subtitles,
        "quality": quality,
    }
    write_json(Path(args.output), result)


if __name__ == "__main__":
    main()
