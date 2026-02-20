import os
import asyncio
import logging
import yt_dlp
import aiofiles
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
import tempfile
import time

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота (в Render добавим как переменную окружения)
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Проверка токена
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
        "Привет! Отправь мне название трека, и я скачаю его с YouTube в MP3.\n\n"
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
        ydl_opts = {
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
            # Ограничение размера (меньше 50 МБ для Telegram)
            'max_filesize': 45 * 1024 * 1024,  # 45 MB
        }
        
        try:
            # Показываем что ищем
            logging.info(f"Поиск: {query}")
            
            # Поиск и скачивание
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{query}", download=True)
                
                if not info or 'entries' not in info or not info['entries']:
                    return None, None, "❌ Ничего не найдено"
                
                video = info['entries'][0]
                title = video.get('title', 'Unknown')
                
                # Ждем завершения записи файла
                await asyncio.sleep(2)
                
                # Ищем скачанный MP3 файл
                for file in os.listdir(temp_dir):
                    if file.endswith('.mp3'):
                        file_path = os.path.join(temp_dir, file)
                        
                        # Проверяем размер
                        file_size = os.path.getsize(file_path)
                        if file_size > 50 * 1024 * 1024:  # 50 MB
                            return None, None, "❌ Файл слишком большой (больше 50 МБ)"
                        
                        # Читаем файл
                        async with aiofiles.open(file_path, 'rb') as f:
                            audio_data = await f.read()
                        
                        return audio_data, title, None
            
            return None, None, "❌ Не удалось найти MP3 файл"
            
        except Exception as e:
            logging.error(f"Ошибка: {e}")
            return None, None, f"❌ Ошибка: {str(e)[:100]}"

# Обработка текстовых сообщений (поиск музыки)
@dp.message(F.text & ~F.text.startswith('/'))
async def handle_text(message: Message):
    query = message.text.strip()
    
    if len(query) < 3:
        await message.reply("⚠️ Слишком короткий запрос. Введи хотя бы 3 символа.")
        return
    
    # Отправляем статус "печатает..."
    await bot.send_chat_action(message.chat.id, "typing")
    
    # Отправляем сообщение о начале поиска
    status_msg = await message.reply(f"🔍 Ищу: *{query}*...", parse_mode="Markdown")
    
    # Скачиваем
    audio_data, title, error = await download_audio(query)
    
    if error:
        await status_msg.edit_text(error)
        return
    
    if audio_data and title:
        # Обновляем статус
        await status_msg.edit_text(f"✅ Нашел: *{title}*\n📤 Отправляю...", parse_mode="Markdown")
        
        # Показываем "отправка аудио"
        await bot.send_chat_action(message.chat.id, "upload_audio")
        
        # Сохраняем во временный файл для отправки
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        try:
            # Отправляем аудио
            with open(tmp_path, 'rb') as audio:
                await message.reply_audio(
                    audio,
                    title=title[:100],  # Обрезаем если слишком длинное
                    performer="YouTube",
                    caption=f"🎵 {query}"
                )
            
            # Удаляем временный файл
            os.unlink(tmp_path)
            
            # Удаляем статусное сообщение
            await status_msg.delete()
            
        except Exception as e:
            logging.error(f"Ошибка отправки: {e}")
            await message.reply("❌ Ошибка при отправке файла. Попробуй другой трек.")
    else:
        await status_msg.edit_text("❌ Не удалось скачать трек. Попробуй другое название.")

# Запуск бота
async def main():
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())