[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $ProjectRoot ".geoai-runtime"
$StoppedAny = $false

function Stop-RecordedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$RecordPath,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if (-not (Test-Path -LiteralPath $RecordPath -PathType Leaf)) {
        return
    }

    $removeRecord = $false
    try {
        $record = Get-Content -LiteralPath $RecordPath -Raw | ConvertFrom-Json
        $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            Write-Host "$Label is already stopped."
            $removeRecord = $true
            return
        }

        $actualStart = $process.StartTime.ToUniversalTime().ToString("o")
        if ($actualStart -ne [string]$record.started_at_utc) {
            Write-Host "Skipped stale $Label process record; its PID now belongs to another process." -ForegroundColor Yellow
            $removeRecord = $true
            return
        }

        $taskkill = Join-Path $env:SystemRoot "System32\taskkill.exe"
        & $taskkill /PID $process.Id /T /F | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to stop the $Label process tree (PID $($process.Id))."
        }
        $script:StoppedAny = $true
        $removeRecord = $true
        Write-Host "$Label stopped."
    }
    finally {
        if ($removeRecord) {
            Remove-Item -LiteralPath $RecordPath -Force -ErrorAction SilentlyContinue
        }
    }
}

if (-not (Test-Path -LiteralPath $RuntimeDir -PathType Container)) {
    Write-Host "No GeoAI launcher processes were found."
    exit 0
}

Stop-RecordedProcess `
    -RecordPath (Join-Path $RuntimeDir "frontend.process.json") `
    -Label "GeoAI frontend"
Stop-RecordedProcess `
    -RecordPath (Join-Path $RuntimeDir "backend.process.json") `
    -Label "GeoAI backend"

if (-not $StoppedAny) {
    Write-Host "No running GeoAI launcher processes needed to be stopped."
}
