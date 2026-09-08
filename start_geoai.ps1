[CmdletBinding()]
param(
    [switch]$NoBrowser
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackEndDir = Join-Path $ProjectRoot "GIS_agent\back_end"
$FrontEndDir = Join-Path $ProjectRoot "GIS_agent\front_end"
$RuntimeDir = Join-Path $ProjectRoot ".geoai-runtime"
$BackEndUrl = "http://127.0.0.1:5000/api/health"
$FrontEndHealthUrl = "http://127.0.0.1:5173/"
$FrontEndBrowserUrl = "http://localhost:5173/"
$StartedProcesses = @()

function Test-ServiceUrl {
    param([Parameter(Mandatory = $true)][string]$Url)

    $response = $null
    try {
        $request = [System.Net.HttpWebRequest]::Create($Url)
        $request.Method = "GET"
        $request.Proxy = $null
        $request.Timeout = 1000
        $request.ReadWriteTimeout = 1000
        $response = $request.GetResponse()
        return ([int]$response.StatusCode -ge 200 -and [int]$response.StatusCode -lt 500)
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $response) {
            $response.Close()
        }
    }
}

function Wait-ServiceUrl {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Label,
        [System.Diagnostics.Process]$Process,
        [int]$TimeoutSeconds = 60
    )

    for ($attempt = 0; $attempt -lt $TimeoutSeconds; $attempt++) {
        if (Test-ServiceUrl -Url $Url) {
            return
        }
        if ($null -ne $Process -and $Process.HasExited) {
            throw "$Label stopped during startup (exit code $($Process.ExitCode))."
        }
        Start-Sleep -Seconds 1
    }
    throw "$Label did not become ready within $TimeoutSeconds seconds."
}

