param(
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$appUrl = 'http://127.0.0.1:8765/'
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$appFile = Join-Path $projectRoot 'app.py'
$modelFile = Join-Path $projectRoot 'models\sensevoice\model.int8.onnx'
$logDir = Join-Path $projectRoot 'data\logs'
$stdoutLog = Join-Path $logDir 'server-output.log'
$stderrLog = Join-Path $logDir 'server-error.log'

function Test-PackagingServer {
    try {
        $response = Invoke-RestMethod -Uri ($appUrl + 'api/desktop-health') -TimeoutSec 2
        return $response.application -eq 'smart-video-packaging' -and $response.root -eq $projectRoot
    }
    catch {
        return $false
    }
}

try {
    $desktopExe = Join-Path $projectRoot '剪辑智能包装.exe'
    if (-not $NoBrowser -and (Test-Path -LiteralPath $desktopExe)) {
        Start-Process -FilePath $desktopExe -WorkingDirectory $projectRoot
        exit 0
    }
    if (-not (Test-Path -LiteralPath $pythonExe)) {
        throw 'Python runtime is missing. Run the environment installer first.'
    }
    if (-not (Test-Path -LiteralPath $appFile)) {
        throw 'app.py is missing. The application folder is incomplete.'
    }

    if (-not (Test-PackagingServer)) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
        Start-Process -FilePath $pythonExe `
            -ArgumentList @('app.py') `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdoutLog `
            -RedirectStandardError $stderrLog | Out-Null

        $ready = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            Start-Sleep -Milliseconds 500
            if (Test-PackagingServer) {
                $ready = $true
                break
            }
        }
        if (-not $ready) {
            throw "The server did not start within 30 seconds. See: $stderrLog"
        }
    }

    if (-not $NoBrowser) {
        Start-Process -FilePath $appUrl
    }
    exit 0
}
catch {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $message = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $($_.Exception.Message)"
    Add-Content -LiteralPath $stderrLog -Value $message -Encoding UTF8
    Write-Error $message
    exit 1
}
