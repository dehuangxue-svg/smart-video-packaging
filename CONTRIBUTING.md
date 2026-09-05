# Contributing / 参与开发

欢迎中文或英文 Issue / PR。请说明问题的触发方式、预期结果与实际结果，优先附可以公开的最小复现素材。

Issues and pull requests in Chinese or English are welcome. Describe the trigger, expected behavior, and observed result. Use a minimal sample that you have permission to share.

## Architecture / 代码结构

- `app.py`: loopback FastAPI service, project persistence, worker scheduling and export.
- `core.py`, `editing.py`: portable configuration, caption rules, sound placement and source-to-timeline mapping.
- `workers/`: separate CPU ASR, text-analysis and visual-analysis processes.
- `static/`: editor interface, localization, timeline operations and desktop integration.
- `desktop/`: WinForms / WebView2 host and reproducible build entry point.
- `assets/sfx/`, `assets/licenses/`: bundled CC0 effects and source records.
- `tests/`: timing, edits, English handling, audio mixing and desktop save-state tests.

## Checks / 验证

With dependencies installed and FFmpeg on PATH:

```powershell
python -m unittest discover -s tests -q
node tests/test_edit_core.js
node tests/test_desktop_bridge.js
powershell -NoProfile -ExecutionPolicy Bypass -File desktop/build.ps1
```

The source tests do not require downloading model weights. A model-backed integration check can be run with `python tests/integration_pipeline.py --video path/to/sample.mp4` after model setup. Use a speech sample appropriate for evaluating coverage; synthetic silence is not an ASR quality test.

Keep video, captions, model weights, logs, credentials, machine-specific configuration, and training snapshots out of commits. Timing changes should verify both preview and exported media, including linked captions and effects. Language changes should preserve source text and keep the UI language independent of ASR.

不要加入只做视觉占位的按钮。新增操作必须有实际行为、可保存的工程状态以及明确的导出行为。4GB / 长视频性能声明需要提供可复现测试条件。

Avoid decorative controls with no implementation. New editing actions need real behavior, persistent project state, and defined export behavior. Claims about 4GB operation or long-video performance need reproducible measurement conditions.
