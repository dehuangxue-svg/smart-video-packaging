<div align="center">

# Smart Video Packaging

**A local desktop workflow inspired by Jianying / CapCut intelligent video finishing.**

Turn speech into editable subtitles, highlight important words, and place sound effects — then refine everything on a timeline.

[English](README.en.md) · [中文](README.md) · [Recognition requirements](docs/recognition.md#english) · [MIT License](LICENSE)

![Workflow illustration](docs/workflow.svg)

</div>

Smart Video Packaging is a **Windows desktop video tool that processes media locally**, designed for product demonstrations, livestream clips, talking-head videos, and tutorials. Local models transcribe speech and analyze the text; a content-aware rule system recommends sound effects. You can correct captions, trim clips, adjust styling and audio levels, and export a finished video.

**After dependencies and models have been downloaded, transcription, text analysis, preview, and export run on your computer. No cloud ASR / LLM API key is required.** Media, projects, inference caches, and correction snapshots stay local.

This is an independent open-source implementation, unaffiliated with Jianying / CapCut or their owners. It does not include their proprietary models, templates, or sound libraries. “Smart packaging” here means automated subtitles, keyword highlighting, and sound-effect placement.

## Features

| Feature | Current implementation |
| --- | --- |
| Local speech recognition | SenseVoice INT8 with VAD, local retries, and faster-whisper base INT8 for weak speech regions |
| Captions and highlights | Product-name hints from the filename; Qwen3.5-0.8B analyzes text while retaining caption timing |
| Sound effects | 29 bundled CC0 effects with preview, drag-to-place, adjustable duration, and per-clip volume |
| Timeline | V1 video, T1 captions, A1 effects; right-click deletion for captions and effects |
| Basic editing | Split, trim, and ripple-delete within one source video; linked caption/effect timing with undo/redo |
| Manual refinement | Installed fonts, size, colors, caption position, text, timing, and highlighted words |
| Batch analysis | Sequential folder processing, saved projects, and pass / review / failure summaries; review and export each project |
| Video export | FFmpeg H.264 / AAC output with original audio and mixed sound effects |
| Bilingual UI | Chinese / English interface, independent of the source speech language |

Master effect volume defaults to **50%**; individual effects support **0–200%**. Default targets are 10 effects for 60–75 seconds, 12 for over 75–100 seconds, and 14 for over 100–120 seconds. Longer videos use a target of 7 effects per minute, rounded up; a 30-minute video therefore targets 210 effects. Shorter clips target one per 6 seconds. Fewer are used when suitable positions are unavailable.

## Workflow

1. Load a video and choose its speech language, or use automatic detection.
2. Optionally split, trim, or delete sections on V1.
3. Run **Auto package** to generate captions, keyword highlights, and effect suggestions. Folder-based batch analysis is also available.
4. Review flagged speech regions and refine names, caption boundaries, typography, and effect levels.
5. Save the project and export the video.

**Recognition input:** use an audible speech track, preferably one clear speaker without overpowering music or overlapping voices. Put product / brand names in the filename when relevant. Recognition uses the audio track; on-screen text OCR and translation are outside the current workflow. See the [recognition and model guide](docs/recognition.md#english).

## Install and run

This is a source release with a buildable desktop executable. Keep the entire project on a drive with sufficient free space.

| Component | Requirement |
| --- | --- |
| OS | Windows 10 / 11 x64 |
| Python | Python 3.12 x64 recommended; dependency range 3.10–3.12. Enable Add to PATH during setup |
| Video tools | [FFmpeg and ffprobe](https://ffmpeg.org/download.html) on PATH; libx264, AAC and ASS / libass support |
| Desktop runtime | .NET Framework 4.8 and [Microsoft WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/) |
| RAM | 8GB+ recommended. Sequential CPU inference targets lower-memory devices; 4GB may be usable with a system paging file, but a strict 4GB stress test has not been completed |
| GPU | No dedicated GPU required; the downloaded llama.cpp CPU build must support your processor's instruction set |
| Storage | About 1GB of models, plus dependencies and runtimes. Allow at least 5GB for setup, with additional space for long-video caches and exports |
| Network | Required for initial dependency/model/runtime downloads; the configured processing pipeline uses local models afterward |

```powershell
git clone https://github.com/dehuangxue-svg/smart-video-packaging.git
cd smart-video-packaging
```

1. Install Python, FFmpeg, .NET Framework, and WebView2 as listed above.
2. Run `安装运行环境.bat` (install dependencies), then `下载轻量模型.bat` (download models). The model script uses Windows `winget` to obtain llama.cpp; alternatively place a compatible build from the [official releases](https://github.com/ggml-org/llama.cpp/releases) in `runtime/llama`.
3. Run `构建桌面软件.bat` (build desktop app). It generates `剪辑智能包装.exe` and a desktop shortcut.
4. Launch the shortcut. The executable requires the rest of the project directory.

Equivalent PowerShell commands:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/install.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/download_models.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/build.ps1
.\.venv\Scripts\python.exe scripts/doctor.py
```

For browser mode, run `.\.venv\Scripts\python.exe app.py` and open `http://127.0.0.1:8765/`. The desktop application starts or reuses the service for the same project directory. Closing its window keeps the shared local service and background jobs running. Port 8765 is currently fixed; run one service at a time.

## Local files and configuration

Defaults use paths relative to the project directory. Override them in your local `config.json`; omitted values come from `config.example.json`.

| Folder | Purpose |
| --- | --- |
| `videos/` | Convenient input location; videos elsewhere can also be loaded |
| `outputs/` | Finished videos; change `exports_dir` to use another drive |
| `data/projects/` | Saved editing projects |
| `data/cache/` | Inference caches |
| `data/training/snapshots/` | Model output and human corrections recorded when saving, for building your own future training dataset |
| `data/desktop-webview/` | Desktop cache and interface preferences |
| `data/logs/` | Startup and error logs |

Private data folders, models, runtime files, and `config.json` are excluded from Git. Training snapshots are never uploaded automatically.

## Current limitations

- This is a lightweight subtitle and sound-effect finishing tool. It edits multiple sections of one source video; multi-source composition, transition templates, keyframes, and Jianying / CapCut project import/export are not implemented.
- Existing product/B-roll footage in the source video is retained. Automatic highlight-library matching and insertion of B-roll or image overlays are not connected to this open-source editing workflow yet.
- Mandarin and English have sample-based validation. Cantonese, Japanese, and Korean are exposed as model language options and need more testing.
- Native token timestamps, speech coverage checks, and retries reduce timing errors, but cannot guarantee perfect words or boundaries. Coverage is not transcription accuracy. Captions crossing cuts are marked for review.
- Longer videos use batched text analysis, stage caches, and streamed sound mixing. The 30-minute effect target describes the scheduling rule, not comprehensive long-video or low-memory stress-test coverage.

## Development and licensing

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
node tests/test_edit_core.js
node tests/test_desktop_bridge.js
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/build.ps1
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for architecture and contribution guidelines. Original code uses the [MIT License](LICENSE). Sound assets, model weights, FFmpeg, fonts, and WebView2 retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Model weights and commercial fonts are not bundled in this repository.
