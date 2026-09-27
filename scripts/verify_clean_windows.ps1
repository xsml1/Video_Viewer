$ErrorActionPreference = 'Stop'
$packageRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$appExe = Join-Path $packageRoot 'main.exe'
$ffmpegExe = Join-Path $packageRoot 'bin\ffmpeg.exe'
$ffprobeExe = Join-Path $packageRoot 'bin\ffprobe.exe'
foreach ($required in @($appExe, $ffmpegExe, $ffprobeExe)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Package file missing: $required"
    }
}

$runRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('VideoViewerSelfTest-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $runRoot | Out-Null
$first = Join-Path $runRoot 'test-pattern-a.mp4'
$second = Join-Path $runRoot 'test-pattern-b.mp4'
$output = Join-Path $runRoot 'result'
$firstImage = Join-Path $runRoot 'test-image-a.png'
$secondImage = Join-Path $runRoot 'test-image-b.webp'
$imageOutput = Join-Path $runRoot 'image-result'

& $ffmpegExe -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=320x180:rate=30:duration=2' -c:v libx264 -pix_fmt yuv420p $first
if ($LASTEXITCODE -ne 0) { throw "Test video A generation failed: exit $LASTEXITCODE" }
& $ffmpegExe -hide_banner -loglevel error -f lavfi -i 'testsrc=size=320x180:rate=30:duration=2' -c:v libx264 -pix_fmt yuv420p $second
if ($LASTEXITCODE -ne 0) { throw "Test video B generation failed: exit $LASTEXITCODE" }

& $appExe $first $second --self-test-output $output
if ($LASTEXITCODE -ne 0) { throw "Application self-test failed: exit $LASTEXITCODE; result: $runRoot" }
$images = @(Get-ChildItem -LiteralPath $output -Filter '*.png' -File)
$records = @(Get-ChildItem -LiteralPath $output -Filter '*.json' -File)
if ($images.Count -lt 2 -or $records.Count -lt 1) {
    throw "Application self-test outputs incomplete: $runRoot"
}
& $ffmpegExe -hide_banner -loglevel error -f lavfi -i 'color=c=red:s=320x180:d=1' -frames:v 1 $firstImage
if ($LASTEXITCODE -ne 0) { throw "Test image A generation failed: exit $LASTEXITCODE" }
& $ffmpegExe -hide_banner -loglevel error -f lavfi -i 'color=c=blue:s=320x180:d=1' -frames:v 1 $secondImage
if ($LASTEXITCODE -ne 0) { throw "Test image B generation failed: exit $LASTEXITCODE" }
& $appExe --mode image --self-test-image-output $imageOutput $firstImage $secondImage
if ($LASTEXITCODE -ne 0) { throw "Image self-test failed: exit $LASTEXITCODE; result: $runRoot" }
if (-not (Test-Path -LiteralPath (Join-Path $imageOutput 'image_compare.png') -PathType Leaf)) {
    throw "Image self-test output missing: $runRoot"
}
Write-Output "CLEAN_WINDOWS_SELF_TEST_OK: $runRoot"
