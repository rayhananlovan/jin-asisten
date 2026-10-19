<p align="center">
  <img src="assets/jin-idle.png" width="180" alt="Jin Asghard">
</p>

<h1 align="center">Jin Asghard</h1>

<p align="center">
  Asisten laptop lokal untuk Windows. Chat, suara, dan perintah kerja jalan di mesin sendiri, tanpa API key.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/ollama-local-111111" alt="Ollama">
  <img src="https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white" alt="Windows">
</p>

Jin Asghard adalah aplikasi desktop bertema terminal hijau. Karakter jin di tengah jendela berubah saat mendengar, berpikir, dan berbicara. Model bahasa, memori, dan pengenalan suara semuanya lokal.

## Fitur

- Chat teks, atau bicara lewat mikrofon. Jawaban bisa dibacakan.
- Wake word `Jin` atau `Asghard` untuk membuka jendela dan mulai mendengar.
- Memori semantik untuk catatan, fakta, dan obrolan lama.
- Baca layar, clipboard, PDF, Word, dan file teks.
- Catatan, pengingat, pencarian web, volume, dan kunci laptop.
- Buka VS Code, lanjutkan project kemarin, pasang library, lalu draft commit.

## Stack

| Bagian | Teknologi |
| --- | --- |
| Antarmuka | CustomTkinter |
| Model bahasa | Ollama `qwen2.5:7b` |
| Memori | SQLite + `nomic-embed-text` |
| Dengar | Whisper `tiny` |
| Bicara | edge-tts, suara Indonesia |
| Baca layar | Windows OCR |

## Menjalankan

1. Pasang [Ollama](https://ollama.com/download) dan pastikan `ollama` ada di PATH.
2. Pasang Python 3.11 atau lebih baru.
3. Double-click `start.bat`.

Pertama kali, skrip mengunduh model (sekitar 4–5 GB), membuat virtual environment, memasang dependensi, lalu membuka aplikasi.

Manual:

```bat
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python main.py
```

## Cara pakai

Ketik di kotak bawah lalu Enter, atau klik jin / tombol **MIC**. Sakelar **SUARA** harus nyala agar Jin berbicara. Klik kanan pada jin membuka radar harian.

```text
Jin buka vs code
radar
ingat: proyek portofolio pakai React
baca layar
cari file catatan
ringkas
buka vs code
lanjut kemarin
daftar project
draft commit
commit dan push
```

## Konfigurasi

Salin `.env.example` menjadi `.env`. File itu tidak ikut di-commit.

| Variabel | Fungsi |
| --- | --- |
| `OLLAMA_MODEL` | Model chat lokal |
| `JIN_EMBED_MODEL` | Model memori semantik |
| `WHISPER_MODEL` | Model pengenalan suara |
| `OWNER_NAME` / `OWNER_CALL` | Nama dan sapaan pemilik |
| `JIN_VOICE` | Suara edge-tts |
| `JIN_WAKE_WORDS` | Kata pemanggil, dipisah koma |
| `JIN_PROJECTS_DIR` | Folder project yang dipindai |

## Privasi

Obrolan, catatan, dan embedding tersimpan di `data/jin.db` pada laptop. Folder `data/`, `.venv/`, dan `.env` diabaikan git.
