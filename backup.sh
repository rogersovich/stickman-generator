#!/usr/bin/env bash
# Script Backup Cloudflare R2 ke Google Drive via rclone untuk Stickman Generator (macOS / Linux)
set -eo pipefail
cd "$(dirname "$0")"

SCRIPT_DIR="$(pwd)"
ENV_FILE="$SCRIPT_DIR/backend/.env"

echo ""
echo "=========================================================="
echo "    STICKMAN GENERATOR - BACKUP CLOUD R2 -> GOOGLE DRIVE   "
echo "=========================================================="
echo ""

if [ ! -f "$ENV_FILE" ]; then
  echo "[ERROR] File backend/.env tidak ditemukan di $ENV_FILE!"
  echo "Pastikan file konfigurasi backend/.env sudah ada dan berisi kredensial R2."
  exit 1
fi

# Load variables from backend/.env safely
while IFS='=' read -r key value || [ -n "$key" ]; do
  # Ignore comments and empty lines
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
    GDRIVE_BACKUP_DESTINATION) GDRIVE_BACKUP_DESTINATION="$value" ;;
  esac
done < "$ENV_FILE"

R2_BUCKET_NAME="${R2_BUCKET_NAME:-stickman-genarator}"
if [ -z "$R2_ENDPOINT_URL" ] && [ -n "$CLOUDFLARE_ACCOUNT_ID" ]; then
  R2_ENDPOINT_URL="https://${CLOUDFLARE_ACCOUNT_ID}.r2.cloudflarestorage.com"
fi
GDRIVE_BACKUP_DESTINATION="${GDRIVE_BACKUP_DESTINATION:-gdrive:StickmanGeneratorArchive}"

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
echo "Bucket R2: $R2_BUCKET_NAME"
echo "Tujuan GDrive: $GDRIVE_BACKUP_DESTINATION"
echo ""

# Cek apakah remote GDrive sudah dikonfigurasi
REMOTE_NAME="${GDRIVE_BACKUP_DESTINATION%%:*}"
CONFIGURED_REMOTES=$(rclone listremotes 2>/dev/null | tr -d ':' || true)

if ! echo "$CONFIGURED_REMOTES" | grep -qw "$REMOTE_NAME"; then
  echo "[PERHATIAN] Remote Google Drive '${REMOTE_NAME}:' belum dikonfigurasi di rclone!"
  echo "Daftar remote saat ini: $(echo $CONFIGURED_REMOTES | tr '\n' ' ')"
  echo ""
  echo "Untuk menghubungkan Google Drive akun Anda ke rclone:"
  echo "  1. Pilih opsi setup rclone config sekarang"
  echo "  2. Beri nama remote: '$REMOTE_NAME'"
  echo "  3. Pilih tipe storage: drive (Google Drive)"
  echo "  4. Ikuti login Google di browser"
  echo ""
  read -p "Jalankan 'rclone config' sekarang untuk setup remote Google Drive? (y/n) " setupChoice
  if [[ "$setupChoice" =~ ^[Yy]$ ]]; then
    rclone config
  else
    echo "Setup dibatalkan. Jalankan 'rclone config' jika Anda sudah siap."
    exit 0
  fi
fi

R2_CONN=":s3,provider=Cloudflare,endpoint='$R2_ENDPOINT_URL',access_key_id='$R2_ACCESS_KEY_ID',secret_access_key='$R2_SECRET_ACCESS_KEY':$R2_BUCKET_NAME"

do_copy() {
  echo ""
  echo ">> Memulai proses BACKUP (COPY) dari R2 ke $GDRIVE_BACKUP_DESTINATION..."
  echo "Catatan: File di R2 TIDAK akan dihapus (aman)."
  echo ""
  rclone copy "$R2_CONN" "$GDRIVE_BACKUP_DESTINATION" --progress --transfers 4 --fast-list
  echo ""
  echo "[SUKSES] Semua file berhasil dicopy ke Google Drive ($GDRIVE_BACKUP_DESTINATION)!"
}

do_move() {
  echo ""
  echo ">> PERINGATAN: Memulai BACKUP & CLEANUP (MOVE) ke $GDRIVE_BACKUP_DESTINATION!"
  echo "File akan disalin ke Google Drive, lalu otomatis DIHAPUS dari R2 agar kuota 10 GB lega kembali."
  read -p "Apakah Anda yakin ingin memindahkan & mengosongkan R2? (Ketik 'YAKIN' untuk lanjut): " confirm
  if [ "$confirm" != "YAKIN" ]; then
    echo "Operasi dibatalkan oleh pengguna."
    return
  fi
  echo ""
  echo ">> Menjalankan rclone move..."
  rclone move "$R2_CONN" "$GDRIVE_BACKUP_DESTINATION" --progress --transfers 4 --fast-list
  echo ""
  echo "[SUKSES] Semua file berhasil dipindahkan ke Google Drive dan kuota R2 telah dikosongkan!"
}

do_check_r2() {
  echo ""
  echo ">> Memeriksa file yang ada di Cloudflare R2 ($R2_BUCKET_NAME)..."
  rclone size "$R2_CONN"
  echo ""
  rclone lsf "$R2_CONN" --max-depth 2
}

do_check_gdrive() {
  echo ""
  echo ">> Memeriksa folder di Google Drive ($GDRIVE_BACKUP_DESTINATION)..."
  rclone size "$GDRIVE_BACKUP_DESTINATION"
  echo ""
  rclone lsd "$GDRIVE_BACKUP_DESTINATION"
}

# Mode dari parameter baris perintah
case "${1:-}" in
  copy) do_copy; exit 0 ;;
  move) do_move; exit 0 ;;
  check) do_check_r2; exit 0 ;;
esac

# Menu Interaktif
while true; do
  echo ""
  echo "Pilih operasi backup:"
  echo "  [1] Backup Saja (Copy dari R2 -> Google Drive)"
  echo "  [2] Backup & Kosongkan R2 (Move dari R2 -> Google Drive)"
  echo "  [3] Cek Total Ukuran & File di R2"
  echo "  [4] Cek Isi Folder di Google Drive"
  echo "  [5] Buka Pengaturan Remote Google Drive (rclone config)"
  echo "  [0] Keluar"
  echo ""
  read -p "Masukkan pilihan (0-5): " pilihan
  case "$pilihan" in
    1) do_copy; break ;;
    2) do_move; break ;;
    3) do_check_r2 ;;
    4) do_check_gdrive ;;
    5) rclone config ;;
    0) echo "Selesai."; exit 0 ;;
    *) echo "Pilihan tidak valid, coba lagi." ;;
  esac
done
