# 识别要求与模型 / Recognition requirements and models

[中文产品介绍](../README.md) · [English overview](../README.en.md)

## 中文

### 输入与语言

- 输入为含有可听清人声音轨的视频。FFmpeg 在本地提取并重采样为 16kHz 单声道，用户无需提前转换音频。
- 建议以一个说话人为主，避免多人同时讲话；强混响、过响的音乐、爆音、口音和不清晰的收尾都可能增加错词与边界误差。
- 原声可选自动识别、普通话、英语、粤语、日语、韩语。当前验证集中在普通话与英语，其他语言仍需实测。
- 品牌和产品提示来自视频文件名，建议使用可辨识的名称；这只是纠错线索，不保证每个专有名词正确。
- 界面语言与原声语言分开选择。切换 English 界面不会把中文字幕翻译成英语。当前识别流程不做 OCR、说话人分离或自动翻译。

### 本地处理链路

| 阶段 | 模型 / 工具 | 用途 |
| --- | --- | --- |
| 音频提取 | FFmpeg | 提取原声，统一采样率 |
| 语音活动检测 | Silero VAD / sherpa-onnx | 找出语音区间，并在边缘留出余量 |
| 主识别 | SenseVoice Small INT8 / sherpa-onnx | 文字、原生词元起始时间戳；在词元间隔内细分字符边界 |
| 补识别 | faster-whisper base INT8 | 主模型重试后仍薄弱的局部区间，提供单词时间戳 |
| 中文标点 | CT-Transformer INT8 | 中文断句辅助；英文跳过此阶段 |
| 文案分析 | Qwen3.5-0.8B Q4_K_M / llama.cpp | 产品名称提示、文案分析、类别与高亮词；每批 18 条字幕，保留原时间戳 |
| 音效推荐 | 分析结果 + 本地规则 | 根据内容和时长，从 29 种 CC0 音效中安排位置 |
| 辅助画面分析 | OpenCV YuNet + 简单图像规则 | 抽帧估计主播可见性；不能可靠理解文字板内容 |
| 导出 | FFmpeg | 压制字幕并混合原声与音效 |

SenseVoice 的词元时间戳与由词元推导的字符结束边界有精度限制，不能等同于人工逐字强制对齐。低覆盖语音会局部补识别；未可靠对齐或跨越剪辑点的字幕需要回听。

### 字幕与批量质检

- 中文使用较短字幕；英文按完整单词断句，目标约 42 个字符，保留空格、缩写和小数。
- 文案模型不重新估算时间。识别结果按源文件、剪辑范围、语言和管线版本缓存。
- 语音覆盖率表示多少检测到的语音区间获得了文字时间信息，不是字词准确率。显示“通过”仍应抽检品牌、数字和收尾。
- 批量模式顺序处理文件，避免多模型同时常驻。批次报告和工程可留待逐个复核、导出。
- 保存时会生成模型输出与人工修订对照快照。正负样本仍需要按实际保留、修改和删除情况进一步整理；系统不会自动训练或上传。

### 资源预算

当前选用的模型文件合计约 1.0GB：SenseVoice 约 237MB、Whisper base 约 145MB、中文标点约 76MB、Qwen GGUF 约 580MB，另有很小的 VAD 与人脸模型。文件体积不是运行内存占用。模型按阶段运行，主 ASR 释放后才加载备用 ASR；默认最多 2 个 CPU 线程。4GB 是低内存适配目标，尚未以真实 4GB 硬限制验证所有视频时长。

## English

### Input and language

- Supply a video with an intelligible speech track. FFmpeg locally extracts and resamples audio to 16kHz mono; manual audio conversion is unnecessary.
- Prefer one main speaker and limited overlapping speech. Loud music, reverberation, clipping, strong accents, and unclear phrase endings can increase word and boundary errors.
- Source-language options: automatic, Mandarin, English, Cantonese, Japanese, and Korean. Validation so far focuses on Mandarin and English.
- Product and brand hints come from the video filename. Clear naming helps correction but does not guarantee proper-noun accuracy.
- UI language and speech language are independent. Selecting the English interface does not translate captions. OCR, speaker diarization, and translation are outside this pipeline.

### Local pipeline

1. **FFmpeg** extracts and resamples the original audio.
2. **Silero VAD with sherpa-onnx** identifies speech regions, retaining boundary padding.
3. **SenseVoice Small INT8** produces text and native token start timestamps. Character intervals are derived within token intervals.
4. Weak regions are retried; **faster-whisper base INT8** handles remaining local gaps with word timestamps after the main recognizer is released.
5. **CT-Transformer INT8** assists Chinese punctuation; English bypasses it.
6. **Qwen3.5-0.8B Q4_K_M via llama.cpp** analyzes text and highlights in batches of 18 captions, retaining input timestamps.
7. **Local rules** use text analysis and duration to place effects from the 29-item CC0 library.
8. **OpenCV YuNet and simple image heuristics** provide sampled face-visibility hints; this is not reliable semantic understanding of printed boards.
9. **FFmpeg** burns in captions and mixes effects with the source audio.

Native token start times and inferred character endings are not equivalent to manually verified forced alignment. Unreliable coverage and captions crossing a cut require listening review.

### Quality and batch processing

Chinese captions use short phrases. English preserves complete words, spaces, contractions, and decimals, with a target length of approximately 42 characters. Text analysis does not recompute timestamps. Caches distinguish the source file, clip ranges, speech language, and pipeline version.

Speech coverage measures how much detected speech received text and timing information; it is not word accuracy. Even a passing result should be sampled for names, numbers, and sentence endings. Batch jobs process files sequentially and save projects for individual review/export.

Saving records model output and human corrections locally. These are raw comparison snapshots for future dataset curation, not automatically trained positive/negative datasets.

### Resource budget

Selected model files total approximately 1.0GB: SenseVoice 237MB, Whisper base 145MB, punctuation 76MB, Qwen GGUF 580MB, plus small VAD and face models. File size is not peak RAM usage. Workers run in stages, the main recognizer is released before fallback ASR, and the default CPU thread limit is two. Low-memory operation is a design target; comprehensive testing under a strict 4GB memory limit remains outstanding.
