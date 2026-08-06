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
    """Универсальный GET с обработкой разных структур ответа"""
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            
            # Если есть обёртка success/data
            if isinstance(data, dict) and data.get('success') is True:
                # Для /stats — данные лежат в data.data
                if 'data' in data and isinstance(data['data'], dict):
                    # Если внутри data есть поле data (как в /stats)
                    if 'data' in data['data']:
                        return data['data']['data']
                    return data['data']
                return data.get('data')
            
            # Если нет обёртки — возвращаем как есть
            return data

async def get_user_id_by_username(username):
    """Поиск ID через /resolve_username с правильным параметром req"""
    username = username.replace('@', '').strip()
    # Документация: нужен параметр req, а не username
    data = await api_get("/users/resolve_username", {"req": username})
    if data and isinstance(data, dict):
        return data.get('id')
    return None

async def get_user_id(identifier):
    identifier = str(identifier).strip()
    if identifier.isdigit():
        return identifier
    return await get_user_id_by_username(identifier)

async def get_user_stats(user_id):
    """Получить stats, names, gifts"""
    stats = await api_get(f"/users/{user_id}/stats")
    names = await api_get(f"/users/{user_id}/names")
    gifts = await api_get(f"/users/{user_id}/gifts_relation")
    return stats, names, gifts

@dp.message(Command("start"))
async def start_command(msg: Message):
    await msg.answer(
        "👋 Бот для FunStat API\n\n"
        "📌 Отправь @username или ID цифрами.\n"
        "Показывает статистику, историю имён и подарки."
    )

@dp.message()
async def handle_user_query(msg: Message):
    text = msg.text.strip()
    
    user_id = await get_user_id(text)
    if not user_id:
        await msg.answer(f"❌ Пользователь {text} не найден.")
        return

    wait_msg = await msg.answer("⏳ Загружаю данные...")

    stats, names, gifts = await get_user_stats(user_id)

    if not stats:
        await wait_msg.edit_text(
            f"❌ Не удалось получить данные по ID {user_id}.\n"
            f"Проверь баланс или попробуй позже."
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

async def main():
    print("🤖 Бот запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Вебхук удалён")
    print(f"📡 API: {BASE_URL}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
