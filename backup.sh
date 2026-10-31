#!/usr/bin/env bash
# Script Backup Cloudflare R2 ke Google Drive via rclone (Terisolasi per-Aplikasi)
# Khusus untuk akun Google Drive: aseplandak02@gmail.com
set -eo pipefail
cd "$(dirname "$0")"

SCRIPT_DIR="$(pwd)"
ENV_FILE="$SCRIPT_DIR/backend/.env"

echo ""
echo "=========================================================="
echo "    STICKMAN GENERATOR - BACKUP CLOUD R2 -> GOOGLE DRIVE   "
echo "       (Konfigurasi Terisolasi Khusus Aplikasi Ini)       "
echo "=========================================================="
echo ""

if [ ! -f "$ENV_FILE" ]; then
  echo "[ERROR] File backend/.env tidak ditemukan di $ENV_FILE!"
  echo "Pastikan file konfigurasi backend/.env sudah ada dan berisi kredensial R2."
  exit 1
fi

# Load variables from backend/.env safely
while IFS='=' read -r key value || [ -n "$key" ]; do
  [[ "$key" =~ ^[[:space:]]*# ]] && continue
  [[ -z "$key" ]] && continue
  key=$(echo "$key" | tr -d '[:space:]')
  value=$(echo "$value" | tr -d '\r' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
  case "$key" in
    R2_ENDPOINT_URL) R2_ENDPOINT_URL="$value" ;;
    CLOUDFLARE_ACCOUNT_ID) CLOUDFLARE_ACCOUNT_ID="$value" ;;
    R2_ACCESS_KEY_ID) R2_ACCESS_KEY_ID="$value" ;;
    R2_SECRET_ACCESS_KEY) R2_SECRET_ACCESS_KEY="$value" ;;
    R2_BUCKET_NAME) R2_BUCKET_NAME="$value" ;;
    GDRIVE_EMAIL) GDRIVE_EMAIL="$value" ;;
    GDRIVE_REMOTE_NAME) GDRIVE_REMOTE_NAME="$value" ;;
    GDRIVE_FOLDER_NAME) GDRIVE_FOLDER_NAME="$value" ;;
    GDRIVE_BACKUP_DESTINATION) GDRIVE_BACKUP_DESTINATION="$value" ;;
    RCLONE_CONFIG_PATH) RCLONE_CONFIG_PATH="$value" ;;
    GDRIVE_CLIENT_ID) GDRIVE_CLIENT_ID="$value" ;;
    GDRIVE_CLIENT_SECRET) GDRIVE_CLIENT_SECRET="$value" ;;
  esac
done < "$ENV_FILE"

R2_BUCKET_NAME="${R2_BUCKET_NAME:-stickman-genarator}"
if [ -z "$R2_ENDPOINT_URL" ] && [ -n "$CLOUDFLARE_ACCOUNT_ID" ]; then
  R2_ENDPOINT_URL="https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com"
fi

GDRIVE_EMAIL="${GDRIVE_EMAIL:-aseplandak02@gmail.com}"
GDRIVE_REMOTE_NAME="${GDRIVE_REMOTE_NAME:-gdrive_stickman}"
GDRIVE_FOLDER_NAME="${GDRIVE_FOLDER_NAME:-StickmanGeneratorArchive}"
GDRIVE_BACKUP_DESTINATION="${GDRIVE_BACKUP_DESTINATION:-${GDRIVE_REMOTE_NAME}:${GDRIVE_FOLDER_NAME}}"
RCLONE_CONFIG_PATH="${RCLONE_CONFIG_PATH:-data/rclone.conf}"

# Pastikan folder config ada
mkdir -p "$(dirname "$SCRIPT_DIR/$RCLONE_CONFIG_PATH")"
CONFIG_ABS="$SCRIPT_DIR/$RCLONE_CONFIG_PATH"

if [ -z "$R2_ACCESS_KEY_ID" ] || [ -z "$R2_SECRET_ACCESS_KEY" ] || [ -z "$R2_ENDPOINT_URL" ]; then
  echo "[ERROR] Kredensial R2 di backend/.env belum lengkap!"
  echo "Pastikan R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, dan R2_ENDPOINT_URL sudah terisi."
  exit 1
fi

# Cek rclone
if ! command -v rclone >/dev/null 2>&1; then
  echo "[PERINGATAN] rclone belum terinstall di komputer ini."
  echo ""
  echo "Silakan install rclone:"
  echo "  - Di macOS (Homebrew): brew install rclone"
  echo "  - Di Linux: curl https://rclone.org/install.sh | sudo bash"
  echo "  - Atau unduh dari https://rclone.org/downloads/"
  echo ""
  exit 1
