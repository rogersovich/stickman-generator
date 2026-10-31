import os
import sys
import time
from pathlib import Path
import soundfile as sf
import numpy as np

# Paksa aktifkan konfigurasi performa terbaik dari manhwa-recap-studio
os.environ["VOXCPM_OPTIMIZE"] = "true"
os.environ["VOXCPM_STUDIO_CLEAN"] = "true"

MANHWA_ROOT = Path(r"D:\Coding\Python\manhwa-recap-studio")
STICKMAN_ROOT = Path(r"D:\Coding\Python\stickman-generator")

if str(MANHWA_ROOT) not in sys.path:
    sys.path.insert(0, str(MANHWA_ROOT))
if str(MANHWA_ROOT / "worker-ml") not in sys.path:
    sys.path.insert(0, str(MANHWA_ROOT / "worker-ml"))

from engines.tts_engine import VoxCPM2Narrator

def main():
    print("=" * 75)
    print("BENCHMARK & PENGUJIAN AUDIO LORA SUARA STICKMAN (VOXCPM2 2B)")
    print("Mengikuti konfigurasi Best Performance: manhwa-recap-studio")
    print("=" * 75)

    lora_checkpoint = MANHWA_ROOT / "checkpoints/lora_stickman_voice/latest"
    ref_wav = MANHWA_ROOT / "data/lora_dataset_stickman/wavs/clip_0001.wav"
    ref_text = "Umurmu 18 tahun, suratnya datang bulan Maret 1943, ibumu menangis, ayahmu diam saja, dia ikut perang yang pertama, dia tahu apa arti surat itu."

    out_dirs = [
        MANHWA_ROOT / "output/lora_stickman_test",
        STICKMAN_ROOT / "output/lora_stickman_test",
    ]
    for d in out_dirs:
        d.mkdir(parents=True, exist_ok=True)

    print(f"LoRA Checkpoint : {lora_checkpoint}")
    print(f"Audio Referensi : {ref_wav}")
    print(f"Pengaturan GPU  : NVIDIA GeForce RTX 3060 12GB (TF32, VOXCPM_OPTIMIZE=true)")
    print("-" * 75)

    # 1. Inisialisasi Model & LoRA
    print("\n[1/4] Memuat model VoxCPM2 + LoRA Stickman Voice...")
    t_load = time.perf_counter()
    narrator = VoxCPM2Narrator(local_only=True, lora_path=str(lora_checkpoint))
    narrator.set_lora_scale(0.7)
    narrator.set_reference(str(ref_wav), ref_text)
    print(f"Model siap dalam {time.perf_counter() - t_load:.2f} detik.")

    # 2. Build Prompt Cache (Zero Overhead Caching)
    print("\n[2/4] Mengompilasi Prompt Cache referensi audio...")
    t_cache = time.perf_counter()
    prompt_cache = narrator.model.tts_model.build_prompt_cache(reference_wav_path=str(ref_wav))
    print(f"Prompt cache selesai dalam {(time.perf_counter() - t_cache)*1000:.2f} ms.")

    # Kalimat uji coba
    test_sentences = [
        ("scene_01", "Stickman kecil itu menatap layar komputer dengan rasa penasaran tinggi, mencari tahu bagaimana animasi ceritanya bisa dibuat."),
        ("scene_02", "Setelah berbulan-bulan merancang sistem visual, akhirnya dia berhasil menciptakan alur cerita yang hidup dan penuh aksi."),
        ("scene_03", "Saat semua persiapan selesai, kini saatnya kita mengeksekusi rencana besar ini tanpa ragu sedikit pun.")
    ]

    print("\n[3/4] Melakukan Warmup (8 Timesteps)...")
    _ = narrator.generate(text="Warmup satu kalimat.", cfg_value=2.5, inference_timesteps=8, lora_scale=0.7, seed=42)

    # 3. Uji Generasi Audio & Benchmark Tiap Kalimat
    print("\n[4/4] Menjalankan Generasi Audio Pengujian & Pengukuran Performa:")
    benchmark_data = []

    for name, text in test_sentences:
        print(f"\n>> Men-generate: [{name}] \"{text[:65]}...\"")
        t0 = time.perf_counter()
        target_text = text.strip()
        if not target_text.endswith((".", "!", "?")):
            target_text += "."

        gen_res = narrator.model.tts_model._generate_with_prompt_cache(
            target_text=target_text,
            prompt_cache=prompt_cache,
            min_len=2,
            max_len=2000,
            inference_timesteps=8,
            cfg_value=2.5,
            retry_badcase=False
        )
        wav, _, _ = next(gen_res)
        audio_arr = np.asarray(wav.squeeze().cpu().numpy(), dtype=np.float32)
        total_time = time.perf_counter() - t0

        audio_dur = len(audio_arr) / 48000.0
        rtf = total_time / max(0.001, audio_dur)
        speed = 1.0 / max(0.001, rtf)
        rms = float(np.sqrt(np.mean(audio_arr**2)))
        peak = float(np.max(np.abs(audio_arr)))

        # Simpan ke kedua folder output
        for d in out_dirs:
            out_file = d / f"{name}_lora0.7x_steps8.wav"
            sf.write(str(out_file), audio_arr, 48000)

        record = {
            "name": name,
            "text": text,
            "infer_time": total_time,
            "audio_dur": audio_dur,
            "rtf": rtf,
            "speed": speed,
            "rms": rms,
            "peak": peak,
        }
        benchmark_data.append(record)
        print(f"   [OK] {out_file.name} | Durasi: {audio_dur:.2f}s | Waktu: {total_time:.2f}s | RTF: {rtf:.3f}x ({speed:.2f}x real-time)")

    # Uji Perbandingan LoRA Scale (0.0x vs 0.7x vs 1.0x) pada Kalimat #1
    print("\n" + "=" * 75)
    print("PENGUJIAN PERBANDINGAN LORA SCALE (Karakter Suara vs Model Dasar)")
    print("=" * 75)
    scale_tests = [0.0, 0.7, 1.0]
    scale_results = []
    sample_text = test_sentences[0][1]

    for sc in scale_tests:
        narrator.set_lora_scale(sc)
        t0 = time.perf_counter()
        target_text = sample_text.strip()
        if not target_text.endswith((".", "!", "?")):
            target_text += "."

        gen_res = narrator.model.tts_model._generate_with_prompt_cache(
            target_text=target_text,
            prompt_cache=prompt_cache,
            min_len=2,
            max_len=2000,
            inference_timesteps=8,
            cfg_value=2.5,
            retry_badcase=False
        )
        wav, _, _ = next(gen_res)
        audio_arr = np.asarray(wav.squeeze().cpu().numpy(), dtype=np.float32)
        elapsed = time.perf_counter() - t0
        dur = len(audio_arr) / 48000.0

        for d in out_dirs:
            sc_out = d / f"compare_lora_scale_{sc:.1f}x.wav"
            sf.write(str(sc_out), audio_arr, 48000)

        scale_results.append({
            "scale": sc,
            "file": f"compare_lora_scale_{sc:.1f}x.wav",
            "time": elapsed,
            "dur": dur,
            "rtf": elapsed / dur
        })
        print(f"Scale {sc:.1f}x: Waktu={elapsed:.2f}s | Audio={dur:.2f}s | File={sc_out.name}")

    # Uji Timesteps (6 vs 8 vs 10 steps)
    print("\n" + "=" * 75)
    print("PENGUJIAN PERBANDINGAN TIMESTEPS DIFUSI (6 vs 8 vs 10 Steps)")
    print("=" * 75)
    narrator.set_lora_scale(0.7)
    steps_list = [6, 8, 10]
    steps_results = []
    for st in steps_list:
        t0 = time.perf_counter()
        target_text = sample_text.strip()
        if not target_text.endswith((".", "!", "?")):
            target_text += "."

        gen_res = narrator.model.tts_model._generate_with_prompt_cache(
            target_text=target_text,
            prompt_cache=prompt_cache,
            min_len=2,
            max_len=2000,
            inference_timesteps=st,
            cfg_value=2.5,
            retry_badcase=False
        )
        wav, _, _ = next(gen_res)
        audio_arr = np.asarray(wav.squeeze().cpu().numpy(), dtype=np.float32)
        elapsed = time.perf_counter() - t0
        dur = len(audio_arr) / 48000.0

        for d in out_dirs:
            st_out = d / f"compare_steps_{st}.wav"
            sf.write(str(st_out), audio_arr, 48000)

        steps_results.append({
            "steps": st,
            "file": f"compare_steps_{st}.wav",
            "time": elapsed,
            "dur": dur,
            "rtf": elapsed / dur
        })
        print(f"Steps={st}: Waktu={elapsed:.2f}s | Audio={dur:.2f}s | RTF={elapsed/dur:.3f}x")

    # Cetak Rangkuman Akhir
    print("\n" + "=" * 75)
    print("TABEL REKAPITULASI BENCHMARK (NVIDIA RTX 3060 12GB)")
    print("=" * 75)
    print(f"{'Scene / Uji':<14} | {'Infer (s)':<10} | {'Audio (s)':<10} | {'RTF':<8} | {'Kecepatan':<15}")
    print("-" * 75)
    for b in benchmark_data:
        print(f"{b['name']:<14} | {b['infer_time']:>7.2f}s   | {b['audio_dur']:>7.2f}s   | {b['rtf']:>5.3f}x  | {b['speed']:>6.2f}x real-time")
    print("-" * 75)
    avg_infer = np.mean([b['infer_time'] for b in benchmark_data])
    avg_dur = np.mean([b['audio_dur'] for b in benchmark_data])
    avg_rtf = np.mean([b['rtf'] for b in benchmark_data])
    print(f"{'RATA-RATA':<14} | {avg_infer:>7.2f}s   | {avg_dur:>7.2f}s   | {avg_rtf:>5.3f}x  | {1.0/avg_rtf:>6.2f}x real-time")
    print("=" * 75)
    print("\nSeluruh berkas audio testing telah disimpan di:")
    for d in out_dirs:
        print(f"  * {d}")

if __name__ == "__main__":
    main()

