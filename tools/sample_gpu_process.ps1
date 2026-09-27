param(
    [Parameter(Mandatory = $true)][int]$ProcessId,
    [Parameter(Mandatory = $true)][string]$Output,
    [int]$IntervalSeconds = 5,
    [int]$DurationSeconds = 1800
)

$ErrorActionPreference = 'Stop'
if ($IntervalSeconds -le 0 -or $DurationSeconds -le 0) { throw 'Intervals must be positive.' }
if (Test-Path -LiteralPath $Output) { throw "Output already exists: $Output" }
$counterPath = (Get-Counter -ListSet 'GPU Process Memory').PathsWithInstances |
    Where-Object { $_ -match "pid_$($ProcessId)_" -and $_ -like '*Dedicated Usage' } |
    Select-Object -First 1
if (-not $counterPath) { throw "No WDDM dedicated GPU process counter for PID $ProcessId" }
$started = Get-Date
$deadline = $started.AddSeconds($DurationSeconds)
$samples = [System.Collections.Generic.List[object]]::new()
while ((Get-Date) -lt $deadline) {
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) { break }
    try {
        $value = (Get-Counter -Counter $counterPath).CounterSamples[0].CookedValue
    } catch {
        break
    }
    $samples.Add([pscustomobject]@{
        elapsed_s = [Math]::Round(((Get-Date) - $started).TotalSeconds, 3)
        dedicated_bytes = [long]$value
    })
    Start-Sleep -Seconds $IntervalSeconds
}
$report = [pscustomobject]@{
    process_id = $ProcessId
    source = 'Windows WDDM GPU Process Memory / Dedicated Usage'
    counter_path = $counterPath
    started = $started.ToString('o')
    elapsed_seconds = [Math]::Round(((Get-Date) - $started).TotalSeconds, 3)
    samples = $samples
}
$target = [System.IO.Path]::GetFullPath($Output)
$parent = [System.IO.Path]::GetDirectoryName($target)
[System.IO.Directory]::CreateDirectory($parent) | Out-Null
$temporary = "$target.tmp"
if (Test-Path -LiteralPath $temporary) { throw "Temporary output already exists: $temporary" }
$report | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $temporary -Encoding utf8
Move-Item -LiteralPath $temporary -Destination $target
Write-Output "GPU samples: $($samples.Count), report=$target"
