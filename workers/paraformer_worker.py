"""Paraformer-zh ASR with native character-level timestamps."""
from __future__ import annotations

import argparse
import gc
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import product_name_from_filename, subtitle_text_limit, write_json
from workers.asr_worker import punctuation_marks, subtitles_from_timed_chars

ALIGN_SKIP = set("，。！？；、,.!?;：:…‘’“”\"'（）()【】[]《》<>—- ")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--vad", required=True)
    parser.add_argument("--punc", required=True)
    parser.add_argument("--align-model", default="")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()

    from funasr import AutoModel

    video = Path(args.video)
    output = Path(args.output)
    wav = output.with_suffix(".paraformer.wav")
    text_file = output.with_suffix(".paraformer.txt")
    ffmpeg = "ffmpeg"
    process = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-i", str(video), "-vn", "-af", "aresample=async=1:first_pts=0",
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    if process.returncode:
        raise RuntimeError(process.stderr.decode("utf-8", errors="replace")[-2000:])

    try:
        with wave.open(str(wav), "rb") as stream:
            duration = stream.getnframes() / float(stream.getframerate() or 16000)
        model = AutoModel(
            model=args.model,
            vad_model=args.vad,
            punc_model=args.punc,
            device="cpu",
            disable_update=True,
        )
        result = model.generate(input=str(wav), batch_size_s=300)
        item = result[0] if result else {}
        raw_text = str(item.get("text", ""))
        timestamps = list(item.get("timestamp") or [])
        native_timestamps = list(timestamps)
        native_start = (float(native_timestamps[0][0]) / 1000.0
                        if native_timestamps and len(native_timestamps[0]) >= 2 else 0.0)
        native_end = (float(native_timestamps[-1][1]) / 1000.0
                      if native_timestamps and len(native_timestamps[-1]) >= 2 else 0.0)
        alignment_mode = "paraformer_char"
        if args.align_model and Path(args.align_model).is_dir() and raw_text.strip():
            native_chars = [
                {"text": char, "start": float(pair[0]) / 1000.0, "end": float(pair[1]) / 1000.0}
                for char, pair in zip([char for char in raw_text if not char.isspace() and char not in ALIGN_SKIP], native_timestamps)
                if len(pair) >= 2
            ]
            del model
            gc.collect()
            # Obtain speech regions first. fa-zh is reliable on bounded
            # regions but can drift or truncate long recordings.
            vad_model = AutoModel(model=args.vad, device="cpu", disable_update=True)
            vad_result = vad_model.generate(input=str(wav))
            vad_regions = list((vad_result[0] if vad_result else {}).get("value") or [])
            del vad_model
            gc.collect()
            if not vad_regions:
                vad_regions = [[round(native_start * 1000), round(native_end * 1000)]]
            aligned_timestamps = []
            aligner = AutoModel(model=args.align_model, device="cpu", disable_update=True)
            with wave.open(str(wav), "rb") as source:
                sample_rate = source.getframerate()
                channels = source.getnchannels()
                sample_width = source.getsampwidth()
                for index, region in enumerate(vad_regions):
                    if len(region) < 2:
                        continue
                    region_start = max(0.0, float(region[0]) / 1000.0)
                    region_end = min(duration, float(region[1]) / 1000.0)
                    selected = [char for char in native_chars
                                if char["end"] > region_start and char["start"] < region_end]
                    if not selected or region_end <= region_start:
                        continue
                    seg_start = max(0.0, region_start - 0.15)
                    seg_end = min(duration, region_end + 0.15)
                    source.setpos(min(source.getnframes(), int(seg_start * sample_rate)))
                    frames = source.readframes(max(1, int((seg_end - seg_start) * sample_rate)))
                    segment_wav = output.with_name(f"{output.stem}.fa-{index:04d}.wav")
                    segment_txt = output.with_name(f"{output.stem}.fa-{index:04d}.txt")
                    with wave.open(str(segment_wav), "wb") as target:
                        target.setnchannels(channels); target.setsampwidth(sample_width); target.setframerate(sample_rate); target.writeframes(frames)
                    segment_txt.write_text(" ".join(char["text"] for char in selected), encoding="utf-8")
                    try:
                        result_segment = aligner.generate(
                            input=(str(segment_wav), str(segment_txt)), data_type=("sound", "text"))
                        result_item = result_segment[0] if result_segment else {}
                        candidate = list(result_item.get("timestamp") or [])
                        if len(candidate) >= max(1, int(len(selected) * 0.80)) and candidate:
                            # Anchor this VAD segment to the first native char;
                            # fa-zh's relative offset is removed here.
                            first_rel = float(candidate[0][0]) / 1000.0
                            anchor = selected[0]["start"]
                            for pair in candidate[:len(selected)]:
                                if len(pair) >= 2:
                                    aligned_timestamps.append([
                                        round((anchor + float(pair[0]) / 1000.0 - first_rel) * 1000),
                                        round((anchor + float(pair[1]) / 1000.0 - first_rel) * 1000),
                                    ])
                    finally:
                        segment_wav.unlink(missing_ok=True); segment_txt.unlink(missing_ok=True)
            del aligner
            gc.collect()
            if len(aligned_timestamps) >= max(1, int(len(native_chars) * 0.90)):
                timestamps = aligned_timestamps
                alignment_mode = "fa_zh_vad_corrected"
            else:
                alignment_mode = "paraformer_char_fallback"
        punctuated_text = raw_text
        chars = [char for char in raw_text if not char.isspace() and (alignment_mode != "fa_zh_vad_corrected" or char not in ALIGN_SKIP)]
        count = min(len(chars), len(timestamps))
        timed_chars = [
            {"text": chars[index], "start": round(float(timestamps[index][0]) / 1000, 3),
             "end": round(float(timestamps[index][1]) / 1000, 3)}
            for index in range(count)
            if len(timestamps[index]) >= 2
        ]
        text = "".join(char["text"] for char in timed_chars)
        subtitle_text = punctuated_text if punctuation_marks(punctuated_text, text) else text
        end = timed_chars[-1]["end"] if timed_chars else duration
        alignment_delta = native_end - end if native_end and end else 0.0
        alignment_within_tolerance = alignment_mode in ("fa_zh", "fa_zh_anchor_corrected", "fa_zh_vad_corrected", "paraformer_char") and bool(timed_chars)
        subtitles = subtitles_from_timed_chars(
            timed_chars, subtitle_text, 0.0, max(duration, end),
            limit=subtitle_text_limit(subtitle_text), timestamp_source=alignment_mode,
        )
        speech_segments = [{
            "start": 0.0, "end": round(duration, 3), "text": text,
            "engine": "paraformer_zh", "has_token_timestamps": bool(timed_chars),
            "language": "zh", "model_language": "zh",
        }]
        quality = {
            "status": "ok" if (alignment_within_tolerance or alignment_mode == "paraformer_char_fallback") and len(timed_chars) >= max(1, int(len(text) * 0.98)) else "needs_review",
            "timestamp_mode": alignment_mode,
            "vad_segments": 1,
            "recognized_segments": 1 if timed_chars else 0,
            "sensevoice_retries": 0,
            "fallback_segments": 0,
            "speech_seconds": round(duration, 3),
            "recognized_speech_seconds": round(end, 3) if timed_chars else 0.0,
            "uncovered_speech_seconds": round(max(0.0, duration - end), 3) if timed_chars else round(duration, 3),
            "coverage_ratio": round(min(1.0, end / duration), 4) if duration else 0.0,
            "native_timestamp_end": round(native_end, 3),
            "aligned_timestamp_end": round(end, 3) if timed_chars else 0.0,
            "alignment_delta_seconds": round(alignment_delta, 3),
            "issues": ([{"reason": "fa-zh边界差异较大，已自动采用Paraformer原生时间戳"}] if alignment_mode == "paraformer_char_fallback"
                       else [] if alignment_within_tolerance and len(timed_chars) >= max(1, int(len(text) * 0.98))
                       else [{"reason": "强制对齐边界与Paraformer原始时间戳差异较大，请回听时间轴"}]),
        }
        payload = {
            "engine": "FunASR Paraformer-zh + fa-zh强制对齐（异常回退原生时间戳） + FSMN-VAD + CT-Punc",
            "video": str(video), "duration": round(duration, 3), "text": subtitle_text,
            "subtitles": subtitles, "speech_segments": speech_segments,
            "timed_tokens": timed_chars, "quality": quality,
            "product_name": product_name_from_filename(video),
        }
        write_json(output, payload)
    finally:
        wav.unlink(missing_ok=True)
        text_file.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
