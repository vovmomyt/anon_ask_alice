import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
import os
from loguru import logger
import aiosqlite

class QuestionState(StatesGroup):
    waiting_for_question = State()

bot = Bot(token="7725790114:AAHKNSmlTerFoDfoRKIhy0z1vyVGuXvrOuE")
dp = Dispatcher(storage=MemoryStorage())

QUESTIONS_CHANNEL_ID = -1002073621043
LOGS_CHANNEL_ID = -1002455396764
DB_PATH = 'bot_database.db'

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY,
            banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        await db.commit()

async def ban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('INSERT OR REPLACE INTO banned_users (user_id) VALUES (?)', (user_id,))
        await db.commit()

async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT user_id FROM banned_users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone() is not None

async def is_user_in_channel(user_id: int) -> bool:
    member = await bot.get_chat_member(QUESTIONS_CHANNEL_ID, user_id)
    return member.status in ['member', 'administrator', 'creator']
#    return True
async def unban_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
        await db.commit()

async def log_to_channel(user: types.User, message_text: str, action: str, message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Открыть чат с пользователем", url=f"tg://user?id={user.id}")
    ], [
        InlineKeyboardButton(text="Забанить пользователя", callback_data=f"ban_{user.id}")
    ]])

    log_message = (
        f"👤 Пользователь: {user.full_name} (ID: {user.id})\n"
        f"Username: @{user.username}\n"
        f"Действие: {action}\n"
        f"Сообщение: {message_text}\n"
        f"Время: {message.date.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    await bot.send_message(
        chat_id=LOGS_CHANNEL_ID,
        text=log_message,
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data and c.data.startswith('ban_'))
async def process_ban_callback(callback: types.CallbackQuery):
    user_id = int(callback.data.split('_')[1])
    await ban_user(user_id)
    await callback.answer(text=f"Пользователь {user_id} забанен")
    await bot.send_message(LOGS_CHANNEL_ID, f"🚫 Пользователь {user_id} был забанен")

@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        await message.answer("Вы были заблокированы.")
        return
    if not await is_user_in_channel(message.from_user.id):
        await message.answer("Вы должны быть участником канала, чтобы задавать вопросы.")
        return
    await message.answer("👋 Привет! Здесь ты можешь задать свой анонимный вопрос. Просто напиши его в следующем сообщении.")
    await state.set_state(QuestionState.waiting_for_question)
    await log_to_channel(message.from_user, message.text, "Запустил бота", message)

@dp.message(QuestionState.waiting_for_question, F.text)
async def handle_question(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        await message.answer("Вы были заблокированы.")
        return
    if not await is_user_in_channel(message.from_user.id):
        await message.answer("Вы должны быть участником канала, чтобы задавать вопросы.")
        return
    if message.text.startswith("/start"):
        await message.reply("Задай вопрос!")
        return
    formatted_question = f"❓ Новый анонимный вопрос:\n\n<blockquote expandable>{message.text}</blockquote>"
    await bot.send_message(
        chat_id=QUESTIONS_CHANNEL_ID,
        text=formatted_question,
        parse_mode="HTML"
    )
    await log_to_channel(message.from_user, message.text, "Задал вопрос", message)
    await message.answer("✅ Спасибо! Твой вопрос отправлен. Ответ появится в канале.\n\nМожешь задать следующий вопрос!")

@dp.message(QuestionState.waiting_for_question, F.photo)
async def handle_photo(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        await message.answer("Вы были заблокированы.")
        return
    if not await is_user_in_channel(message.from_user.id):
        await message.answer("Вы должны быть участником канала, чтобы задавать вопросы.")
        return
    photo = message.photo[-1]
    caption = message.caption if message.caption else "Без подписи"

    await bot.send_photo(
        chat_id=QUESTIONS_CHANNEL_ID,
        photo=photo.file_id,
        caption=f"❓ Новый анонимный вопрос с фото:\n\n{caption}"
    )

    await log_to_channel(message.from_user, f"[Фото] {caption}", "Отправил фото", message)
    await message.answer("✅ Спасибо! Твое фото отправлено. Ответ появится в канале.\n\nМожешь задать следующий вопрос!")

@dp.message(QuestionState.waiting_for_question, F.voice)
async def handle_voice(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        await message.answer("Вы были заблокированы.")
        return
    if not await is_user_in_channel(message.from_user.id):
        await message.answer("Вы должны быть участником канала, чтобы задавать вопросы.")
        return
    await bot.send_voice(
        chat_id=QUESTIONS_CHANNEL_ID,
        voice=message.voice.file_id,
        caption="❓ Новый анонимный голосовой вопрос"
    )

    await log_to_channel(message.from_user, "[Голосовое сообщение]", "Отправил голосовое", message)
    await message.answer("✅ Спасибо! Твое голосовое сообщение отправлено. Ответ появится в канале.\n\nМожешь задать следующий вопрос!")

@dp.message(QuestionState.waiting_for_question, F.video_note)
async def handle_video_note(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        await message.answer("Вы были заблокированы.")
        return
    if not await is_user_in_channel(message.from_user.id):
        await message.answer("Вы должны быть участником канала, чтобы задавать вопросы.")
        return
    await bot.send_video_note(
        chat_id=QUESTIONS_CHANNEL_ID,
        video_note=message.video_note.file_id
    )

    await log_to_channel(message.from_user, "[Видеосообщение]", "Отправил видеосообщение", message)
    await message.answer("✅ Спасибо! Твое видеосообщение отправлено. Ответ появится в канале.\n\nМожешь задать следующий вопрос!")

@dp.message(QuestionState.waiting_for_question, F.sticker)
async def handle_sticker(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        await message.answer("Вы были заблокированы.")
        return
    if not await is_user_in_channel(message.from_user.id):
        await message.answer("Вы должны быть участником канала, чтобы задавать вопросы.")
        return
    await bot.send_sticker(
        chat_id=QUESTIONS_CHANNEL_ID,
        sticker=message.sticker.file_id
    )

    await log_to_channel(message.from_user, "[Стикер]", "Отправил стикер", message)
    await message.answer("✅ Спасибо! Твой стикер отправлен. Ответ появится в канале.\n\nМожешь задать следующий вопрос!")

@dp.message(QuestionState.waiting_for_question, F.video)
async def handle_video(message: types.Message, state: FSMContext):
    if await is_user_banned(message.from_user.id):
        await message.answer("Вы были заблокированы.")
        return
    if not await is_user_in_channel(message.from_user.id):
        await message.answer("Вы должны быть участником канала, чтобы задавать вопросы.")
        return
    caption = message.caption if message.caption else "Без подписи"

    await bot.send_video(
        chat_id=QUESTIONS_CHANNEL_ID,
        video=message.video.file_id,
        caption=f"❓ Новый анонимный вопрос с видео:\n\n{caption}"
    )

    await log_to_channel(message.from_user, f"[Видео] {caption}", "Отправил видео", message)
    await message.answer("✅ Спасибо! Твое видео отправлено. Ответ появится в канале.\n\nМожешь задать следующий вопрос!")

async def main():
    logger.info("Bot starting")
    await init_db()
    await bot.send_message(chat_id=LOGS_CHANNEL_ID, text="🚀 Бот запущен")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
