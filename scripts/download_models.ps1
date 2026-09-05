$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Models = Join-Path $Root "models"
$Cache = Join-Path $Root "data\downloads"
$Runtime = Join-Path $Root "runtime"
$env:HF_HOME = Join-Path $Root 'data\cache\huggingface'
$env:TEMP = Join-Path $Root 'data\temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $Models,$Cache,$Runtime | Out-Null
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null

function Download-File([string]$Url, [string]$Output, [long]$MinBytes = 1024) {
    if ((Test-Path -LiteralPath $Output) -and ((Get-Item -LiteralPath $Output).Length -ge $MinBytes)) {
        Write-Host "Already exists: $Output"
        return
    }
    Write-Host "Downloading: $Url"
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }
    & $Python (Join-Path $PSScriptRoot "download_file.py") $Url $Output --min-bytes $MinBytes
    if ($LASTEXITCODE -ne 0) { throw "Download failed: $Url" }
}

$VadDir = Join-Path $Models "vad"
New-Item -ItemType Directory -Force -Path $VadDir | Out-Null
Download-File "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx" (Join-Path $VadDir "silero_vad.onnx")

$SenseDir = Join-Path $Models "sensevoice"
if (-not (Test-Path -LiteralPath (Join-Path $SenseDir "model.int8.onnx"))) {
    $Archive = Join-Path $Cache "sensevoice-int8-2025-09-09.tar.bz2"
    Download-File "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2025-09-09.tar.bz2" $Archive
    $Extract = Join-Path $Cache "sensevoice_extract"
    New-Item -ItemType Directory -Force -Path $Extract | Out-Null
    tar -xf $Archive -C $Extract
    if ($LASTEXITCODE -ne 0) { throw 'SenseVoice archive extraction failed.' }
    $Source = Get-ChildItem -LiteralPath $Extract -Directory | Select-Object -First 1
    New-Item -ItemType Directory -Force -Path $SenseDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $Source.FullName "model.int8.onnx") -Destination $SenseDir -Force
    Copy-Item -LiteralPath (Join-Path $Source.FullName "tokens.txt") -Destination $SenseDir -Force
}

$FallbackDir = Join-Path $Models "faster-whisper-base"
if (-not (Test-Path -LiteralPath (Join-Path $FallbackDir "model.bin"))) {
    Write-Host "Downloading local fallback ASR: faster-whisper base INT8"
    $Python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $Python)) { throw "Please run 安装运行环境.bat first" }
    & $Python -c "from huggingface_hub import snapshot_download; import sys; snapshot_download('Systran/faster-whisper-base', local_dir=sys.argv[1])" $FallbackDir
    if ($LASTEXITCODE -ne 0) { throw "Fallback ASR download failed" }
}

$PunctDir = Join-Path $Models "punctuation"
if (-not (Test-Path -LiteralPath (Join-Path $PunctDir "model.int8.onnx"))) {
    $PunctArchive = Join-Path $Cache "punctuation-ct-transformer-int8.tar.bz2"
    Download-File "https://github.com/k2-fsa/sherpa-onnx/releases/download/punctuation-models/sherpa-onnx-punct-ct-transformer-zh-en-vocab272727-2024-04-12-int8.tar.bz2" $PunctArchive 50000000
    $PunctExtract = Join-Path $Cache "punctuation_extract"
    New-Item -ItemType Directory -Force -Path $PunctExtract | Out-Null
    tar -xf $PunctArchive -C $PunctExtract
    if ($LASTEXITCODE -ne 0) { throw 'Punctuation archive extraction failed.' }
    $PunctSource = Get-ChildItem -LiteralPath $PunctExtract -Directory | Select-Object -First 1
    New-Item -ItemType Directory -Force -Path $PunctDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $PunctSource.FullName "model.int8.onnx") -Destination $PunctDir -Force
}

$VisionDir = Join-Path $Models "vision"
New-Item -ItemType Directory -Force -Path $VisionDir | Out-Null
Download-File "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" (Join-Path $VisionDir "face_detection_yunet_2023mar.onnx") 200000

$QwenDir = Join-Path $Models "qwen"
New-Item -ItemType Directory -Force -Path $QwenDir | Out-Null
$QwenFile = Join-Path $QwenDir "Qwen3.5-0.8B-Q4_K_M.gguf"
Download-File "https://huggingface.co/bartowski/Qwen_Qwen3.5-0.8B-GGUF/resolve/main/Qwen_Qwen3.5-0.8B-Q4_K_M.gguf?download=true" $QwenFile 500000000

$LlamaDir = Join-Path $Runtime "llama"
if (-not (Test-Path -LiteralPath (Join-Path $LlamaDir "llama-cli.exe"))) {
    $DownloadDir = Join-Path $Runtime "llama_download"
    New-Item -ItemType Directory -Force -Path $DownloadDir | Out-Null
    winget download --id ggml.llamacpp -e --architecture x64 --download-directory $DownloadDir --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw 'llama.cpp download failed. See https://github.com/ggml-org/llama.cpp/releases for a compatible Windows CPU build.' }
    $Zip = Get-ChildItem -LiteralPath $DownloadDir -Filter "*.zip" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $Zip) { throw "llama.cpp zip was not found" }
    Expand-Archive -LiteralPath $Zip.FullName -DestinationPath $LlamaDir -Force
    $Cli = Get-ChildItem -LiteralPath $LlamaDir -Recurse -Filter "llama-cli.exe" | Select-Object -First 1
    if (-not $Cli) { throw "llama-cli.exe was not found" }
    if ($Cli.DirectoryName -ne $LlamaDir) {
        Get-ChildItem -LiteralPath $Cli.DirectoryName | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $LlamaDir -Recurse -Force }
    }
}

Write-Host ""
Write-Host "Models are ready: $Models" -ForegroundColor Green
Write-Host "SenseVoice INT8, token timestamps, faster-whisper fallback, Silero VAD, punctuation, Qwen3.5-0.8B Q4, and llama.cpp are ready."
