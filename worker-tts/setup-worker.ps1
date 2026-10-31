# Create worker-tts\.venv-ml (Python 3.10) and install the TTS worker with CUDA torch. Windows.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    Write-Host "The Python launcher 'py' was not found. Install Python 3.10 from python.org (tick 'py launcher')."
    exit 1
}
if (-not (Test-Path .venv-ml)) { py -3.10 -m venv .venv-ml }
$py = ".venv-ml\Scripts\python.exe"

& $py -m pip install --upgrade pip
# CUDA build of torch first, so requirements.txt does not pull the CPU build
& $py -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
& $py -m pip install -r requirements.txt
& $py -m pip install voxcpm
if ($LASTEXITCODE -ne 0) { Write-Host "WARNING: voxcpm failed to install; the worker will only offer OmniVoice." }
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
Write-Host "Done. Start the worker with: worker-tts\run-worker.bat"
