# JIN ASGHARD

Asisten pribadi laptop. Tampilan terminal hijau, ada karakter jin di tengah.
Tanpa API key. Semua jalan di laptop kamu.

- Ketik atau bicara lewat mic
- Jin menjawab dengan teks dan suara
- Bukan bagian dari project pajak

## Yang dipakai

- Otak: Ollama (`qwen2.5:7b`) — lebih pintar, lokal
- Memori: embedding lokal (`nomic-embed-text`) — catatan + fakta + obrolan
- Dengar: Whisper `tiny` — lokal
- Bicara: `edge-tts` suara Indonesia dalam/serem
- Chat + memori: SQLite di folder `data`

## Cara jalankan

1. Install [Ollama](https://ollama.com/download).
2. Double-click `start.bat`.
   - Pertama kali akan unduh `qwen2.5:7b` (sekitar 4–5 GB).
   - Lalu aplikasi Jin terbuka.

Atau manual:

```bat
ollama pull qwen2.5:7b
cd /d D:\jin-asisten
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Cara pakai

- Ketik di kotak bawah, lalu Enter / **KIRIM**.
- Klik gambar jin, atau tekan **MIC**, bicara, lalu **STOP**.
- Bilang **Jin** (atau **Asghard**) untuk memanggil jendela + mulai dengar.
  - Bisa langsung: *“Jin buka vs code”*.
- Klik kanan pada jin untuk **radar** harian.
- Sakelar **SUARA** harus nyala agar Jin bicara terus.

Contoh perintah:

- `radar`
- `ingat: bos Rehan kerja di Jambi`
- `baca layar`
- `volume naik`
- `mode serius`
- `tempel Halo dari Jin Asghard`
- `kunci laptop`
- `fokus`  /  `pulang`
- `ringkas`  (PDF, Word, atau halaman yang sedang dibuka)
- Copy teks di mana saja, lalu jawab `ringkas` / `terjemah` / `catat`
- `buka vs code`
- `buat folder web-app di vscode`
- `install library requests flask`
- `pip install numpy`  /  `npm install express`
- `ingat: proyek pajak Jambi`
- `proyek yang kemarin?`  /  `ingat soal proyek`
- `apa yang kamu ingat tentang Jambi`
- `lanjut kemarin`  /  `lanjut coding`  /  `kerja`
- `lanjut project namafolder`
- `daftar project`
- `ringkas commit`  /  `draft commit`
- `commit`  (pesan auto dari ringkasan diff)
- `commit dan push`
- `commit pesan: perbaiki bug login`
- `push`

Data chat: `D:\jin-asisten\data\jin.db`
