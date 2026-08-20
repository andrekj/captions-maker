# Captions Maker

Aplikasi web lokal untuk membuat caption video dengan transkripsi **Whisper** (faster-whisper): upload video berisi voiceover → transkripsi otomatis per kata → edit/review → render caption terbakar (burn-in) ke MP4.

## Fitur

- Upload video + transkripsi voiceover otomatis (Whisper, lokal — tanpa internet)
- Caption per kata (word-level timing)
- Review & edit caption sebelum render
- Styling: font, ukuran, warna (palet 10 warna), posisi caption (fix tengah, tidak melayang antar-scene)
- Preview dan hasil render ukuran font konsisten
- Export MP4 dengan caption burn-in (ffmpeg + libass)
- Varian desktop opsional: `captions_maker_ctk.py` (customtkinter)

## Kebutuhan Sistem

| Komponen | Versi / Catatan |
|---|---|
| OS | Windows 10/11 (path & script `.bat`/`.vbs` khusus Windows) |
| Python | 3.10+ (tested: 3.11) |
| ffmpeg | Wajib, harus tersedia di `PATH`, dengan **libass** & **libx264** (`ffmpeg -filters` harus memuat filter `ass` dan encoder `libx264`) |
| faster-whisper | `pip install faster-whisper` (model diunduh otomatis saat pertama kali dipakai) |
| customtkinter | Hanya untuk varian desktop, opsional untuk web UI |

> ffmpeg di Windows: download build dari https://www.gyan.dev/ffmpeg/builds/ (release full) lalu tambahkan folder `bin` ke PATH. Cek: `ffmpeg -version`.

## Instalasi

```bash
cd path/ke/Captions\ Maker
python -m pip install -r requirements.txt
```

Isi `requirements.txt`: `faster-whisper>=1.0.0`, `customtkinter>=5.2.0`.

## Menjalankan

### Cara cepat (Windows)

- Web UI: double-click **`start_captions_maker.bat`** → server berjalan tersembunyi, browser terbuka otomatis di:

  ```
  http://127.0.0.1:8770/captions-maker.html
  ```

- Varian desktop: double-click **`start_captions_maker_ctk.bat`**

Script memakai Python dari Hermes venv (`%LOCALAPPDATA%\hermes\hermes-agent\venv`) jika ada, fallback ke `python` di PATH.

### Manual

```bash
cd "C:/Users/akj/Desktop/Captions Maker"
python captions_maker_server.py
# buka http://127.0.0.1:8770/captions-maker.html
```

Server murni stdlib Python (`http.server`) — tanpa Flask/dependensi web.

## Alur Pakai

1. Upload video berisi voiceover
2. Klik transkripsi → Whisper memproses (pertama kali mengunduh model, butuh internet sekali)
3. Review/edit caption per kata di panel
4. Atur font, warna, ukuran, posisi
5. Render → MP4 dengan caption burn-in

## Struktur File

```
captions_maker_server.py   # backend: server HTTP, transkripsi, render ffmpeg
captions-maker.html        # frontend web UI
captions_maker_ctk.py      # varian desktop (customtkinter)
index.html                 # redirect ke UI
requirements.txt           # dependensi Python
start_captions_maker.bat   # launcher web (Windows)
start_captions_maker.vbs   # helper: start server hidden + buka browser
start_captions_maker_ctk.bat  # launcher desktop
```

## Catatan

- Transkripsi dan rendering berjalan **lokal** — tidak ada data terkirim ke cloud
- Model Whisper di-cache lokal; ukuran model bisa ratusan MB (pilih model kecil seperti `small` untuk kecepatan)
- `caption_projects/`, `server.log`, `ai_settings.json` bersifat lokal dan tidak di-commit (lihat `.gitignore`)
