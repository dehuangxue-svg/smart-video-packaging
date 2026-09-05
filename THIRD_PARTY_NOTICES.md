# Third-party notices / 第三方资源说明

The repository's MIT license covers its original code and documentation. It does not replace licenses for dependencies, model weights, sound assets, fonts, or runtimes. 本仓库 MIT 许可适用于原创代码和文档，第三方组件仍遵循各自许可。

## Bundled sound effects / 内置音效

`assets/sfx/` contains 29 edited/converted WAV effects. Their source mapping is in [manifest.json](assets/sfx/manifest.json). The selected source recordings are CC0; the upstream source pages and bundled source-license notices are authoritative.

| Source | Source page / bundled notice |
| --- | --- |
| Kenney Interface Sounds | [Source](https://kenney.nl/assets/interface-sounds) · [Notice](assets/licenses/interface-sounds.txt) |
| Kenney Impact Sounds | [Source](https://kenney.nl/assets/impact-sounds) · [Notice](assets/licenses/impact-sounds.txt) |
| Kenney Digital Audio | [Source](https://kenney.nl/assets/digital-audio) · [Notice](assets/licenses/digital-audio.txt) |
| Kenney Casino Audio | [Source](https://kenney.nl/assets/casino-audio) · [Notice](assets/licenses/casino-audio.txt) |
| Camera Shutter — roachpowder | [CC0 source](https://freesound.org/people/roachpowder/sounds/170229/) |
| Cash Register — modusmogulus | [CC0 source](https://freesound.org/people/modusmogulus/sounds/794903/) |
| Small applause — Breviceps | [CC0 source](https://freesound.org/people/Breviceps/sounds/462362/) |
| Heartbeat — JonasTisell | [CC0 source](https://freesound.org/people/JonasTisell/sounds/670465/) |
| Cartoon Boing.wav — reelworldstudio | [CC0 source](https://freesound.org/people/reelworldstudio/sounds/161122/) |

Additional Freesound source identifiers and editing provenance are preserved in [freesound-sources.json](assets/licenses/freesound-sources.json). CC0 terms: [Creative Commons CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).

## Downloaded models and tools / 另行下载的模型和工具

Weights and executables listed here are **not committed to this repository**. The installation scripts fetch them from upstream sources.

| Component | Role | Upstream licensing reference |
| --- | --- | --- |
| SenseVoice Small / FunAudioLLM | Primary ASR model, converted to INT8 ONNX | [Model card and model license](https://huggingface.co/FunAudioLLM/SenseVoiceSmall); retain the model name and attribution. Its model terms are separate from this project's MIT license |
| sherpa-onnx | Local inference and converted models | [Project](https://github.com/k2-fsa/sherpa-onnx), Apache-2.0 for code; individual models retain their model terms |
| Silero VAD | Speech activity detection | [Project and MIT license](https://github.com/snakers4/silero-vad) |
| CT-Transformer / FunASR | Punctuation model | [FunASR](https://github.com/modelscope/FunASR); consult its model license independently of code licensing |
| faster-whisper / Whisper base | Fallback ASR | [faster-whisper MIT license](https://github.com/SYSTRAN/faster-whisper/blob/master/LICENSE) · [converted model card](https://huggingface.co/Systran/faster-whisper-base) |
| Qwen3.5-0.8B | Local text analysis | [Original model, Apache-2.0](https://huggingface.co/Qwen/Qwen3.5-0.8B) · [GGUF quantization source](https://huggingface.co/bartowski/Qwen_Qwen3.5-0.8B-GGUF) |
| llama.cpp | GGUF CPU inference | [Project and MIT license](https://github.com/ggml-org/llama.cpp) |
| OpenCV / YuNet | Sampled face detection | [OpenCV Zoo model and license](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet) |
| FFmpeg | Decoding, encoding and mixing | [Legal and build-license information](https://ffmpeg.org/legal.html); license depends on the selected build |
| Microsoft WebView2 | Windows desktop web runtime | [SDK package](https://www.nuget.org/packages/Microsoft.Web.WebView2/1.0.4191.47) · [Runtime distribution](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution) |

`desktop/build.ps1` copies the SDK's LICENSE and NOTICE alongside its DLLs when building locally. Python dependencies are installed by pip and retain the license files supplied in their distributions. Font choices refer to fonts already installed on the user's computer; no font binaries are bundled.

## Product references / 产品参考

Jianying / CapCut is referenced to describe the intelligent finishing workflow. This project uses its own code and the documented assets above. It is not an official client, and has no affiliation with Jianying / CapCut or its owners. Timeline interaction also took inspiration from [OpenCut](https://github.com/OpenCut-app/OpenCut) and [Shotcut's documented keyboard shortcuts](https://shotcut.org/howtos/keyboard-shortcuts/); their source code is not included.
