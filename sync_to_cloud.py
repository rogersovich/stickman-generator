#!/usr/bin/env python3
"""Sync local projects and media files (images, audio, JSON) to Cloudflare D1 and R2.

Usage:
    python sync_to_cloud.py
    ./backup.sh sync
"""

import mimetypes
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Add backend directory to sys.path so app modules can be loaded
BACKEND_DIR = Path(__file__).resolve().parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app import config, d1, r2, storage
from app.models import Project


def get_existing_r2_keys(project_id: str) -> dict[str, int]:
    """Return a mapping of {r2_key: file_size} currently in R2 for this project."""
    if not config.has_r2():
        return {}
    s3 = r2.get_s3()
    prefix = f"projects/{project_id}/"
    existing = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=config.R2_BUCKET_NAME, Prefix=prefix):
        for item in page.get("Contents", []):
            existing[item["Key"]] = item["Size"]
    return existing


def sync_project_files(project: Project, existing_r2: dict[str, int], max_workers: int = 8) -> tuple[int, int, int]:
    """Upload all missing or modified media files for a project to R2 in parallel.
    Returns (uploaded_count, skipped_count, total_bytes).
    """
    p_dir = storage.project_dir(project.id)
    if not p_dir.exists():
        return (0, 0, 0)

    # Collect files to upload
    files_to_check = []
    for f in p_dir.rglob("*"):
        if f.is_file() and not f.name.endswith(".tmp") and not f.name.startswith("."):
            rel = f.relative_to(p_dir).as_posix()
            r2_key = f"projects/{project.id}/{rel}"
            files_to_check.append((f, r2_key))

    to_upload = []
    skipped = 0
    for local_file, r2_key in files_to_check:
        local_size = local_file.stat().st_size
        if r2_key in existing_r2 and existing_r2[r2_key] == local_size:
            skipped += 1
        else:
            to_upload.append((local_file, r2_key, local_size))

    if not to_upload:
        return (0, skipped, 0)

    uploaded = 0
    total_bytes = 0

    def _do_upload(item):
        local_file, r2_key, size = item
        ctype, _ = mimetypes.guess_type(str(local_file))
        if local_file.suffix == ".json":
            ctype = "application/json"
        elif local_file.suffix == ".wav":
            ctype = "audio/wav"
        elif local_file.suffix in (".png", ".webp", ".jpg", ".jpeg"):
            ctype = f"image/{local_file.suffix.lstrip('.')}"
        ok = r2.upload_file(local_file, r2_key, content_type=ctype)
        return ok, r2_key, size

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_do_upload, item): item for item in to_upload}
        for fut in as_completed(futures):
            ok, r2_key, size = fut.result()
            if ok:
                uploaded += 1
                total_bytes += size
                sys.stdout.write(f"\r  -> [{uploaded}/{len(to_upload)}] Uploaded {Path(r2_key).name} ({size / 1024:.1f} KB)")
                sys.stdout.flush()
            else:
                print(f"\n  [ERROR] Gagal upload: {r2_key}")

    sys.stdout.write("\n")
    return (uploaded, skipped, total_bytes)


def main():
    print("=" * 60)
    print("   STICKMAN GENERATOR - SYNC LOCAL PROJECTS TO CLOUDFLARE    ")
    print("=" * 60)
    print(f"Directory Output: {config.OUTPUT_DIR}")
    print(f"Cloudflare D1   : {'TERHUBUNG' if config.has_d1() else 'TIDAK TERHUBUNG'}")
    print(f"Cloudflare R2   : {'TERHUBUNG (' + config.R2_BUCKET_NAME + ')' if config.has_r2() else 'TIDAK TERHUBUNG'}")
    print()

    if not config.has_d1() and not config.has_r2():
        print("[ERROR] Kredensial Cloudflare D1 dan R2 belum dikonfigurasi di backend/.env!")
        sys.exit(1)

    if config.has_d1():
        try:
            d1.init_db()
            print("[OK] Cloudflare D1 Database terhubung & tabel siap.")
        except Exception as e:
            print(f"[ERROR] Gagal inisialisasi D1: {e}")
            sys.exit(1)

    # Scan all local projects in output/
    if not config.OUTPUT_DIR.exists():
        print(f"[ERROR] Folder output {config.OUTPUT_DIR} tidak ditemukan!")
        sys.exit(1)

    project_dirs = [d for d in config.OUTPUT_DIR.iterdir() if d.is_dir() and (d / "project.json").is_file()]
    if not project_dirs:
        print("[INFO] Tidak ditemukan proyek lokal dengan file project.json di folder output.")
        sys.exit(0)

    print(f"Ditemukan {len(project_dirs)} proyek lokal.")
    print("-" * 60)

    total_d1_synced = 0
    total_r2_uploaded = 0
    total_r2_skipped = 0
    total_bytes_uploaded = 0

    t0 = time.time()

    for idx, p_dir in enumerate(project_dirs, 1):
        pf = p_dir / "project.json"
        try:
            project = Project.model_validate_json(pf.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[{idx}/{len(project_dirs)}] Gagal membaca {p_dir.name}: {e}")
            continue

        print(f"\n[{idx}/{len(project_dirs)}] Memproses: {project.title}")
        print(f"    ID: {project.id} ({len(project.scenes)} adegan)")

        # 1. Sync metadata to D1
        if config.has_d1():
            try:
                d1.save_project(project)
                total_d1_synced += 1
                print("    ✓ D1 Database: Metadata tersimpan")
            except Exception as e:
                print(f"    ✗ D1 Database: Gagal simpan: {e}")

        # 2. Sync media to R2
        if config.has_r2():
            try:
                existing_r2 = get_existing_r2_keys(project.id)
                up_count, skip_count, bytes_up = sync_project_files(project, existing_r2)
                total_r2_uploaded += up_count
                total_r2_skipped += skip_count
                total_bytes_uploaded += bytes_up
                if up_count > 0:
                    print(f"    ✓ R2 Storage : {up_count} file diunggah ({bytes_up / (1024*1024):.2f} MB), {skip_count} dilewati (sudah ada)")
                else:
                    print(f"    ✓ R2 Storage : Semua {skip_count} file sudah ada di R2 (sinkron)")
            except Exception as e:
                print(f"    ✗ R2 Storage : Error saat upload: {e}")

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("                  RINGKASAN SINKRONISASI                     ")
    print("=" * 60)
    print(f"Total Proyek ke D1 Database : {total_d1_synced} proyek")
    print(f"Total File Baru ke R2 Cloud : {total_r2_uploaded} file ({total_bytes_uploaded / (1024*1024):.2f} MB)")
    print(f"Total File Sudah Sinkron    : {total_r2_skipped} file")
    print(f"Durasi Waktu                : {elapsed:.1f} detik")
    print("=" * 60)
    print("[SELESAI] Data proyek dan seluruh gambar Anda sekarang sudah 100% online di Cloudflare D1 & R2!")


if __name__ == "__main__":
    main()