fi

echo "[OK] rclone terdeteksi: $(command -v rclone)"
echo "Target Akun Google Drive : $GDRIVE_EMAIL"
echo "Remote Aplikasi Khusus   : $GDRIVE_REMOTE_NAME"
echo "Config Terisolasi        : $RCLONE_CONFIG_PATH (Terpisah dari settingan luar/global)"
echo "Bucket R2 Asal           : $R2_BUCKET_NAME"
echo "Tujuan Google Drive      : $GDRIVE_BACKUP_DESTINATION"
echo ""

is_remote_ready() {
  if [ -f "$CONFIG_ABS" ]; then
    if grep -q "\[$GDRIVE_REMOTE_NAME\]" "$CONFIG_ABS" && grep -q "token" "$CONFIG_ABS"; then
      if [ -n "$GDRIVE_CLIENT_ID" ] && ! grep -q "client_id = $GDRIVE_CLIENT_ID" "$CONFIG_ABS"; then
        return 1
      fi
      return 0
    fi
  fi
  return 1
}

do_setup_remote() {
  echo ""
  echo "=========================================================="
  echo "   PENGATURAN KONEKSI GOOGLE DRIVE ($GDRIVE_EMAIL)         "
  echo "=========================================================="
  echo "Browser akan terbuka untuk login ke akun Google Anda."
  echo "PENTING: Pastikan Anda memilih akun: $GDRIVE_EMAIL"
  if [ -n "$GDRIVE_CLIENT_ID" ]; then
    echo "Menggunakan Client ID Pribadi Google Cloud Anda (Bebas Limit & Permanen)."
  fi
  echo ""
  echo "Menjalankan rclone config create untuk remote '$GDRIVE_REMOTE_NAME'..."
  cmdArgs=("config" "create" "$GDRIVE_REMOTE_NAME" "drive" "scope=drive" "--config" "$CONFIG_ABS")
  if [ -n "$GDRIVE_CLIENT_ID" ]; then
    cmdArgs+=("client_id=$GDRIVE_CLIENT_ID")
  fi
  if [ -n "$GDRIVE_CLIENT_SECRET" ]; then
    cmdArgs+=("client_secret=$GDRIVE_CLIENT_SECRET")
  fi
  rclone "${cmdArgs[@]}"
  
  if is_remote_ready; then
    echo ""
    echo "[SUKSES] Akun Google Drive ($GDRIVE_EMAIL) berhasil terhubung ke $RCLONE_CONFIG_PATH!"
  else
    echo ""
    echo "[PERINGATAN] Setup selesai tetapi remote belum aktif. Anda bisa mencoba rclone config interaktif."
    read -p "Buka rclone config interaktif sekarang? (y/n): " tryInteractive
    if [[ "$tryInteractive" =~ ^[Yy]$ ]]; then
      rclone config --config "$CONFIG_ABS"
    fi
  fi
}

if ! is_remote_ready && [ "${1:-}" != "setup" ]; then
  echo "[PERHATIAN] Remote '$GDRIVE_REMOTE_NAME' belum terhubung ke Google Drive!"
  echo "Koneksi ini terpisah di file lokal: $RCLONE_CONFIG_PATH"
  echo ""
  read -p "Hubungkan akun Google Drive ($GDRIVE_EMAIL) sekarang? (y/n): " setupChoice
  if [[ "$setupChoice" =~ ^[Yy]$ ]]; then
    do_setup_remote
    if ! is_remote_ready; then
      exit 1
    fi
  else
    echo "Setup dibatalkan. Hubungkan akun terlebih dahulu sebelum backup."
    exit 0
  fi
fi

R2_CONN=":s3,provider=Cloudflare,endpoint='$R2_ENDPOINT_URL',access_key_id='$R2_ACCESS_KEY_ID',secret_access_key='$R2_SECRET_ACCESS_KEY':$R2_BUCKET_NAME"

do_copy() {
  echo ""
  echo ">> Memulai proses BACKUP (COPY) dari R2 ke $GDRIVE_BACKUP_DESTINATION..."
  echo "Target Akun: $GDRIVE_EMAIL"
  echo "Catatan: File di R2 TIDAK akan dihapus (aman)."
  echo ""
  rclone copy "$R2_CONN" "$GDRIVE_BACKUP_DESTINATION" --config "$CONFIG_ABS" --progress --transfers 4 --fast-list
  echo ""
  echo "[SUKSES] Semua file berhasil dicopy ke Google Drive ($GDRIVE_BACKUP_DESTINATION)!"
}

