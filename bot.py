import os
import asyncio
import aiohttp
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

# ===== ЗАГРУЗКА .env =====
load_dotenv()

# ===== КОНФИГ =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_TOKEN = os.getenv("FUNSTAT_API_TOKEN")
BASE_URL = os.getenv("FUNSTAT_BASE_URL", "http://telelog.info/api/v1")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в .env")
if not API_TOKEN:
    raise RuntimeError("FUNSTAT_API_TOKEN не задан в .env")

HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====
def parse_date(ts):
    """Конвертирует timestamp в читаемую дату"""
    if not ts:
        return "неизвестно"
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%d %b %y").lower()
    except:
        return str(ts)

async def api_get(endpoint, params=None):
    """Универсальный GET-запрос к FunStat API"""
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

async def resolve_username(username):
    """Получить ID пользователя по @username"""
    data = await api_get("/users/resolve_username", {"username": username.lstrip("@")})
    if data and isinstance(data, dict) and "id" in data:
        return data["id"]
    return None

async def get_user_stats(user_id):
    """Получить статистику, историю имён и подарки"""
    stats = await api_get(f"/users/{user_id}/stats")
    names = await api_get(f"/users/{user_id}/names")
    gifts = await api_get(f"/users/{user_id}/gifts_relation")
    return stats, names, gifts

# ===== ОБРАБОТЧИКИ КОМАНД =====
@dp.message(Command("start"))
async def start_command(msg: Message):
    await msg.answer(
        "👋 Привет! Я бот для поиска информации о пользователях Telegram через FunStat API.\n\n"
        "📌 Отправь мне:\n"
        "• @username (например, @vnxwi)\n"
        "• или числовой ID (например, 8276815852)\n\n"
        "Я покажу статистику, историю имён и подарки."
    )

@dp.message()
async def handle_user_query(msg: Message):
    text = msg.text.strip()
    user_id = None

    # Определяем, что прислали: ID или username
    if text.isdigit():
        user_id = int(text)
    elif text.startswith("@"):
        user_id = await resolve_username(text)
        if not user_id:
            await msg.answer("❌ Пользователь не найден. Проверь правильность username.")
            return
    else:
        await msg.answer("❌ Неверный формат. Отправь @username или числовой ID.")
        return

    # Отправляем статус
    wait_msg = await msg.answer("⏳ Загружаю данные...")

    # Получаем данные
    stats, names, gifts = await get_user_stats(user_id)

    if not stats:
        await wait_msg.edit_text("❌ Не удалось получить данные. Возможно, пользователь скрыт или API вернул ошибку.")
        return

    # ===== ФОРМИРУЕМ ОТВЕТ =====
    uid = stats.get("id", user_id)
    reg_ts = stats.get("registration_date")
    reg_str = parse_date(reg_ts) if reg_ts else "неизвестно"

    # История имён
    name_history = ""
    if names and isinstance(names, list):
        for i, item in enumerate(names[:5]):  # максимум 5 последних
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

    # Текущий юзернейм и имя
    cur_username = stats.get("username", "")
    cur_first = stats.get("first_name", "")
    cur_last = stats.get("last_name", "")
    cur_name = f"{cur_first} {cur_last}".strip()

    # Финальный вывод
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

# ===== ЗАПУСК =====
async def main():
    print("🤖 Бот запущен в режиме поллинга")
    print(f"📡 Подключен к API: {BASE_URL}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
