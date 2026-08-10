import os
import re
import asyncio
import logging
import tempfile

from telegram import Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters
)
import yt_dlp

MAX_SEND_RETRIES = 3  # jumlah percobaan ulang kalau koneksi sempat putus


async def send_with_retry(coro_func, *args, **kwargs):
    """Jalankan fungsi kirim pesan/video, otomatis coba ulang kalau koneksi bermasalah."""
    last_error = None
    for attempt in range(1, MAX_SEND_RETRIES + 1):
        try:
            return await coro_func(*args, **kwargs)
        except (NetworkError, TimedOut) as e:
            last_error = e
            logger.warning(f"Percobaan kirim ke-{attempt} gagal: {e}. Mencoba lagi...")
            await asyncio.sleep(2 * attempt)
    raise last_error

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
COOKIES_B64 = os.getenv("YOUTUBE_COOKIES_B64")  # cookies YouTube (base64), opsional tapi disarankan untuk hosting cloud
MAX_DURATION_SECONDS = 180   # durasi klip maksimal (3 menit)
MAX_FILE_SIZE_MB = 49        # batas upload bot Telegram (~50MB)

LINK, TIME_RANGE = range(2)

YOUTUBE_REGEX = re.compile(
    r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)[\w-]+'
)

COOKIES_FILE_PATH = "/tmp/youtube_cookies.txt"


def setup_cookies_file():
    """Tulis file cookies.txt dari env var (base64) kalau tersedia. Return path atau None."""
    if not COOKIES_B64:
        return None
    try:
        import base64
        decoded = base64.b64decode(COOKIES_B64)
        with open(COOKIES_FILE_PATH, "wb") as f:
            f.write(decoded)
        logger.info("File cookies YouTube berhasil disiapkan.")
        return COOKIES_FILE_PATH
    except Exception as e:
        logger.warning(f"Gagal menyiapkan cookies: {e}")
        return None


def parse_time_to_seconds(t: str) -> int:
    """Ubah format waktu 'HH:MM:SS' / 'MM:SS' / 'SS' menjadi total detik."""
    parts = [int(p) for p in t.strip().split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Kirimkan link video YouTube yang ingin kamu potong.\n\n"
        "Gunakan /cancel untuk membatalkan kapan saja."
    )
    return LINK


async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not YOUTUBE_REGEX.search(text):
        await update.message.reply_text(
            "Itu bukan link YouTube yang valid. Coba kirim ulang link-nya."
        )
        return LINK

    context.user_data["url"] = text
    await update.message.reply_text(
        "Link diterima ✅\n\n"
        "Sekarang kirim rentang waktu klip dengan format:\n"
        "`start end`\n\n"
        "Contoh: `00:00:10 00:00:40`\n"
        f"(durasi klip maksimal {MAX_DURATION_SECONDS // 60} menit)",
        parse_mode="Markdown"
    )
    return TIME_RANGE


async def receive_time_range(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        start_str, end_str = text.split()
        start_sec = parse_time_to_seconds(start_str)
        end_sec = parse_time_to_seconds(end_str)
    except Exception:
        await update.message.reply_text(
            "Format salah. Kirim dalam format `start end`, contoh: `00:00:10 00:00:40`",
            parse_mode="Markdown"
        )
        return TIME_RANGE

    if end_sec <= start_sec:
        await update.message.reply_text("Waktu akhir harus lebih besar dari waktu awal. Coba lagi.")
        return TIME_RANGE

    duration = end_sec - start_sec
    if duration > MAX_DURATION_SECONDS:
        await update.message.reply_text(
            f"Durasi klip maksimal {MAX_DURATION_SECONDS // 60} menit. "
            "Coba rentang waktu yang lebih pendek."
        )
        return TIME_RANGE

    url = context.user_data["url"]
    status_msg = await send_with_retry(
        update.message.reply_text, "⏳ Sedang memproses video, mohon tunggu..."
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_template = os.path.join(tmp_dir, "clip.%(ext)s")

        def section_selector(info_dict, ydl_instance):
            return [{"start_time": start_sec, "end_time": end_sec}]

        ydl_opts = {
            "format": "bestvideo[ext=mp4][filesize<50M]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": output_template,
            "download_ranges": section_selector,
            "force_keyframes_at_cuts": True,
            "quiet": False,
            "no_warnings": False,
            "verbose": True,
            "merge_output_format": "mp4",
            "extractor_args": {
                "youtube": {
                    "player_client": ["android_vr"],
                },
                "youtubepot-bgutilhttp": {
                    "base_url": ["http://bgutil-ytdlp-pot-provider.railway.internal:4416"]
                }
            },
        }
        cookies_path = setup_cookies_file()
        if cookies_path:
            ydl_opts["cookiefile"] = cookies_path

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except Exception as e:
            logger.exception("Download gagal")
            await status_msg.edit_text(f"❌ Gagal memproses video: {e}")
            return ConversationHandler.END

        clip_path = None
        for fname in os.listdir(tmp_dir):
            if fname.startswith("clip."):
                clip_path = os.path.join(tmp_dir, fname)
                break

        if not clip_path or not os.path.exists(clip_path):
            await status_msg.edit_text("❌ Gagal membuat klip. File tidak ditemukan.")
            return ConversationHandler.END

        size_mb = os.path.getsize(clip_path) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            await status_msg.edit_text(
                f"❌ Ukuran klip ({size_mb:.1f}MB) melebihi batas kirim Telegram bot "
                f"({MAX_FILE_SIZE_MB}MB). Coba persingkat durasi klip."
            )
            return ConversationHandler.END

        try:
            await send_with_retry(status_msg.edit_text, "📤 Mengirim video...")
            with open(clip_path, "rb") as video_file:
                await send_with_retry(
                    update.message.reply_video,
                    video=video_file,
                    caption=f"Klip {start_str} - {end_str}"
                )
            await status_msg.delete()
        except (NetworkError, TimedOut) as e:
            logger.exception("Gagal mengirim setelah beberapa percobaan")
            try:
                await status_msg.edit_text(
                    "❌ Koneksi internet tidak stabil, gagal mengirim video. "
                    "Coba lagi ya."
                )
            except Exception:
                pass

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Dibatalkan.")
    context.user_data.clear()
    return ConversationHandler.END


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN belum diset. Set environment variable BOT_TOKEN terlebih dahulu.")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(60)
        .pool_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(30)
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_link)],
            TIME_RANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time_range)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    logger.info("Bot berjalan...")
    application.run_polling()


if __name__ == "__main__":
    main()
