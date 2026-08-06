import os
import asyncio
import aiohttp
import requests
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_TOKEN = os.getenv("FUNSTAT_API_TOKEN")
BASE_URL = os.getenv("FUNSTAT_BASE_URL", "https://telelog.info/api/v1")

if not BOT_TOKEN or not API_TOKEN:
    raise RuntimeError("BOT_TOKEN и FUNSTAT_API_TOKEN обязательны")

HEADERS = {
    "accept": "text/plain",
    "Authorization": f"Bearer {API_TOKEN}"
}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ============================================================
# ФУНКЦИИ ИЗ ТВОЕГО СКРИПТА (адаптированные под асинхронность)
# ============================================================

def parse_date(ts):
    if not ts:
        return "неизвестно"
    try:
        if isinstance(ts, int):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        return dt.strftime("%d %b %y").lower()
    except:
        return str(ts)

async def api_get(endpoint, params=None):
    """Асинхронный GET с обработкой структуры {success, data}"""
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                # Обрабатываем обёртку как в твоём скрипте
                if isinstance(data, dict) and data.get('success'):
                    return data.get('data')
                return data
            return None

async def get_id_by_username(username):
    """Получить ID по username (как в твоём скрипте)"""
    username = username.replace('@', '').strip()
    data = await api_get("/users/resolve_username", {"username": username})
    if data:
        if isinstance(data, dict):
            return data.get('id')
        elif isinstance(data, list) and data:
            return data[0].get('id')
    return None

async def find_id_by_historical_username(username):
    """Поиск по историческому username"""
    username = username.replace('@', '').strip()
    data = await api_get("/users/username_usage", {"username": username})
    if data:
        users = data.get('active_users', []) or data.get('users', [])
        if users:
            return users[0].get('id')
    return None

async def get_user_id(identifier):
    """Комбинированный поиск ID"""
    identifier = str(identifier).strip()
    if identifier.isdigit():
        return identifier
    
    # Сначала пробуем resolve
    uid = await get_id_by_username(identifier)
    if uid:
        return uid
    
    # Потом исторический поиск
    uid = await find_id_by_historical_username(identifier)
    if uid:
        return uid
    
    return None

async def get_user_stats(user_id):
    """Получить stats, names, gifts с обработкой обёртки"""
    stats = await api_get(f"/users/{user_id}/stats")
    names = await api_get(f"/users/{user_id}/names")
    gifts = await api_get(f"/users/{user_id}/gifts_relation")
    return stats, names, gifts

# ============================================================
# ОБРАБОТЧИКИ КОМАНД
# ============================================================

@dp.message(Command("start"))
async def start_command(msg: Message):
    await msg.answer(
        "👋 Бот для поиска по FunStat API\n\n"
        "📌 Отправь @username или ID цифрами.\n"
        "Работает как твой скрипт, но в Telegram."
    )

@dp.message()
async def handle_user_query(msg: Message):
    text = msg.text.strip()
    
    # Получаем ID
    user_id = await get_user_id(text)
    if not user_id:
        await msg.answer(f"❌ Пользователь {text} не найден в FunStat.")
        return

    wait_msg = await msg.answer("⏳ Загружаю данные...")

    # Получаем данные
    stats, names, gifts = await get_user_stats(user_id)

    if not stats:
        await wait_msg.edit_text(
            f"❌ Не удалось получить данные по ID {user_id}.\n"
            f"Возможно, API вернул ошибку или недостаточно баланса."
        )
        return

    # ===== ФОРМИРУЕМ ОТВЕТ =====
    uid = stats.get("id", user_id)
    reg_ts = stats.get("registration_date")
    reg_str = parse_date(reg_ts) if reg_ts else "неизвестно"

    # История имён
    name_history = ""
    if names and isinstance(names, list):
        for item in names[:5]:
            fn = item.get("first_name", "")
            ln = item.get("last_name", "")
            full = f"{fn} {ln}".strip()
            date_str = parse_date(item.get("date"))
            name_history += f"├ {date_str} → {full}\n"
    if not name_history:
        name_history = "└ нет данных\n"

    # Подарки
    sent = "нет"
    received = "нет"
    if gifts and isinstance(gifts, dict):
        sent_list = gifts.get("sent", [])
        recv_list = gifts.get("received", [])
        if sent_list:
            sent = ", ".join(str(x) for x in sent_list[:5])
            if len(sent_list) > 5:
                sent += f" ... и ещё {len(sent_list)-5}"
        if recv_list:
            received = ", ".join(str(x) for x in recv_list[:5])
            if len(recv_list) > 5:
                received += f" ... и ещё {len(recv_list)-5}"

    cur_username = stats.get("username", "")
    cur_first = stats.get("first_name", "")
    cur_last = stats.get("last_name", "")
    cur_name = f"{cur_first} {cur_last}".strip()

    out = f"""🔎 Результат поиска по @{cur_username or uid}

👤 Аккаунт Telegram
├ ID: {uid}
├ Имя: {cur_name or "не указано"}
└ Регистрация: ~ {reg_str}

👤 История изменения имени ({len(names) if names else 0})
{name_history}

🎁 Кому отправлял(-а) подарки: {sent}
🎁 От кого получал(-а) подарки: {received}
"""

    await wait_msg.edit_text(out)

# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    print("🤖 Бот запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Вебхук удалён")
    print(f"📡 API: {BASE_URL}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
