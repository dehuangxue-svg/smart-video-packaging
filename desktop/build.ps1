$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$sdkVersion = '1.0.4191.47'
$sdk = Join-Path $PSScriptRoot "vendor\webview2.$sdkVersion"
$archive = Join-Path $PSScriptRoot "vendor\webview2.$sdkVersion.zip"
$native = Join-Path $PSScriptRoot 'native'
New-Item -ItemType Directory -Force -Path $native | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $sdk 'lib\net462\Microsoft.Web.WebView2.Core.dll'))) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $archive) | Out-Null
    Invoke-WebRequest -Uri "https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/$sdkVersion/microsoft.web.webview2.$sdkVersion.nupkg" -OutFile $archive
    Expand-Archive -LiteralPath $archive -DestinationPath $sdk -Force
}
foreach ($name in @('Microsoft.Web.WebView2.Core.dll', 'Microsoft.Web.WebView2.WinForms.dll')) {
    Copy-Item -LiteralPath (Join-Path $sdk "lib\net462\$name") -Destination (Join-Path $native $name) -Force
}
Copy-Item -LiteralPath (Join-Path $sdk 'runtimes\win-x64\native\WebView2Loader.dll') -Destination $native -Force
Copy-Item -LiteralPath (Join-Path $sdk 'LICENSE.txt') -Destination (Join-Path $native 'WebView2-LICENSE.txt') -Force
Copy-Item -LiteralPath (Join-Path $sdk 'NOTICE.txt') -Destination (Join-Path $native 'WebView2-NOTICE.txt') -Force

# A small original editing/play icon; PNG-in-ICO is supported on Windows 10/11.
Add-Type -AssemblyName System.Drawing
$bitmap = New-Object Drawing.Bitmap 256,256
$graphics = [Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.Clear([Drawing.Color]::Transparent)
$dark = New-Object Drawing.SolidBrush ([Drawing.Color]::FromArgb(24,28,35))
$mint = New-Object Drawing.SolidBrush ([Drawing.Color]::FromArgb(48,212,192))
$white = New-Object Drawing.SolidBrush ([Drawing.Color]::FromArgb(245,250,251))
$graphics.FillEllipse($dark, 6,6,244,244)
$graphics.FillRectangle($mint, 57,59,140,18)
$graphics.FillRectangle($mint, 57,178,140,18)
$graphics.FillRectangle($mint, 57,85,16,85)
$graphics.FillRectangle($mint, 181,85,16,85)
$points = [Drawing.Point[]]@([Drawing.Point]::new(104,92),[Drawing.Point]::new(104,164),[Drawing.Point]::new(163,128))
$graphics.FillPolygon($white,$points)
$stream = New-Object IO.MemoryStream
$bitmap.Save($stream,[Drawing.Imaging.ImageFormat]::Png)
$imageBytes = $stream.ToArray()
$iconFile = Join-Path $PSScriptRoot 'app.ico'
$fileStream = [IO.File]::Create($iconFile)
$writer = New-Object IO.BinaryWriter $fileStream
$writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]1)
$writer.Write([byte]0); $writer.Write([byte]0); $writer.Write([byte]0); $writer.Write([byte]0)
$writer.Write([uint16]1); $writer.Write([uint16]32); $writer.Write([uint32]$imageBytes.Length); $writer.Write([uint32]22)
$writer.Write($imageBytes); $writer.Dispose(); $stream.Dispose(); $graphics.Dispose(); $bitmap.Dispose(); $dark.Dispose(); $mint.Dispose(); $white.Dispose()

$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$output = Join-Path $projectRoot '剪辑智能包装.exe'
$compileArgs = @('/nologo', '/target:winexe', '/platform:x64', '/optimize+', '/utf8output',
    "/out:$output", "/win32icon:$iconFile", "/win32manifest:$(Join-Path $PSScriptRoot 'app.manifest')",
    '/r:System.dll', '/r:System.Core.dll', '/r:System.Drawing.dll', '/r:System.Windows.Forms.dll',
    '/r:System.Net.Http.dll', '/r:System.Web.Extensions.dll',
    "/r:$(Join-Path $native 'Microsoft.Web.WebView2.Core.dll')",
    "/r:$(Join-Path $native 'Microsoft.Web.WebView2.WinForms.dll')",
    (Join-Path $PSScriptRoot 'DesktopApp.cs'))
& $compiler @compileArgs
if ($LASTEXITCODE -ne 0) { throw 'Desktop compilation failed.' }
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'desktop.config') -Destination ($output + '.config') -Force
[pscustomobject]@{File=$output;Bytes=(Get-Item -LiteralPath $output).Length;SHA256=(Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash;WebView2SDK=$sdkVersion} | ConvertTo-Json
