from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import english_caption_signals, read_json, split_subtitle, write_json


BENEFITS = "改善 缓解 控油 蓬松 留香 清洁 补水 保湿 提亮 显瘦 舒服 舒适 方便 好吃 真好吃 酥 香 不油 防滑 支撑 去污 除菌 抑菌 柔顺 除臭 祛味 修护 透亮 清爽 持久 味道 口感 软糯 爆浆".split()
SELLING = "专利 设计 成分 材质 工艺 容量 套装 独立 认证 低糖 添加 五腔 双效 进口 菌株 配方 结构 香水油 黑芝麻 配料表 用料 真材实料".split()
REMOVE = "宝宝们 谁呀 是谁 在不在 来了吗 点关注 上链接 拍一号 库存 倒计时 抢到 付款 客服 公屏 刷起来 直降 到手价 一二三 上车 单买 多少钱".split()
GENERIC_PRODUCT_ENDINGS = {"组合", "套装", "系列", "产品", "精剪", "素材"}


def filename_correct_text(text: str, product_name: str) -> tuple[str, list[dict[str, str]]]:
    """Correct one-character ASR errors only when the replacement comes from the filename."""
    product = re.sub(r"[^\u4e00-\u9fff]", "", product_name)
    changes: list[dict[str, str]] = []
    if len(product) < 3:
        return text, changes
    try:
        from pypinyin import lazy_pinyin
    except ImportError:
        lazy_pinyin = lambda value: list(value)
    replacements: list[tuple[int, int, str, str]] = []
    occupied: set[int] = set()
    for width in range(min(6, len(product)), 2, -1):
        candidates = {product[i:i + width] for i in range(len(product) - width + 1)}
        candidates = {x for x in candidates if x not in GENERIC_PRODUCT_ENDINGS}
        for position in range(0, len(text) - width + 1):
            if any(i in occupied for i in range(position, position + width)):
                continue
            source = text[position:position + width]
            for target in candidates:
                if re.fullmatch(r"[\u4e00-\u9fff]+", source):
                    diff_positions = [i for i, (a, b) in enumerate(zip(source, target)) if a != b]
                    if len(diff_positions) != 1:
                        continue
                    diff = diff_positions[0]
                    brand_match = target == product[:3]
                    source_py = lazy_pinyin(source[diff])[0]
                    target_py = lazy_pinyin(target[diff])[0]
                    phonetic = SequenceMatcher(None, source_py, target_py).ratio() >= 0.48 or source_py[:1] == target_py[:1]
                    if brand_match or phonetic:
                        replacements.append((position, position + width, source, target))
                        occupied.update(range(position, position + width))
                        break
    current = text
    for start, end, source, target in sorted(replacements, reverse=True):
        current = current[:start] + target + current[end:]
        changes.append({"from": source, "to": target, "source": "video_filename"})
    return current, changes


def classify(text: str) -> tuple[str, float, list[str], str]:
    english = english_caption_signals(text)
    benefit = [w for w in BENEFITS if w in text] + english["benefit"]
    selling = [w for w in SELLING if w in text] + english["selling_point"]
    remove = [w for w in REMOVE if w in text] + english["remove"]
    if remove and not benefit and not selling:
        return "remove", min(0.96, 0.78 + 0.02 * len(remove)), remove[:4], "交易催促或低信息直播话术"
    if benefit:
        return "benefit", min(0.96, 0.72 + 0.04 * len(benefit)), (benefit + selling)[:4], "包含明确功效、口感或使用结果"
    if selling:
        return "selling_point", min(0.94, 0.68 + 0.04 * len(selling)), selling[:4], "包含产品成分、结构或用料卖点"
    return "other", 0.42, [], "普通产品信息"


def rule_analyze(data: dict) -> dict:
    rows = []
    corrections = []
    for index, sub in enumerate(data.get("subtitles", [])):
        corrected, changes = filename_correct_text(str(sub.get("text", "")), str(data.get("product_name", "")))
        label, score, words, reason = classify(corrected)
        row = dict(sub)
        row.update({"id": index, "text": corrected, "label": label, "score": score, "highlight_words": words, "reason": reason})
        rows.append(row)
        corrections.extend(changes)
    return {"engine": "文件名纠错 + 轻量规则回退", "subtitles": rows, "filename_corrections": corrections}


def dynamic_schema(count: int) -> dict:
    item = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "id": {"type": "integer", "minimum": 0, "maximum": max(0, count - 1)},
            "text": {"type": "string"},
            "label": {"type": "string", "enum": ["benefit", "selling_point", "remove", "other"]},
            "score": {"type": "number", "minimum": 0, "maximum": 1},
            "highlight_words": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
            "reason": {"type": "string"},
        },
        "required": ["id", "text", "label", "score", "highlight_words", "reason"],
    }
    return {
        "type": "object", "additionalProperties": False,
        "properties": {"items": {"type": "array", "minItems": count, "maxItems": count, "items": item}},
        "required": ["items"],
    }


