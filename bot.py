import os
import asyncio
import aiohttp
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
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data

# ============================================================
# ТОЧНО КАК В ТВОЁМ СКРИПТЕ
# ============================================================

async def get_id_by_username(username):
    username = username.replace('@', '').strip()
    data = await api_get("/users/resolve_username", {"req": username})
    if data and isinstance(data, dict):
        return data.get('id')
    return None

async def find_id_by_historical_username(username):
    username = username.replace('@', '').strip()
    data = await api_get("/users/username_usage", {"username": username})
    if data:
        users = data.get('active_users', []) or data.get('users', [])
        if users:
            return users[0].get('id')
    return None

async def get_user_id(identifier):
    identifier = str(identifier).strip()
    if identifier.isdigit():
        return identifier
    uid = await get_id_by_username(identifier)
    if uid:
        return uid
    uid = await find_id_by_historical_username(identifier)
    if uid:
        return uid
    return None

async def get_user_names(user_id):
    """История имён"""
    data = await api_get(f"/users/{user_id}/names")
    if data and isinstance(data, list):
        return data
    return []

async def get_user_gifts(user_id):
    """Подарки (отправленные и полученные)"""
    data = await api_get(f"/users/{user_id}/gifts_relation")
    if data and isinstance(data, dict):
        return data
    return {}

async def get_user_stats_min(user_id):
    """Базовая статистика (бесплатно)"""
    return await api_get(f"/users/{user_id}/stats_min")

# ============================================================
# ОБРАБОТЧИКИ
# ============================================================

@dp.message(Command("start"))
async def start_command(msg: Message):
    await msg.answer(
        "👋 Бот для FunStat API\n\n"
        "📌 Отправь @username или ID цифрами.\n"
        "Показывает полную информацию: статистику, историю имён и подарки."
    )

@dp.message()
async def handle_user_query(msg: Message):
    text = msg.text.strip()
    
    # Получаем ID
    user_id = await get_user_id(text)
    if not user_id:
        await msg.answer(f"❌ Пользователь {text} не найден.")
        return

    wait_msg = await msg.answer("⏳ Загружаю данные...")

    # Получаем все данные
    stats = await get_user_stats_min(user_id)
    names = await get_user_names(user_id)
    gifts = await get_user_gifts(user_id)

    if not stats:
        await wait_msg.edit_text(
            f"❌ Не удалось получить данные по ID {user_id}.\n"
            f"Проверь баланс или попробуй позже."
        )
        return

    # ===== ФОРМИРУЕМ ОТВЕТ (КАК В ТВОЁМ СКРИПТЕ) =====
    uid = stats.get("id", user_id)
    
    # Регистрация
    first_msg = stats.get("first_msg_date")
    reg_str = parse_date(first_msg) if first_msg else "неизвестно"
    
    # Текущее имя
    first_name = stats.get("first_name", "")
    last_name = stats.get("last_name", "")
    cur_name = f"{first_name} {last_name}".strip() or "не указано"
    
    # Статистика
    total_msgs = stats.get("total_msg_count", 0)
    total_groups = stats.get("total_groups", 0)
    names_count = stats.get("names_count", 0)
    usernames_count = stats.get("usernames_count", 0)
    is_bot = "🤖 Бот" if stats.get("is_bot") else "👤 Человек"
    is_active = "🟢 Активен" if stats.get("is_active") else "🔴 Неактивен"

    # ===== ИСТОРИЯ ИМЁН =====
    name_history = ""
    if names and isinstance(names, list):
        for item in names[:10]:  # показываем последние 10
            fn = item.get("first_name", "")
            ln = item.get("last_name", "")
            full = f"{fn} {ln}".strip()
            date_str = parse_date(item.get("date"))
            name_history += f"├ {date_str} → {full}\n"
    if not name_history:
        name_history = "└ нет данных\n"

    # ===== ПОДАРКИ =====
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

    # ===== ФИНАЛЬНЫЙ ВЫВОД =====
    out = f"""🔎 Результат поиска

👤 Аккаунт Telegram
├ ID: {uid}
├ Имя: {cur_name}
├ {is_bot}
└ {is_active}

📊 Статистика
├ Сообщений всего: {total_msgs}
├ Групп: {total_groups}
├ Смен имён: {names_count}
└ Смен юзернеймов: {usernames_count}

📅 Первое сообщение: ~ {reg_str}

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
    print("🤖 Бот запускается (полная версия как в скрипте)...")
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Вебхук удалён")
    print(f"📡 API: {BASE_URL}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
