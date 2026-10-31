<#
.SYNOPSIS
    Script Backup Cloudflare R2 ke Google Drive via rclone untuk Stickman Generator.
#>

[CmdletBinding()]
param (
    [string]$Mode = "" # "copy", "move", "check", or interactive if empty
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "    STICKMAN GENERATOR - BACKUP CLOUD R2 -> GOOGLE DRIVE   " -ForegroundColor Yellow
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Baca backend/.env
$EnvFile = Join-Path $ScriptDir "backend\.env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "[ERROR] File backend/.env tidak ditemukan di $EnvFile!" -ForegroundColor Red
    Write-Host "Pastikan file konfigurasi backend/.env sudah ada dan berisi kredensial R2." -ForegroundColor Yellow
    exit 1
}

$EnvVars = @{}
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $parts = $line.Split("=", 2)
        $EnvVars[$parts[0].Trim()] = $parts[1].Trim()
    }
}

$Endpoint = $EnvVars["R2_ENDPOINT_URL"]
$AccountId = $EnvVars["CLOUDFLARE_ACCOUNT_ID"]
$AccessKey = $EnvVars["R2_ACCESS_KEY_ID"]
$SecretKey = $EnvVars["R2_SECRET_ACCESS_KEY"]
$Bucket = $EnvVars["R2_BUCKET_NAME"]
if (-not $Bucket) { $Bucket = "stickman-genarator" }
if (-not $Endpoint -and $AccountId) {
    $Endpoint = "https://$AccountId.r2.cloudflarestorage.com"
}
$GDriveDest = $EnvVars["GDRIVE_BACKUP_DESTINATION"]
if (-not $GDriveDest) { $GDriveDest = "gdrive:StickmanGeneratorArchive" }

if (-not $AccessKey -or -not $SecretKey -or -not $Endpoint) {
    Write-Host "[ERROR] Kredensial R2 di backend/.env belum lengkap!" -ForegroundColor Red
    Write-Host "Pastikan R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, dan R2_ENDPOINT_URL sudah terisi." -ForegroundColor Yellow
    exit 1
}

# 2. Cek apakah rclone terinstall
$rcloneCmd = Get-Command rclone -ErrorAction SilentlyContinue
if (-not $rcloneCmd) {
    Write-Host "[PERINGATAN] rclone belum terinstall di komputer ini." -ForegroundColor Yellow
    Write-Host ""
    $installChoice = Read-Host "Apakah Anda ingin menginstall rclone sekarang via winget? (Y/N)"
    if ($installChoice -match "^[Yy]") {
        Write-Host "Menjalankan: winget install Rclone.Rclone ..." -ForegroundColor Cyan
        try {
            winget install --id Rclone.Rclone --source winget --accept-package-agreements --accept-source-agreements
            Write-Host "Instalasi selesai! Memperbarui PATH sesi saat ini..." -ForegroundColor Green
            # Update PATH in current process
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
            $rcloneCmd = Get-Command rclone -ErrorAction SilentlyContinue
        } catch {
            Write-Host "[GAGAL] Tidak dapat menginstall rclone secara otomatis: $_" -ForegroundColor Red
        }
    }
    
    if (-not $rcloneCmd) {
        Write-Host ""
        Write-Host "Silakan install rclone secara manual:" -ForegroundColor Yellow
        Write-Host "1. Buka PowerShell baru dan jalankan: winget install Rclone.Rclone"
        Write-Host "2. Atau download file rclone.exe dari https://rclone.org/downloads/ dan masukkan ke PATH."
        Write-Host ""
        exit 1
    }
}

Write-Host "[OK] rclone terdeteksi: $($rcloneCmd.Source)" -ForegroundColor Green
Write-Host "Bucket R2: $Bucket" -ForegroundColor Gray
Write-Host "Tujuan GDrive: $GDriveDest" -ForegroundColor Gray
Write-Host ""

# Remote name extraction (e.g. 'gdrive:' -> 'gdrive')
$remoteName = ($GDriveDest.Split(":")[0]).Trim()
$configuredRemotes = @(& rclone listremotes 2>$null) | ForEach-Object { $_.Trim().TrimEnd(":") }

if ($remoteName -and -not ($configuredRemotes -contains $remoteName)) {
    Write-Host "[PERHATIAN] Remote Google Drive '$($remoteName):' belum dikonfigurasi di rclone!" -ForegroundColor Yellow
    Write-Host "Daftar remote yang ada saat ini: $([string]::Join(', ', $configuredRemotes))" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Untuk menghubungkan Google Drive akun Anda ke rclone:" -ForegroundColor Cyan
    Write-Host "  1. Pilih opsi setup rclone config sekarang"
    Write-Host "  2. Beri nama remote: '$remoteName'"
    Write-Host "  3. Pilih tipe storage: drive (Google Drive)"
    Write-Host "  4. Ikuti login Google di browser"
    Write-Host ""
    $setupChoice = Read-Host "Jalankan 'rclone config' sekarang untuk setup remote Google Drive? (Y/N)"
    if ($setupChoice -match "^[Yy]") {
        & rclone config
    } else {
        Write-Host "Setup dibatalkan. Jalankan 'rclone config' jika Anda sudah siap." -ForegroundColor Yellow
        exit 0
    }
}

