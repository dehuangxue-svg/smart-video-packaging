$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $projectRoot '剪辑智能包装.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw 'Build the desktop executable first.' }
$shellLink = New-Object -ComObject WScript.Shell
$shortcut = $shellLink.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) '剪辑智能包装.lnk'))
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = $projectRoot
$shortcut.IconLocation = $exe + ',0'
$shortcut.Description = 'Local subtitles, sound effects and timeline editing'
$shortcut.Save()