function Get-PythonLaunch {
    if (-not [string]::IsNullOrWhiteSpace($env:GEOAI_PYTHON)) {
        if (-not (Test-Path -LiteralPath $env:GEOAI_PYTHON -PathType Leaf)) {
            throw "GEOAI_PYTHON does not point to an existing Python executable."
        }
        return [PSCustomObject]@{
            FilePath = $env:GEOAI_PYTHON
            PrefixArguments = @()
        }
    }

    $localCandidates = @(
        (Join-Path $BackEndDir ".venv\Scripts\python.exe"),
        (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
        (Join-Path $env:USERPROFILE "anaconda3\python.exe"),
        (Join-Path $env:USERPROFILE "miniconda3\python.exe"),
        "C:\ProgramData\anaconda3\python.exe",
        "C:\ProgramData\miniconda3\python.exe"
    )
    foreach ($candidate in $localCandidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return [PSCustomObject]@{
                FilePath = $candidate
                PrefixArguments = @()
            }
        }
    }

    $pythonInstallRoot = Join-Path $env:LOCALAPPDATA "Programs\Python"
    if (Test-Path -LiteralPath $pythonInstallRoot -PathType Container) {
        $installedPython = Get-ChildItem -LiteralPath $pythonInstallRoot -Directory `
            -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object { Join-Path $_.FullName "python.exe" } |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
        if ($null -ne $installedPython) {
            return [PSCustomObject]@{
                FilePath = $installedPython
                PrefixArguments = @()
            }
        }
    }

    $pyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($null -ne $pyLauncher) {
        return [PSCustomObject]@{
            FilePath = $pyLauncher.Source
            PrefixArguments = @("-3")
        }
    }

    $python = Get-Command "python.exe" -ErrorAction SilentlyContinue
    if ($null -ne $python) {
        return [PSCustomObject]@{
            FilePath = $python.Source
            PrefixArguments = @()
        }
    }

    throw "Python 3 was not found. Install Python, create GIS_agent\back_end\.venv, or set GEOAI_PYTHON."
}

function Save-ProcessRecord {
    param(
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)][string]$Path
    )

    @{
        pid = $Process.Id
        started_at_utc = $Process.StartTime.ToUniversalTime().ToString("o")
    } | ConvertTo-Json | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Register-StartedProcess {
    param(
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process,
        [Parameter(Mandatory = $true)][string]$RecordPath
    )

    Save-ProcessRecord -Process $Process -Path $RecordPath
    $script:StartedProcesses += [PSCustomObject]@{
        Process = $Process
        RecordPath = $RecordPath
    }
}

function Stop-NewProcesses {
    foreach ($item in $script:StartedProcesses) {
        try {
            if (-not $item.Process.HasExited) {
                Stop-Process -Id $item.Process.Id -Force -ErrorAction Stop
            }
        }
        catch {
            # Preserve the original startup error.
        }
        if (Test-Path -LiteralPath $item.RecordPath) {
            Remove-Item -LiteralPath $item.RecordPath -Force
        }
    }
}

try {
    if (-not (Test-Path -LiteralPath $BackEndDir -PathType Container)) {
        throw "Backend directory not found: $BackEndDir"
    }
    if (-not (Test-Path -LiteralPath $FrontEndDir -PathType Container)) {
        throw "Frontend directory not found: $FrontEndDir"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $BackEndDir ".env") -PathType Leaf)) {
        throw "Backend .env file is missing. Copy .env.example to .env and add the Azure credentials."
    }
    if (-not (Test-Path -LiteralPath (Join-Path $FrontEndDir "node_modules") -PathType Container)) {
        throw "Frontend dependencies are missing. Run npm install once in GIS_agent\front_end."
    }

    New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

    $backEndProcess = $null
    if (Test-ServiceUrl -Url $BackEndUrl) {
        Write-Host "GeoAI backend is already running on port 5000."
    }
    else {
        $pythonLaunch = Get-PythonLaunch
        $backEndOut = Join-Path $RuntimeDir "backend.out.log"
        $backEndError = Join-Path $RuntimeDir "backend.error.log"
        $backEndArguments = @($pythonLaunch.PrefixArguments) + @("-u", "server.py")
        $backEndProcess = Start-Process `
            -FilePath $pythonLaunch.FilePath `
            -ArgumentList $backEndArguments `
            -WorkingDirectory $BackEndDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $backEndOut `
            -RedirectStandardError $backEndError `
            -PassThru
        Register-StartedProcess `
            -Process $backEndProcess `
            -RecordPath (Join-Path $RuntimeDir "backend.process.json")
        Write-Host "Starting GeoAI backend..."
        Wait-ServiceUrl -Url $BackEndUrl -Label "GeoAI backend" -Process $backEndProcess
    }

    $frontEndProcess = $null
    if (Test-ServiceUrl -Url $FrontEndHealthUrl) {
        Write-Host "GeoAI frontend is already running on port 5173."
    }
    else {
        $node = Get-Command "node.exe" -ErrorAction SilentlyContinue
        if ($null -eq $node) {
            throw "Node.js was not found. Install Node.js and ensure node.exe is available."
        }
        $viteCli = Join-Path $FrontEndDir "node_modules\vite\bin\vite.js"
        if (-not (Test-Path -LiteralPath $viteCli -PathType Leaf)) {
            throw "Vite is missing. Run npm install once in GIS_agent\front_end."
        }
        $frontEndOut = Join-Path $RuntimeDir "frontend.out.log"
        $frontEndError = Join-Path $RuntimeDir "frontend.error.log"
        $frontEndArguments = ('"{0}" --host 127.0.0.1 --port 5173 --strictPort' -f $viteCli)
        $frontEndProcess = Start-Process `
            -FilePath $node.Source `
            -ArgumentList $frontEndArguments `
            -WorkingDirectory $FrontEndDir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $frontEndOut `
            -RedirectStandardError $frontEndError `
            -PassThru
        Register-StartedProcess `
            -Process $frontEndProcess `
            -RecordPath (Join-Path $RuntimeDir "frontend.process.json")
        Write-Host "Starting GeoAI frontend..."
        Wait-ServiceUrl -Url $FrontEndHealthUrl -Label "GeoAI frontend" -Process $frontEndProcess
    }

    Write-Host "GeoAI is ready: $FrontEndBrowserUrl" -ForegroundColor Green
    Write-Host "Runtime logs: $RuntimeDir"
    if (-not $NoBrowser) {
        Start-Process $FrontEndBrowserUrl
    }
}
catch {
    Stop-NewProcesses
    Write-Host "GeoAI startup failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Check the logs in $RuntimeDir" -ForegroundColor Yellow
    exit 1
}