# String koneksi On-the-Fly Cloudflare R2 ke rclone
$r2ConnectionString = ":s3,provider=Cloudflare,endpoint='$Endpoint',access_key_id='$AccessKey',secret_access_key='$SecretKey':$Bucket"

function Do-Copy {
    Write-Host ""
    Write-Host ">> Memulai proses BACKUP (COPY) dari R2 ke $GDriveDest..." -ForegroundColor Cyan
    Write-Host "Catatan: File di R2 TIDAK akan dihapus (aman)." -ForegroundColor Gray
    Write-Host ""
    & rclone copy $r2ConnectionString $GDriveDest --progress --transfers 4 --fast-list
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "[SUKSES] Semua file berhasil dicopy ke Google Drive ($GDriveDest)!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "[GAGAL] Terjadi kesalahan saat copy (Exit code: $LASTEXITCODE)." -ForegroundColor Red
    }
}

function Do-Move {
    Write-Host ""
    Write-Host ">> PERINGATAN: Memulai BACKUP & CLEANUP (MOVE) ke $GDriveDest!" -ForegroundColor Yellow
    Write-Host "File akan disalin ke Google Drive, lalu otomatis DIHAPUS dari R2 agar kuota 10 GB lega kembali." -ForegroundColor Yellow
    $confirm = Read-Host "Apakah Anda yakin ingin memindahkan & mengosongkan R2? (Ketik 'YAKIN' untuk lanjut)"
    if ($confirm -ne "YAKIN") {
        Write-Host "Operasi dibatalkan oleh pengguna." -ForegroundColor Gray
        return
    }
    Write-Host ""
    Write-Host ">> Menjalankan rclone move..." -ForegroundColor Cyan
    & rclone move $r2ConnectionString $GDriveDest --progress --transfers 4 --fast-list
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "[SUKSES] Semua file berhasil dipindahkan ke Google Drive dan kuota R2 telah dikosongkan!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "[GAGAL] Terjadi kesalahan saat move (Exit code: $LASTEXITCODE)." -ForegroundColor Red
    }
}

function Do-CheckR2 {
    Write-Host ""
    Write-Host ">> Memeriksa file yang ada di Cloudflare R2 ($Bucket)..." -ForegroundColor Cyan
    & rclone size $r2ConnectionString
    Write-Host ""
    & rclone lsf $r2ConnectionString --max-depth 2
}

function Do-CheckGDrive {
    Write-Host ""
    Write-Host ">> Memeriksa folder di Google Drive ($GDriveDest)..." -ForegroundColor Cyan
    & rclone size $GDriveDest
    Write-Host ""
    & rclone lsd $GDriveDest
}

# Mode execution or Interactive Menu
if ($Mode.ToLower() -eq "copy") {
    Do-Copy
    exit 0
} elseif ($Mode.ToLower() -eq "move") {
    Do-Move
    exit 0
} elseif ($Mode.ToLower() -eq "check") {
    Do-CheckR2
    exit 0
}

# Menu Interaktif
while ($true) {
    Write-Host ""
    Write-Host "Pilih operasi backup:" -ForegroundColor Cyan
    Write-Host "  [1] Backup Saja (Copy dari R2 -> Google Drive)" -ForegroundColor White
    Write-Host "  [2] Backup & Kosongkan R2 (Move dari R2 -> Google Drive)" -ForegroundColor White
    Write-Host "  [3] Cek Total Ukuran & File di R2" -ForegroundColor White
    Write-Host "  [4] Cek Isi Folder di Google Drive" -ForegroundColor White
    Write-Host "  [5] Buka Pengaturan Remote Google Drive (rclone config)" -ForegroundColor White
    Write-Host "  [0] Keluar" -ForegroundColor Gray
    Write-Host ""
    $pilihan = Read-Host "Masukkan pilihan (0-5)"

    switch ($pilihan) {
        "1" { Do-Copy; break }
        "2" { Do-Move; break }
        "3" { Do-CheckR2 }
        "4" { Do-CheckGDrive }
        "5" { & rclone config }
        "0" { Write-Host "Selesai."; exit 0 }
        default { Write-Host "Pilihan tidak valid, coba lagi." -ForegroundColor Yellow }
    }
}
