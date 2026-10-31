# Start backend (FastAPI :8000) + frontend (Vite :5173) + optional TTS worker together. Ctrl+C stops all.
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Check busy ports
foreach ($port in @(8000, 5173)) {
    $busy = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($busy) {
        Write-Error "Port $port is already in use (app already running?). Stop it first before starting."
        exit 1
    }
}

if (-not (Test-Path "backend\.env")) {
    Copy-Item "backend\.env.example" "backend\.env"
    Write-Host "Created backend\.env - fill in the 9router settings if needed."
}

if (-not (Test-Path "frontend\node_modules")) {
    Write-Host "Installing frontend dependencies..."
    Push-Location "frontend"
    npm install
    Pop-Location
}

$hostIp = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }
$startTts = if ($env:START_TTS_WORKER) { $env:START_TTS_WORKER } else { "1" }

$jobs = @()

# Backend
$backendScript = {
    param($hostIp)
    Set-Location "$using:PSScriptRoot\backend"
    uv run uvicorn app.main:app --reload --host $hostIp --port 8000 2>&1 | ForEach-Object { "[backend]  $_" }
}
$jobs += Start-Job -ScriptBlock $backendScript -ArgumentList $hostIp

# Frontend
$frontendScript = {
    Set-Location "$using:PSScriptRoot\frontend"
    npm run dev -- --strictPort 2>&1 | ForEach-Object { "[frontend] $_" }
}
$jobs += Start-Job -ScriptBlock $frontendScript

# TTS Worker if venv exists
$pythonExe = "$PSScriptRoot\worker-tts\.venv-ml\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $altPy = "D:\Coding\Python\manhwa-recap-studio\.venv-ml\Scripts\python.exe"
    if (Test-Path $altPy) {
        $pythonExe = $altPy
    }
}
if ($startTts -ne "0" -and (Test-Path $pythonExe)) {
    $ttsScript = {
        param($py)
        Set-Location "$using:PSScriptRoot"
        & $py "worker-tts\main.py" 2>&1 | ForEach-Object { "[tts]      $_" }
    }
    $jobs += Start-Job -ScriptBlock $ttsScript -ArgumentList $pythonExe
}

Write-Host "App: http://localhost:5173   (Ctrl+C to stop)"

try {
    while ($true) {
        foreach ($job in $jobs) {
            Receive-Job $job | Write-Host
            if ($job.State -eq "Failed" -or $job.State -eq "Stopped") {
                throw "Job $($job.Id) stopped unexpectedly"
            }
        }
        Start-Sleep -Milliseconds 250
    }
}
finally {
    Write-Host "`nStopping all processes..."
    $jobs | Stop-Job -PassThru | Remove-Job
}
