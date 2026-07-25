database.py
import aiosqlite
import time
from config import COOLDOWN_SECONDS

DB_NAME = "bot_database.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        # Включаем WAL-режим для защиты от блокировок (database is locked) при высоких нагрузках
        await db.execute('PRAGMA journal_mode=WAL;')
        
        # Таблица пользователей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                first_name TEXT,
                username TEXT,
                is_blocked INTEGER DEFAULT 0,
                last_message_time REAL DEFAULT 0
            )
        ''')
        # Таблица настроек
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        # Таблица связи сообщений (id сообщения у владельца -> id отправителя)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS messages_map (
                owner_message_id INTEGER PRIMARY KEY,
                sender_user_id INTEGER
            )
        ''')
        
        # Устанавливаем режим анонимности по умолчанию (0 - анонимно, 1 - показывать)
        await db.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("show_senders", "0")')
        await db.commit()

async def add_user(user_id: int, first_name: str, username: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)',
            (user_id, first_name, username)
        )
        await db.commit()

async def check_spam(user_id: int) -> bool:
    """Возвращает True, если нужно заблокировать сообщение из-за спама"""
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT last_message_time FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                last_time = row[0]
                if time.time() - last_time < COOLDOWN_SECONDS:
                    return True
        # Обновляем время
        await db.execute('UPDATE users SET last_message_time = ? WHERE user_id = ?', (time.time(), user_id))
        await db.commit()
        return False

async def get_setting(key: str) -> str:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else "0"

async def set_setting(key: str, value: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE settings SET value = ? WHERE key = ?', (value, key))
        await db.commit()

async def save_message_map(owner_message_id: int, sender_user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'INSERT INTO messages_map (owner_message_id, sender_user_id) VALUES (?, ?)',
            (owner_message_id, sender_user_id)
        )
        await db.commit()

async def get_sender_by_message(owner_message_id: int) -> int:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT sender_user_id FROM messages_map WHERE owner_message_id = ?', (owner_message_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def is_user_blocked(user_id: int) -> bool:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT is_blocked FROM users WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            return bool(row[0]) if row else False

async def get_stats() -> tuple:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT COUNT(*) FROM users') as cursor1:
            total_users = (await cursor1.fetchone())[0]
        async with db.execute('SELECT COUNT(*) FROM messages_map') as cursor2:
            total_messages = (await cursor2.fetchone())[0]
        return total_users, total_messages

async def get_blocked_users() -> list:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT user_id, first_name FROM users WHERE is_blocked = 1') as cursor:
            return await cursor.fetchall()

async def block_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE users SET is_blocked = 1 WHERE user_id = ?', (user_id,))
        await db.commit()
