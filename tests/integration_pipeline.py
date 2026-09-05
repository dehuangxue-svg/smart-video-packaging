from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app


def new_job(video: Path) -> tuple[dict, float]:
    job_id = uuid.uuid4().hex
    app.JOBS[job_id] = {
        "id": job_id, "kind": "integration", "video": str(video), "status": "running",
        "stage": "test", "message": "test", "progress": 0, "created_at": time.time(),
    }
    started = time.perf_counter()
    app.run_auto_job(job_id, video)
    return app.JOBS[job_id], time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the timestamped ASR pipeline twice and verify cache reuse.")
    parser.add_argument("--video", required=True)
    args = parser.parse_args()
    video = Path(args.video)
    if not video.is_file():
        raise FileNotFoundError(video)

    test_root = ROOT / "data" / "integration_test"
    app.PROJECTS = test_root / "projects"
    app.JOBS_DIR = test_root / "jobs"
    app.CACHE = test_root / "cache"
    app.PIPELINE_VERSION += "-integration"
    for directory in (app.PROJECTS, app.JOBS_DIR, app.CACHE):
        directory.mkdir(parents=True, exist_ok=True)

    first, first_seconds = new_job(video)
    assert first["status"] == "done", first
    project = first["result"]
    quality = project["asr_quality"]
    assert quality["timestamp_mode"] == "token", quality
    assert quality["coverage_ratio"] >= 0.985, quality
    assert all(row.get("timestamp_locked") for row in project["subtitles"])

    second, second_seconds = new_job(video)
    assert second["status"] == "done", second
    assert second_seconds < first_seconds, (first_seconds, second_seconds)
    print({
        "first_seconds": round(first_seconds, 2), "cached_seconds": round(second_seconds, 2),
        "subtitles": len(project["subtitles"]), "coverage": quality["coverage_ratio"],
        "quality": quality["status"], "timestamp_mode": quality["timestamp_mode"],
    })


if __name__ == "__main__":
    main()
