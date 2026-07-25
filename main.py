import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.exceptions import TelegramAPIError

import config
import database

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# Состояния для FSM (ожидание ответа от владельца)
class ReplyState(StatesGroup):
    waiting_for_reply = State()

# --- КЛАВИАТУРЫ ---
def get_admin_keyboard(show_senders_status: str) -> InlineKeyboardMarkup:
    toggle_text = "🔒 Скрыть отправителей" if show_senders_status == "1" else "🔓 Показать отправителей"
    toggle_callback = "admin_hide_senders" if show_senders_status == "1" else "admin_show_senders"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_text, callback_data=toggle_callback)],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🚫 Заблокированные пользователи", callback_data="admin_blocked")]
    ])
    return keyboard

def get_reply_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data="action_reply")],
        [InlineKeyboardButton(text="🚫 Заблокировать", callback_data="action_block")]
    ])

def get_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="action_cancel")]
    ])

# --- ОБРАБОТЧИКИ КОМАНД ---
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await database.add_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
    
    if message.from_user.id == config.OWNER_ID:
        await message.answer("👋 Привет, владелец! Бот работает. Используй /admin для настроек.")
    else:
        await message.answer("👋 Привет! Напиши сюда любое сообщение (текст, фото, видео, голосовое), и я анонимно передам его владельцу бота.")

@dp.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id != config.OWNER_ID:
        return
    
    show_status = await database.get_setting("show_senders")
    await message.answer("⚙️ Админ-панель:", reply_markup=get_admin_keyboard(show_status))

# --- ОБРАБОТЧИКИ АДМИН-ПАНЕЛИ (CALLBACK) ---
@dp.callback_query(F.data.startswith("admin_"))
async def admin_callbacks(call: CallbackQuery):
    if call.from_user.id != config.OWNER_ID:
        await call.answer("Нет доступа", show_alert=True)
        return

    if call.data == "admin_show_senders":
        await database.set_setting("show_senders", "1")
        await call.message.edit_text("⚙️ Админ-панель:\n\n✅ Режим деанонимизации ВКЛЮЧЕН.", reply_markup=get_admin_keyboard("1"))
        await call.answer()
        
    elif call.data == "admin_hide_senders":
        await database.set_setting("show_senders", "0")
        await call.message.edit_text("⚙️ Админ-панель:\n\n✅ Анонимный режим ВКЛЮЧЕН.", reply_markup=get_admin_keyboard("0"))
        await call.answer()
        
    elif call.data == "admin_stats":
        users, messages = await database.get_stats()
        text = f"📊 Статистика:\n\nПользователей: {users}\nСообщений переслано: {messages}"
        await call.answer(text, show_alert=True)
        
    elif call.data == "admin_blocked":
        blocked = await database.get_blocked_users()
        if not blocked:
            await call.answer("Заблокированных пользователей нет.", show_alert=True)
        else:
            text = "🚫 Заблокированные:\n\n" + "\n".join([f"{name} (ID: {uid})" for uid, name in blocked])
            await call.answer(text, show_alert=True)

# --- ЛОГИКА ОТВЕТОВ ВЛАДЕЛЬЦА ---
@dp.callback_query(F.data == "action_reply")
async def process_reply_button(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != config.OWNER_ID:
        return
    
    sender_id = await database.get_sender_by_message(call.message.message_id)
    if not sender_id:
        await call.answer("Ошибка: Пользователь не найден в базе.", show_alert=True)
        return
        
    await state.update_data(target_user_id=sender_id)
    await state.set_state(ReplyState.waiting_for_reply)
    await call.message.reply("✍️ Отправьте ответное сообщение. Оно будет доставлено пользователю:", reply_markup=get_cancel_keyboard())
    await call.answer()

@dp.callback_query(F.data == "action_block")
async def process_block_button(call: CallbackQuery):
    if call.from_user.id != config.OWNER_ID:
        return
    
    sender_id = await database.get_sender_by_message(call.message.message_id)
    if not sender_id:
        await call.answer("Ошибка связи с базой.", show_alert=True)
        return
        
    await database.block_user(sender_id)
    await call.answer("✅ Пользователь заблокирован.", show_alert=True)

@dp.callback_query(F.data == "action_cancel", ReplyState.waiting_for_reply)
async def cancel_reply(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Ответ отменен.")
    await call.answer()

@dp.message(ReplyState.waiting_for_reply)
async def send_reply_to_user(message: Message, state: FSMContext):
    if message.from_user.id != config.OWNER_ID:
        return
        
    data = await state.get_data()
    target_user_id = data.get("target_user_id")
    
    try:
        await message.copy_to(chat_id=target_user_id)
        await message.reply("✅ Ответ успешно отправлен!")
    except TelegramAPIError:
        await message.reply("❌ Ошибка отправки. Возможно, пользователь заблокировал бота.")
    finally:
        await state.clear()

# --- ОСНОВНАЯ ЛОГИКА (ПРИЕМ СООБЩЕНИЙ) ---
@dp.message(F.text != "/start")
async def handle_all_messages(message: Message, state: FSMContext):
    # Игнорируем владельца, если он не в состоянии ответа (чтобы он сам себе не отправлял анонимки)
    if message.from_user.id == config.OWNER_ID:
        return

    user_id = message.from_user.id
    
    # Добавляем в базу, если еще нет
    await database.add_user(user_id, message.from_user.first_name, message.from_user.username)
    
    # Проверка на блокировку
    is_blocked = await database.is_user_blocked(user_id)
    if is_blocked:
        return
        
    # Проверка на спам
    is_spam = await database.check_spam(user_id)
    if is_spam:
        await message.answer(f"⏳ Пожалуйста, подождите {config.COOLDOWN_SECONDS} секунд перед отправкой следующего сообщения.")
        return

    # Отправляем уведомление пользователю
    msg_to_user = await message.answer("✅ Сообщение доставлено!")

    # Проверяем настройки анонимности
    show_senders = await database.get_setting("show_senders")
    
    if show_senders == "1":
        username_text = f"@{message.from_user.username}" if message.from_user.username else "Нет"
        header_text = f"📩 Новое сообщение:\n\n👤 Отправитель:\nИмя: {message.from_user.first_name}\nUsername: {username_text}\nID: {user_id}"
    else:
        header_text = "📩 Новое анонимное сообщение:"
        
    # Отправка владельцу с перехватом ошибок (если владелец случайно заблокировал своего бота)
    try:
        # Отправляем заголовок владельцу
        await bot.send_message(chat_id=config.OWNER_ID, text=header_text)
        
        # Копируем само сообщение владельцу с сохранением формата и кнопками
        copied_msg = await message.copy_to(
            chat_id=config.OWNER_ID,
            reply_markup=get_reply_keyboard()
        )
        # Сохраняем в БД связь: ID сообщения у владельца -> ID отправителя
        await database.save_message_map(copied_msg.message_id, user_id)
        
    except TelegramAPIError as e:
        logging.error(f"Failed to forward message: {e}")
        # Если не получилось доставить владельцу, уведомляем пользователя, что сообщение не ушло
        try:
            await msg_to_user.edit_text("❌ Произошла ошибка на стороне сервера при доставке сообщения.")
        except TelegramAPIError:
            pass

# --- ЗАПУСК ---
async def main():
    await database.init_db()
    logging.info("Bot is starting...")
    # Удаляем вебхуки, чтобы polling работал корректно
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
