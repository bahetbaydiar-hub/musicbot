import os
import asyncio
import logging
import yt_dlp
import aiofiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
import tempfile

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Нет токена! Добавь BOT_TOKEN в переменные окружения")

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply(
        "🎵 **Music Bot**\n\n"
        "Отправь мне название трека, и я скачаю его с YouTube в MP3.\n\n"
        "Пример: `Imagine Dragons - Believer`\n"
        "Пример: `Daft Punk - Get Lucky`\n\n"
        "⚡️ Работает 24/7, полностью бесплатно!",
        parse_mode="Markdown"
    )

# Команда /help
@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.reply(
        "📖 **Как пользоваться:**\n\n"
        "1. Отправь название трека и исполнителя\n"
        "2. Подожди немного (идет поиск и скачивание)\n"
        "3. Получи MP3 файл\n\n"
        "⚠️ **Ограничения:**\n"
        "• Файл не больше 50 МБ (примерно 10-15 минут музыки)\n"
        "• Качество: 192 kbps MP3\n\n"
        "🔍 **Примеры запросов:**\n"
        "• `The Weeknd - Blinding Lights`\n"
        "• `Linkin Park - In The End`\n"
        "• `Miyagi - Тамада`",
        parse_mode="Markdown"
    )

async def download_audio(query: str):
    """
    Скачивает аудио с YouTube по запросу
    Возвращает: (audio_data, title, error_message)
    """
    # Создаем временную папку для этого скачивания
    with tempfile.TemporaryDirectory() as temp_dir:
        # Улучшенные настройки yt-dlp
        ydl_opts = {
            # Пробуем разные форматы в порядке приоритета
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            'default_search': 'ytsearch1',
            'source_address': '0.0.0.0',
            'max_filesize': 45 * 1024 * 1024,
            # Важные параметры для стабильности
            'ignoreerrors': True,
            'nooverwrites': True,
            'continuedl': True,
            'noplaylist': True,
            'extract_flat': False,
            'retries': 10,
            'fragment_retries': 10,
            'skip_unavailable_fragments': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        # Добавляем cookies если файл существует
        cookies_path = 'cookies.txt'
        if os.path.exists(cookies_path):
            ydl_opts['cookiefile'] = cookies_path
            logging.info("Using cookies file for authentication")
        else:
            logging.warning("No cookies file found, continuing without authentication")
        
        try:
            logging.info(f"Поиск: {query}")
            
            # Поиск информации о видео
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(f"ytsearch1:{query}", download=False)
                
                if not info_dict or 'entries' not in info_dict or not info_dict['entries']:
                    return None, None, "❌ Ничего не найдено по запросу"
                
                video_info = info_dict['entries'][0]
                title = video_info.get('title', 'Unknown')
                
                # Проверки доступности
                if video_info.get('availability') == 'private':
                    return None, None, "❌ Это видео недоступно (приватное)"
                
                if video_info.get('live_status') == 'is_live':
                    return None, None, "❌ Это прямой эфир, скачивание недоступно"
                
                duration = video_info.get('duration', 0)
                if duration > 900:
                    return None, None, "❌ Видео слишком длинное (больше 15 минут)"
                
                logging.info(f"Найдено видео: {title}")
                
                # Скачиваем видео
                ydl.download([video_info['webpage_url']])
                
                # Ждем завершения конвертации
                await asyncio.sleep(5)
                
                # Ищем скачанные файлы
                files = os.listdir(temp_dir)
                logging.info(f"Файлы в папке: {files}")
                
                # Сначала ищем MP3 файлы
                mp3_files = [f for f in files if f.endswith('.mp3')]
                
                if mp3_files:
                    # Берем первый MP3 файл
                    file_name = mp3_files[0]
                    file_path = os.path.join(temp_dir, file_name)
                    file_size = os.path.getsize(file_path)
                    
                    if file_size < 1024:
                        return None, None, "❌ Файл слишком маленький (менее 1 КБ)"
                    
                    async with aiofiles.open(file_path, 'rb') as f:
                        audio_data = await f.read()
                    
                    logging.info(f"Успешно скачано: {title} ({file_size} bytes)")
                    return audio_data, title, None
                
                # Если MP3 не найден, ищем другие аудиофайлы
                audio_extensions = ['.m4a', '.webm', '.ogg', '.aac', '.wav']
                for ext in audio_extensions:
                    audio_files = [f for f in files if f.endswith(ext)]
                    if audio_files:
                        file_name = audio_files[0]
                        file_path = os.path.join(temp_dir, file_name)
                        file_size = os.path.getsize(file_path)
                        
                        if file_size < 1024:
                            continue
                        
                        # Пробуем сконвертировать в MP3 через FFmpeg
                        mp3_path = os.path.join(temp_dir, f"{os.path.splitext(file_name)[0]}.mp3")
                        
                        import subprocess
                        try:
                            subprocess.run([
                                'ffmpeg', '-i', file_path, 
                                '-codec:a', 'libmp3lame', 
                                '-qscale:a', '2', 
                                mp3_path
                            ], check=True, capture_output=True)
                            
                            if os.path.exists(mp3_path) and os.path.getsize(mp3_path) > 1024:
                                async with aiofiles.open(mp3_path, 'rb') as f:
                                    audio_data = await f.read()
                                return audio_data, title, None
                        except Exception as e:
                            logging.error(f"Ошибка конвертации: {e}")
                
                return None, None, "❌ Не удалось создать MP3 файл"
                
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Ошибка скачивания: {error_msg}")
            
            if "Sign in to confirm you're not a bot" in error_msg:
                return None, None, "❌ YouTube требует подтверждения. Проверьте cookies"
            elif "Video unavailable" in error_msg:
                return None, None, "❌ Видео недоступно"
            elif "ffmpeg" in error_msg.lower():
                return None, None, "❌ Ошибка конвертации. Попробуйте другой трек"
            else:
                return None, None, f"❌ Ошибка: {error_msg[:200]}"

# Обработка текстовых сообщений
@dp.message(F.text & ~F.text.startswith('/'))
async def handle_text(message: Message):
    query = message.text.strip()
    
    if len(query) < 3:
        await message.reply("⚠️ Слишком короткий запрос. Введи хотя бы 3 символа.")
        return
    
    await bot.send_chat_action(message.chat.id, "typing")
    status_msg = await message.reply(f"🔍 Ищу: *{query}*...", parse_mode="Markdown")
    
    audio_data, title, error = await download_audio(query)
    
    if error:
        await status_msg.edit_text(error)
        return
    
    if audio_data and title:
        await status_msg.edit_text(f"✅ Нашел: *{title}*\n📤 Отправляю...", parse_mode="Markdown")
        await bot.send_chat_action(message.chat.id, "upload_audio")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        try:
            with open(tmp_path, 'rb') as audio:
                await message.reply_audio(
                    audio,
                    title=title[:100],
                    performer="YouTube",
                    caption=f"🎵 {query}"
                )
            
            os.unlink(tmp_path)
            await status_msg.delete()
            await asyncio.sleep(5)
            
        except Exception as e:
            logging.error(f"Ошибка отправки: {e}")
            await message.reply("❌ Ошибка при отправке файла. Попробуй другой трек.")
    else:
        await status_msg.edit_text("❌ Не удалось скачать трек. Попробуй другое название.")

async def main():
    logging.info("Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
