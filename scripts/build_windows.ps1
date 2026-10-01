param(
    [string]$FfmpegBin = ""
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$deploy = Join-Path $projectRoot '.venv\Scripts\pyside6-deploy.exe'
$spec = Join-Path $projectRoot 'pysidedeploy.spec'
$tempSpec = Join-Path $projectRoot ('.pysidedeploy-' + [guid]::NewGuid().ToString('N') + '.spec')
$output = Join-Path $projectRoot 'dist\VideoCompare.dist'

if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess) {
    throw 'Build requires 64-bit Windows.'
}
foreach ($required in @($python, $deploy, $spec)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing build dependency: $required. Run uv sync --extra dev --extra build."
    }
}

& $python -c "import av, PySide6; from importlib.metadata import version; assert version('Nuitka') == '4.1.1'; print('PyAV', av.__version__, 'PySide6', PySide6.__version__, 'Nuitka', version('Nuitka'))"
if ($LASTEXITCODE -ne 0) { throw 'Dependency version check failed; synchronize from uv.lock.' }

# Regenerate the transparent app icon from the user's logo before packaging.
& $python (Join-Path $projectRoot 'tools\prepare_logo.py')
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed; check logo/ and tools\prepare_logo.py.' }
$icon = Join-Path $projectRoot 'src\video_compare\assets\app.ico'
if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) { throw "Missing application icon: $icon" }

if ($FfmpegBin) {
    $binaryDir = (Resolve-Path -LiteralPath $FfmpegBin).Path
} else {
    $ffprobeCommand = Get-Command 'ffprobe.exe' -ErrorAction SilentlyContinue
    if (-not $ffprobeCommand) { throw 'ffprobe.exe not found. Pass -FfmpegBin with ffprobe.exe and ffmpeg.exe.' }
    $binaryDir = Split-Path -Parent $ffprobeCommand.Source
}
$ffprobe = Join-Path $binaryDir 'ffprobe.exe'
$ffmpeg = Join-Path $binaryDir 'ffmpeg.exe'
foreach ($required in @($ffprobe, $ffmpeg)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing $required" }
}
$ffprobeVersion = & $ffprobe -version
if ($LASTEXITCODE -ne 0) { throw 'ffprobe version check failed.' }
Write-Host $ffprobeVersion[0]
$ffmpegVersion = & $ffmpeg -version
if ($LASTEXITCODE -ne 0) { throw 'ffmpeg version check failed.' }
Write-Host $ffmpegVersion[0]

if (Test-Path -LiteralPath $output) {
    if (Get-ChildItem -LiteralPath $output -Force | Select-Object -First 1) {
        throw "Output already exists: $output. Move it before rebuilding to avoid stale files."
    }
    Remove-Item -LiteralPath $output
}

Push-Location $projectRoot
$previousVirtualEnv = $env:VIRTUAL_ENV
$previousNuitkaCache = $env:NUITKA_CACHE_DIR
$env:VIRTUAL_ENV = Join-Path $projectRoot '.venv'
$env:NUITKA_CACHE_DIR = Join-Path $projectRoot '.codex-tools\nuitka-cache'
New-Item -ItemType Directory -Path $env:NUITKA_CACHE_DIR -Force | Out-Null
try {
    Copy-Item -LiteralPath $spec -Destination $tempSpec
    & $deploy -c $tempSpec --nuitka-version=4.1.1 -f
    if ($LASTEXITCODE -ne 0) { throw "pyside6-deploy failed with exit code $LASTEXITCODE" }
    $appExe = Join-Path $output 'main.exe'
    if (-not (Test-Path -LiteralPath $appExe -PathType Leaf)) {
        throw "Deployment did not produce the expected standalone executable: $appExe"
    }
    $bundledBin = Join-Path $output 'bin'
    New-Item -ItemType Directory -Path $bundledBin -Force | Out-Null
    Copy-Item -LiteralPath $ffprobe -Destination (Join-Path $bundledBin 'ffprobe.exe')
    Copy-Item -LiteralPath $ffmpeg -Destination (Join-Path $bundledBin 'ffmpeg.exe')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'notices\THIRD_PARTY.md') -Destination (Join-Path $output 'THIRD_PARTY.md')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'README.md') -Destination (Join-Path $output 'README.md')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'KNOWN_ISSUES.md') -Destination (Join-Path $output 'KNOWN_ISSUES.md')
    New-Item -ItemType Directory -Path (Join-Path $output 'docs') -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $output 'reports') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\USER_GUIDE.zh-CN.md') -Destination (Join-Path $output 'docs\USER_GUIDE.zh-CN.md')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\FORMAT_SUPPORT.zh-CN.md') -Destination (Join-Path $output 'docs\FORMAT_SUPPORT.zh-CN.md')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'docs\PROGRESS.md') -Destination (Join-Path $output 'docs\PROGRESS.md')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'reports\ACCEPTANCE.md') -Destination (Join-Path $output 'reports\ACCEPTANCE.md')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'reports\DEMO.md') -Destination (Join-Path $output 'reports\DEMO.md')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'scripts\verify_clean_windows.ps1') -Destination (Join-Path $output 'verify_clean_windows.ps1')
    Copy-Item -LiteralPath (Join-Path $projectRoot 'scripts\verify_clean_windows.cmd') -Destination (Join-Path $output 'verify_clean_windows.cmd')
    $ffmpegRoot = Split-Path -Parent $binaryDir
    foreach ($name in @('LICENSE', 'README.txt')) {
        $source = Join-Path $ffmpegRoot $name
        if (Test-Path -LiteralPath $source -PathType Leaf) {
            Copy-Item -LiteralPath $source -Destination (Join-Path $output "FFmpeg-$name")
        }
    }
    Write-Host "Build complete: $appExe"
    Write-Host 'The built application still requires launch and A22 acceptance verification.'
} finally {
    if (Test-Path -LiteralPath $tempSpec -PathType Leaf) {
        Remove-Item -LiteralPath $tempSpec
    }
    $env:VIRTUAL_ENV = $previousVirtualEnv
    $env:NUITKA_CACHE_DIR = $previousNuitkaCache
    Pop-Location
}
