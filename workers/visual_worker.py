from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import write_json


def board_score(cv2, frame) -> float:
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 70, 170)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    image_area = height * width
    best = 0.0
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.035 * perimeter, True)
        area = cv2.contourArea(approx)
        if len(approx) != 4 or not image_area * 0.035 <= area <= image_area * 0.55:
            continue
        x, y, w, h = cv2.boundingRect(approx)
        ratio = w / max(h, 1)
        if not 0.55 <= ratio <= 3.2 or y > height * 0.86:
            continue
        roi = edges[y:y + h, x:x + w]
        density = float((roi > 0).mean()) if roi.size else 0.0
        position = 1.0 if y + h / 2 > height * 0.25 else 0.7
        best = max(best, min(1.0, density * 7.0) * position)
    return round(best, 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--face-model", required=True)
    args = parser.parse_args()
    import cv2

    video = Path(args.video)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError("OpenCV无法打开视频")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    duration = frames / fps if frames else 0
    face_model = Path(args.face_model)
    if not face_model.is_file():
        raise FileNotFoundError(f"缺少人脸检测模型：{face_model}")
    detector = cv2.FaceDetectorYN.create(str(face_model), "", (320, 320), 0.65, 0.3, 5000)
    samples = []
    t = 0.5
    while t < duration:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            t += args.interval
            continue
        height, width = frame.shape[:2]
        scale = 480 / max(width, 1)
        small = cv2.resize(frame, (480, max(1, int(height * scale))))
        detector.setInputSize((small.shape[1], small.shape[0]))
        _, faces = detector.detect(small)
        face_count = 0 if faces is None else len(faces)
        risk = board_score(cv2, small)
        samples.append({
            "time": round(t, 2), "host_visible": face_count > 0,
            "face_count": face_count, "board_risk": risk,
            "overlay_allowed": risk < 0.48,
        })
        t += args.interval
    cap.release()
    write_json(Path(args.output), {
        "engine": "OpenCV轻量抽帧检测",
        "interval": args.interval,
        "samples": samples,
        "warning": "文字板为轻量视觉预警，最终必须在编辑器内人工确认",
    })


if __name__ == "__main__":
    main()
