$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PIP_CACHE_DIR = Join-Path $projectRoot 'data\pip-cache'
$env:HF_HOME = Join-Path $projectRoot 'data\cache\huggingface'
$env:TEMP = Join-Path $projectRoot 'data\temp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
$python = Get-Command python -ErrorAction Stop
& $python.Source -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 x64 (with Add to PATH enabled), then retry.' }
$venv = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venv)) {
    & $python.Source -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $venv -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip installation failed.' }
& $venv -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'config.json'))) {
    Copy-Item -LiteralPath (Join-Path $projectRoot 'config.example.json') -Destination (Join-Path $projectRoot 'config.json')
}
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    Write-Warning 'FFmpeg and ffprobe are required. Install FFmpeg from https://ffmpeg.org/download.html and add its bin folder to PATH.'
}
Write-Host 'Python dependencies installed. Next: download models, then build the desktop app.'
