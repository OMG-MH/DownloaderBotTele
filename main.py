import os
import re
import aiohttp
import asyncio
import traceback
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.error import RetryAfter

TOKEN = "1502748286:AAEY4cMa5f0vo9Dzp2fVbwjrBaQkRn4DJ24"

SUPPORTED_DIRECT_VIDEO_FORMATS = ('.mp4', '.mov', '.webm', '.avi', '.mkv')


async def download_m3u8(url, output_filename, update):
    cmd = ['ffmpeg', '-y', '-i', url, '-c', 'copy', output_filename]
    process = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    msg = await update.message.reply_text(
        "بدء تحميل فيديو HLS (m3u8)... 0 ميجابايت")
    last_edit_time = 0

    while True:
        line = await process.stderr.readline()
        if not line:
            break
        line = line.decode('utf-8').strip()
        if "size=" in line:
            try:
                size_match = re.search(r'size=\s*(\d+)(kB|M)?', line)
                if size_match:
                    size_value = int(size_match.group(1))
                    size_unit = size_match.group(2)
                    size_mb = size_value / 1024 if size_unit in (
                        None, 'kB') else size_value
                    now = asyncio.get_event_loop().time()
                    if now - last_edit_time > 1:
                        await msg.edit_text(
                            f"جاري تحميل الفيديو... {size_mb:.2f} ميجابايت")
                        last_edit_time = now
            except Exception:
                pass

    await process.wait()
    return process.returncode == 0


async def download_direct_video(url, output_filename, update):
    try:
        msg = await update.message.reply_text("جاري تحميل الفيديو المباشر...")
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await msg.edit_text("فشل تحميل الفيديو (الرابط غير متاح).")
                    return False

                total_size = int(resp.headers.get('Content-Length', 0))
                downloaded = 0
                last_update_time = asyncio.get_event_loop().time()

                with open(output_filename, 'wb') as f:
                    while True:
                        chunk = await resp.content.read(1024 * 512
                                                        )  # نصف ميجابايت
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        now = asyncio.get_event_loop().time()
                        if now - last_update_time > 1:
                            if total_size:
                                percent = downloaded / total_size * 100
                                mb = downloaded / (1024 * 1024)
                                await msg.edit_text(
                                    f"جاري التحميل: {mb:.2f} م.ب ({percent:.1f}%)"
                                )
                            else:
                                mb = downloaded / (1024 * 1024)
                                await msg.edit_text(
                                    f"جاري التحميل: {mb:.2f} م.ب")
                            last_update_time = now

        await asyncio.sleep(1)  # تأخير بسيط للتأكد من إنهاء الملف
        if os.path.getsize(output_filename) < 1024 * 100:
            await update.message.reply_text("الملف صغير جداً أو غير صالح.")
            return False
        return True
    except Exception as e:
        error_text = ''.join(traceback.format_exception_only(type(e), e))
        await update.message.reply_text(f"فشل تحميل الفيديو:\n{error_text}")
        return False


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    await update.message.reply_text(f"جاري معالجة الرابط:\n{url}")

    output_file = "output_video.mp4"
    success = False

    if ".m3u8" in url:
        success = await download_m3u8(url, output_file, update)
    elif url.lower().endswith(SUPPORTED_DIRECT_VIDEO_FORMATS):
        success = await download_direct_video(url, output_file, update)
    else:
        await update.message.reply_text(
            "الرابط غير مدعوم. يرجى إرسال رابط m3u8 أو mp4 أو صيغ فيديو معروفة."
        )
        return

    if not success:
        return

    # إرسال الفيديو كما هو
    try:
        with open(output_file, 'rb') as video:
            await update.message.reply_video(video,
                                             filename=output_file,
                                             supports_streaming=True)
    except RetryAfter as e:
        await update.message.reply_text(
            f"تم حظرك مؤقتًا، الرجاء الانتظار {e.retry_after} ثانية.")
        await asyncio.sleep(int(e.retry_after) + 1)
        with open(output_file, 'rb') as video:
            await update.message.reply_video(video,
                                             filename=output_file,
                                             supports_streaming=True)
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء إرسال الفيديو: {e}")

    # حذف الملف بعد الإرسال
    if os.path.exists(output_file):
        os.remove(output_file)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحباً! أرسل لي رابط فيديو بصيغة m3u8 أو mp4 أو صيغة فيديو مباشرة وسأقوم بتحميله لك وإرساله بدون تقسيم."
    )


if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), handle_link))
    app.run_polling()