do_move() {
  echo ""
  echo ">> PERINGATAN: Memulai BACKUP & CLEANUP (MOVE) ke $GDRIVE_BACKUP_DESTINATION!"
  echo "Target Akun: $GDRIVE_EMAIL"
  echo "File akan disalin ke Google Drive, lalu otomatis DIHAPUS dari R2 agar kuota 10 GB lega kembali."
  read -p "Apakah Anda yakin ingin memindahkan & mengosongkan R2? (Ketik 'YAKIN' untuk lanjut): " confirm
  if [ "$confirm" != "YAKIN" ]; then
    echo "Operasi dibatalkan oleh pengguna."
    return
  fi
  echo ""
  echo ">> Menjalankan rclone move..."
  rclone move "$R2_CONN" "$GDRIVE_BACKUP_DESTINATION" --config "$CONFIG_ABS" --progress --transfers 4 --fast-list
  echo ""
  echo "[SUKSES] Semua file berhasil dipindahkan ke Google Drive dan kuota R2 telah dikosongkan!"
}

do_check_r2() {
  echo ""
  echo ">> Memeriksa file yang ada di Cloudflare R2 ($R2_BUCKET_NAME)..."
  rclone size "$R2_CONN" --config "$CONFIG_ABS"
  echo ""
  rclone lsf "$R2_CONN" --config "$CONFIG_ABS" --max-depth 2
}

do_check_gdrive() {
  echo ""
  echo ">> Memeriksa folder di Google Drive ($GDRIVE_BACKUP_DESTINATION)..."
  echo "Akun: $GDRIVE_EMAIL"
  sizeOutput=$(rclone size "$GDRIVE_BACKUP_DESTINATION" --config "$CONFIG_ABS" 2>&1 || true)
  if echo "$sizeOutput" | grep -q "directory not found"; then
    echo ""
    echo "[INFO] Folder '$GDRIVE_FOLDER_NAME' belum ada di Google Drive karena Anda belum pernah melakukan backup."
    echo "Folder ini akan OTOMATIS dibuat oleh rclone saat Anda menjalankan menu [1] atau [2]."
  else
    echo "$sizeOutput"
    echo ""
    rclone lsd "$GDRIVE_BACKUP_DESTINATION" --config "$CONFIG_ABS" || true
  fi
}

do_sync_local() {
  echo ""
  echo ">> Menjalankan sinkronisasi proyek & gambar lokal ke Cloudflare D1 & R2..."
  if [ -f "$SCRIPT_DIR/backend/.venv/bin/python" ]; then
    "$SCRIPT_DIR/backend/.venv/bin/python" "$SCRIPT_DIR/sync_to_cloud.py"
  elif command -v python3 >/dev/null 2>&1; then
    python3 "$SCRIPT_DIR/sync_to_cloud.py"
  else
    python "$SCRIPT_DIR/sync_to_cloud.py"
  fi
}

# Mode dari parameter baris perintah
case "${1:-}" in
  copy) do_copy; exit 0 ;;
  move) do_move; exit 0 ;;
  check) do_check_r2; exit 0 ;;
  setup) do_setup_remote; exit 0 ;;
  sync) do_sync_local; exit 0 ;;
esac

# Menu Interaktif
while true; do
  echo ""
  echo "Pilih operasi backup (Akun: $GDRIVE_EMAIL):"
  echo "  [1] Backup Saja (Copy dari R2 -> Google Drive)"
  echo "  [2] Backup & Kosongkan R2 (Move dari R2 -> Google Drive)"
  echo "  [3] Cek Total Ukuran & File di R2"
  echo "  [4] Cek Isi Folder di Google Drive"
  echo "  [5] Hubungkan Ulang Akun Google Drive (rclone login)"
  echo "  [6] Upload/Sync Proyek Lokal ke Cloud (D1 & R2)"
  echo "  [0] Keluar"
  echo ""
  read -p "Masukkan pilihan (0-6): " pilihan
  case "$pilihan" in
    1) do_copy; break ;;
    2) do_move; break ;;
    3) do_check_r2 ;;
    4) do_check_gdrive ;;
    5) do_setup_remote ;;
    6) do_sync_local ;;
    0) echo "Selesai."; exit 0 ;;
    *) echo "Pilihan tidak valid, coba lagi." ;;
  esac
done