def extract_json(text: str):
    decoder = json.JSONDecoder()
    candidates = []
    for start, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            value, length = decoder.raw_decode(text[start:])
            if isinstance(value, (list, dict)):
                candidates.append((length, value))
        except json.JSONDecodeError:
            pass
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def model_analyze(data: dict, llama: Path, model: Path, threads: int, output: Path) -> dict:
    # Work on timestamped subtitle pieces rather than broad VAD segments. Text
    # correction and classification must never recalculate the audio alignment.
    segments = data.get("subtitles") or data.get("speech_segments", [])
    product = str(data.get("product_name", ""))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    mapping: dict[int, dict] = {}
    batch_size = 18
    batch_count = 0
    for batch_start in range(0, len(segments), batch_size):
        compact = [
            {"id": index, "text": str(segments[index].get("text", ""))}
            for index in range(batch_start, min(len(segments), batch_start + batch_size))
        ]
        ids = [item["id"] for item in compact]
        prompt = f"""任务：校正并分类直播商品口播字幕。当前视频文件名给出的商品是“{product}”。
必须返回{len(compact)}项，id必须依次为{ids}，不得合并、拆分或遗漏。
text必须是对应输入原话的校正版，保留原意、数字和语气；不准写“原句”“同上”等占位词，不准新增功效。
保持每条字幕的原文语言，禁止翻译；英文必须保留单词间空格及大小写，不要把不同单词拼接。
字幕时间已经锁定，因此只能修改每一项自己的text，不能把文字移到相邻id。
当品牌或商品词明显是同音错字时，只能依据文件名纠正。与该商品无关的食物名不得硬改。
分类：benefit=明确功效、口感或使用结果；selling_point=成分、结构、设计、用料或规格卖点；remove=称呼、价格催单、倒数、无意义互动；other=其他有用内容。
highlight_words只能逐字复制校正后text中真实出现的1到4个短词，没有则空数组。
只输出JSON，不解释。
输入：{json.dumps(compact, ensure_ascii=False)}"""
        cmd = [
            str(llama), "-m", str(model), "-p", prompt, "-n", "1600", "-c", "3072",
            "-t", str(max(1, min(threads, 2))), "--temp", "0.05", "--top-p", "0.8",
            "--no-display-prompt", "--simple-io", "-ngl", "0", "--reasoning", "off",
            "--reasoning-budget", "0", "-st",
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=flags, timeout=900,
        )
        output.with_name(f"{output.stem}.batch{batch_count + 1}.llm.txt").write_text(
            proc.stdout, encoding="utf-8", errors="replace",
        )
        if proc.returncode:
            raise RuntimeError((proc.stderr or proc.stdout)[-2000:])
        parsed = extract_json(proc.stdout)
        if not parsed:
            raise RuntimeError(f"0.8B模型第{batch_count + 1}批没有返回可解析的JSON")
        items = parsed if isinstance(parsed, list) else parsed.get("items", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = int(item.get("id", -1))
            if item_id in ids:
                mapping[item_id] = item
        batch_count += 1
    if not mapping:
        raise RuntimeError("0.8B模型没有返回任何有效条目")
    rows = []
    corrections = []
    for index, source in enumerate(segments):
        item = mapping.get(index, {"text": source.get("text", ""), "label": "other", "score": 0.42, "highlight_words": [], "reason": "模型缺项，已使用规则判断"})
        original = str(source.get("text", ""))
        model_text = str(item.get("text", "")).strip()
        if not model_text or model_text in ("原句", "同上") or len(model_text) < max(2, len(original) * 0.55):
            model_text = original
        if re.search(r"[A-Za-z]{3}", original) and not re.search(r"[\u3400-\u9fff]", original):
            # Reject translations or destructive rewrites of English ASR output.
            if (re.search(r"[\u3400-\u9fff]", model_text)
                    or SequenceMatcher(None, original.casefold(), model_text.casefold()).ratio() < 0.65):
                model_text = original
        corrected, changes = filename_correct_text(model_text, product)
        corrections.extend(changes)
        rule_label, rule_score, rule_words, rule_reason = classify(corrected)
        label = str(item.get("label", "other"))
        words = [str(x) for x in item.get("highlight_words", []) if str(x) and str(x) in corrected][:4]
        if rule_label in ("benefit", "selling_point", "remove"):
            label = rule_label
            words = list(dict.fromkeys(rule_words + words))[:4]
            score = max(rule_score, float(item.get("score", 0.5)))
            reason = rule_reason
        else:
            if label == "benefit" and not re.search(r"[A-Za-z]", corrected) and not any(w in corrected for w in BENEFITS):
                label = "other"
            score = float(item.get("score", 0.5))
            reason = str(item.get("reason", ""))[:80]
        piece = dict(source)
        piece_label, piece_score, piece_words, piece_reason = classify(corrected)
        final_label = piece_label if piece_label in ("benefit", "selling_point", "remove") else label
        if final_label not in ("benefit", "selling_point", "remove", "other"):
            final_label = "other"
        piece.update({
            "text": corrected, "label": final_label,
            "score": round(max(piece_score, score if final_label == label else 0), 2),
            "highlight_words": list(dict.fromkeys(piece_words + [w for w in words if w in corrected]))[:4],
            "reason": piece_reason if piece_label != "other" else reason,
            "selected": True, "timestamp_locked": True,
        })
        rows.append(piece)
    for i, row in enumerate(rows):
        row["id"] = i
    return {
        "engine": "Qwen3.5-0.8B Q4 + 文件名硬纠错 + 时间戳锁定",
        "model_items": len(mapping), "batches": batch_count, "timestamp_locked": True,
        "subtitles": rows, "filename_corrections": corrections,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--llama", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    input_path, output_path = Path(args.input), Path(args.output)
    data = read_json(input_path, {})
    result = None
    warning = ""
    llama, model = Path(args.llama), Path(args.model)
    if llama.is_file() and model.is_file():
        try:
            result = model_analyze(data, llama, model, args.threads, output_path)
        except Exception as exc:
            warning = f"0.8B模型调用失败，已使用规则回退：{exc}"
    if result is None:
        result = rule_analyze(data)
    result["warning"] = warning
    result["product_name"] = data.get("product_name", "")
    write_json(output_path, result)


if __name__ == "__main__":
    main()
