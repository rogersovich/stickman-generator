<#
.SYNOPSIS
    Script Backup Cloudflare R2 ke Google Drive via rclone (Terisolasi per-Aplikasi)
    Khusus untuk akun Google Drive: aseplandak02@gmail.com
#>

[CmdletBinding()]
param (
    [string]$Mode = "" # "copy", "move", "check", "setup", or interactive if empty
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "    STICKMAN GENERATOR - BACKUP CLOUD R2 -> GOOGLE DRIVE   " -ForegroundColor Yellow
Write-Host "       (Konfigurasi Terisolasi Khusus Aplikasi Ini)       " -ForegroundColor Gray
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

$GDriveEmail = $EnvVars["GDRIVE_EMAIL"]
if (-not $GDriveEmail) { $GDriveEmail = "aseplandak02@gmail.com" }

$RemoteName = $EnvVars["GDRIVE_REMOTE_NAME"]
if (-not $RemoteName) { $RemoteName = "gdrive_stickman" }

$FolderName = $EnvVars["GDRIVE_FOLDER_NAME"]
if (-not $FolderName) { $FolderName = "StickmanGeneratorArchive" }

$GDriveDest = $EnvVars["GDRIVE_BACKUP_DESTINATION"]
if (-not $GDriveDest) { $GDriveDest = "$RemoteName`:$FolderName" }

$ConfigPathRel = $EnvVars["RCLONE_CONFIG_PATH"]
if (-not $ConfigPathRel) { $ConfigPathRel = "data/rclone.conf" }
$ConfigPathAbs = Join-Path $ScriptDir $ConfigPathRel

# Pastikan folder data ada
$ConfigDir = Split-Path -Parent $ConfigPathAbs
if (-not (Test-Path $ConfigDir)) {
    New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
}

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
Write-Host "Target Akun Google Drive : $GDriveEmail" -ForegroundColor Yellow
Write-Host "Remote Aplikasi Khusus   : $RemoteName" -ForegroundColor Cyan
Write-Host "Config Terisolasi        : $ConfigPathRel (Terpisah dari settingan luar/global)" -ForegroundColor Gray
Write-Host "Bucket R2 Asal           : $Bucket" -ForegroundColor Gray
Write-Host "Tujuan Google Drive      : $GDriveDest" -ForegroundColor Gray
Write-Host ""

# Cek apakah remote sudah terdaftar di config terisolasi
function Test-RemoteReady {
    if (-not (Test-Path $ConfigPathAbs)) { return $false }
    $content = Get-Content $ConfigPathAbs -Raw -ErrorAction SilentlyContinue
    if ($content -and $content.Contains("[$RemoteName]") -and $content.Contains("token")) {
        return $true
    }
    return $false
}

function Do-SetupRemote {
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "   PENGATURAN KONEKSI GOOGLE DRIVE ($GDriveEmail)         " -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "Browser akan terbuka untuk login ke akun Google Anda." -ForegroundColor White
    Write-Host "PENTING: Pastikan Anda memilih akun: $GDriveEmail" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Menjalankan rclone config create untuk remote '$RemoteName'..." -ForegroundColor Cyan
    
    & rclone config create $RemoteName drive scope=drive --config $ConfigPathAbs
    
    if (Test-RemoteReady) {
        Write-Host ""
        Write-Host "[SUKSES] Akun Google Drive ($GDriveEmail) berhasil terhubung ke $ConfigPathRel!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "[PERINGATAN] Setup selesai tetapi remote belum terdeteksi aktif. Anda bisa mencoba via rclone config interaktif." -ForegroundColor Yellow
        $tryInteractive = Read-Host "Buka rclone config interaktif sekarang? (Y/N)"
        if ($tryInteractive -match "^[Yy]") {
            & rclone config --config $ConfigPathAbs
        }
    }
}

# Cek kesiapan remote
if (-not (Test-RemoteReady) -and $Mode -ne "setup") {
    Write-Host "[PERHATIAN] Remote '$RemoteName' belum terhubung ke Google Drive!" -ForegroundColor Yellow
    Write-Host "Koneksi ini terpisah di file lokal: $ConfigPathRel" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Apakah Anda ingin menghubungkan akun Google Drive ($GDriveEmail) sekarang?" -ForegroundColor Cyan
    $setupChoice = Read-Host "Tekan Y untuk buka login browser (Y/N)"
    if ($setupChoice -match "^[Yy]") {
        Do-SetupRemote
        if (-not (Test-RemoteReady)) {
            exit 1
        }
    } else {
        Write-Host "Dibatalkan. Hubungkan akun terlebih dahulu sebelum backup." -ForegroundColor Yellow
        exit 0
    }
}

# String koneksi On-the-Fly Cloudflare R2 ke rclone
$r2ConnectionString = ":s3,provider=Cloudflare,endpoint='$Endpoint',access_key_id='$AccessKey',secret_access_key='$SecretKey':$Bucket"

function Do-Copy {
    Write-Host ""
    Write-Host ">> Memulai proses BACKUP (COPY) dari R2 ke $GDriveDest..." -ForegroundColor Cyan
    Write-Host "Target Akun: $GDriveEmail" -ForegroundColor Yellow
    Write-Host "Catatan: File di R2 TIDAK akan dihapus (aman)." -ForegroundColor Gray
    Write-Host ""
    & rclone copy $r2ConnectionString $GDriveDest --config $ConfigPathAbs --progress --transfers 4 --fast-list
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
    Write-Host "Target Akun: $GDriveEmail" -ForegroundColor Yellow
    Write-Host "File akan disalin ke Google Drive, lalu otomatis DIHAPUS dari R2 agar kuota 10 GB lega kembali." -ForegroundColor Yellow
    $confirm = Read-Host "Apakah Anda yakin ingin memindahkan & mengosongkan R2? (Ketik 'YAKIN' untuk lanjut)"
    if ($confirm -ne "YAKIN") {
        Write-Host "Operasi dibatalkan oleh pengguna." -ForegroundColor Gray
        return
    }
    Write-Host ""
    Write-Host ">> Menjalankan rclone move..." -ForegroundColor Cyan
    & rclone move $r2ConnectionString $GDriveDest --config $ConfigPathAbs --progress --transfers 4 --fast-list
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
    & rclone size $r2ConnectionString --config $ConfigPathAbs
    Write-Host ""
    & rclone lsf $r2ConnectionString --config $ConfigPathAbs --max-depth 2
}

function Do-CheckGDrive {
    Write-Host ""
    Write-Host ">> Memeriksa folder di Google Drive ($GDriveDest)..." -ForegroundColor Cyan
    Write-Host "Akun: $GDriveEmail" -ForegroundColor Yellow
    & rclone size $GDriveDest --config $ConfigPathAbs
    Write-Host ""
    & rclone lsd $GDriveDest --config $ConfigPathAbs
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
} elseif ($Mode.ToLower() -eq "setup") {
    Do-SetupRemote
    exit 0
}

# Menu Interaktif
while ($true) {
    Write-Host ""
    Write-Host "Pilih operasi backup (Akun: $GDriveEmail):" -ForegroundColor Cyan
    Write-Host "  [1] Backup Saja (Copy dari R2 -> Google Drive)" -ForegroundColor White
    Write-Host "  [2] Backup & Kosongkan R2 (Move dari R2 -> Google Drive)" -ForegroundColor White
    Write-Host "  [3] Cek Total Ukuran & File di R2" -ForegroundColor White
    Write-Host "  [4] Cek Isi Folder di Google Drive" -ForegroundColor White
    Write-Host "  [5] Hubungkan Ulang Akun Google Drive (rclone login)" -ForegroundColor White
    Write-Host "  [0] Keluar" -ForegroundColor Gray
    Write-Host ""
    $pilihan = Read-Host "Masukkan pilihan (0-5)"

    switch ($pilihan) {
        "1" { Do-Copy; break }
        "2" { Do-Move; break }
        "3" { Do-CheckR2 }
        "4" { Do-CheckGDrive }
        "5" { Do-SetupRemote }
        "0" { Write-Host "Selesai."; exit 0 }
        default { Write-Host "Pilihan tidak valid, coba lagi." -ForegroundColor Yellow }
    }
}
