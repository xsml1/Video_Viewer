param(
    [string]$Name = '视频对比工具',
    [string]$Target = '',
    [string]$Arguments = '',
    [string]$IconPath = '',
    [string]$WorkingDirectory = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path

if (-not $Target) {
    $packaged = Join-Path $projectRoot 'dist\VideoCompare.dist\main.exe'
    if (Test-Path -LiteralPath $packaged -PathType Leaf) {
        $Target = $packaged
        $working = Join-Path $projectRoot 'dist\VideoCompare.dist'
    } else {
        $Target = Join-Path $projectRoot 'scripts\run_video_compare.cmd'
        $working = $projectRoot
    }
} else {
    $working = $projectRoot
}
if ($WorkingDirectory) { $working = $WorkingDirectory }
if (-not (Test-Path -LiteralPath $Target)) { throw "Shortcut target does not exist: $Target" }

if (-not $IconPath) {
    $candidate = Join-Path $projectRoot 'src\video_compare\assets\app.ico'
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        & (Join-Path $projectRoot '.venv\Scripts\python.exe') (Join-Path $projectRoot 'tools\prepare_logo.py')
        if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
    }
    $IconPath = $candidate
}

$desktop = [Environment]::GetFolderPath('Desktop')
if (-not $desktop) { throw 'Desktop folder not found.' }
$linkPath = Join-Path $desktop "$Name.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = $Target
$shortcut.Arguments = $Arguments
$shortcut.WorkingDirectory = $working
$shortcut.Description = '视频对比工具（本地多路视频同步对比）'
$shortcut.IconLocation = "$IconPath,0"
$shortcut.WindowStyle = 1
$shortcut.Save()

Write-Host "Shortcut created: $linkPath"
Write-Host "Target: $Target"
Write-Host "Working directory: $working"
Write-Host "Icon: $IconPath"
