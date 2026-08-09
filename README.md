# Bot Telegram Pemotong Klip YouTube

Bot ini menerima link video YouTube dari pengguna, lalu memotong bagian
tertentu dari video tersebut (berdasarkan waktu mulai & selesai) dan
mengirimkannya kembali sebagai video klip.

## Cara Kerja
1. Pengguna kirim `/start`.
2. Bot minta link YouTube.
3. Bot minta rentang waktu, format: `start end` (contoh: `00:00:10 00:00:40`).
4. Bot mengunduh **hanya bagian tersebut** (pakai fitur `download_ranges` dari
   yt-dlp, jadi tidak perlu download seluruh video), lalu mengirimkannya
   sebagai video.

## Persyaratan
- Python 3.9+
- **ffmpeg** harus terinstal di sistem (dipakai yt-dlp untuk memotong & merge video)
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Windows: unduh dari https://ffmpeg.org/download.html dan tambahkan ke PATH
- Token bot Telegram dari [@BotFather](https://t.me/BotFather)

## Instalasi

```bash
# 1. Buat virtual environment (opsional tapi disarankan)
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 2. Install dependensi
pip install -r requirements.txt

# 3. Set token bot
export BOT_TOKEN="isi-token-dari-botfather"   # Windows (PowerShell): $env:BOT_TOKEN="..."

# 4. Jalankan bot
python bot.py
```

## Batasan Penting
- **Durasi klip maksimal**: 3 menit (bisa diubah lewat variabel `MAX_DURATION_SECONDS` di `bot.py`).
- **Ukuran file maksimal**: ~49MB, karena ini batas resmi upload file oleh Bot API Telegram
  (bukan batas dari kode ini). Untuk file lebih besar, Telegram mensyaratkan
  penggunaan local Bot API server sendiri (di luar cakupan bot ini).
- Bot ini hanya mengunduh video yang memang bisa diakses publik oleh yt-dlp
  (tidak untuk video privat/berbayar/dibatasi umur tanpa login).
- Menghormati Ketentuan Layanan YouTube adalah tanggung jawab pengguna bot ini —
  gunakan hanya untuk konten yang memang boleh diunduh/diklip (video sendiri,
  domain publik, berlisensi terbuka, dsb).

## Menjalankan terus-menerus (opsional)
Untuk produksi, jalankan lewat process manager seperti `systemd`, `pm2`, atau
`supervisor` agar bot otomatis restart jika crash, dan pertimbangkan menambahkan
rate-limiting per user agar server tidak kelebihan beban.

## Struktur File
```
telegram-youtube-clipper/
├── bot.py              # kode utama bot
├── requirements.txt    # dependensi Python
└── README.md           # panduan ini
```
