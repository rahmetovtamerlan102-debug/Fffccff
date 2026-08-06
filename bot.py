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

async def api_get_raw(endpoint, params=None):
    """Возвращает (данные, статус, raw_text) для диагностики"""
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=params) as resp:
            status = resp.status
            try:
                data = await resp.json()
                raw = str(data)[:500]
            except:
                raw = await resp.text()
                data = None
            return data, status, raw

async def api_get(endpoint, params=None):
    """Как в твоём скрипте — возвращает data или None"""
    data, status, _ = await api_get_raw(endpoint, params)
    if status == 200 and data:
        if isinstance(data, dict) and data.get('success') is True:
            return data.get('data')
        elif isinstance(data, dict) and 'id' in data:
            return data
        elif isinstance(data, list) and data:
            return data
    return None

async def get_id_by_username(username):
    username = username.replace('@', '').strip()
    data = await api_get("/users/resolve_username", {"username": username})
    if data:
        if isinstance(data, dict):
            return data.get('id')
        elif isinstance(data, list) and data:
            return data[0].get('id')
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

async def get_user_stats_with_diagnostic(user_id):
    """Возвращает stats, names, gifts и диагностику"""
    stats_data, stats_status, stats_raw = await api_get_raw(f"/users/{user_id}/stats")
    names_data, names_status, _ = await api_get_raw(f"/users/{user_id}/names")
    gifts_data, gifts_status, _ = await api_get_raw(f"/users/{user_id}/gifts_relation")
    
    diagnostic = {
        "stats": {"status": stats_status, "raw": stats_raw[:300]},
        "names": {"status": names_status},
        "gifts": {"status": gifts_status}
    }
    
    stats = None
    if stats_status == 200 and stats_data:
        if isinstance(stats_data, dict) and stats_data.get('success') is True:
            stats = stats_data.get('data')
        elif isinstance(stats_data, dict) and 'id' in stats_data:
            stats = stats_data
    
    names = None
    if names_status == 200 and names_data:
        if isinstance(names_data, dict) and names_data.get('success') is True:
            names = names_data.get('data')
        elif isinstance(names_data, list):
            names = names_data
    
    gifts = None
    if gifts_status == 200 and gifts_data:
        if isinstance(gifts_data, dict) and gifts_data.get('success') is True:
            gifts = gifts_data.get('data')
        elif isinstance(gifts_data, dict):
            gifts = gifts_data
    
    return stats, names, gifts, diagnostic

@dp.message(Command("start"))
async def start_command(msg: Message):
    await msg.answer(
        "👋 Бот для FunStat API\n\n"
        "📌 Отправь @username или ID.\n"
        "При ошибке покажу сырой ответ сервера."
    )

@dp.message()
async def handle_user_query(msg: Message):
    text = msg.text.strip()
    
    user_id = await get_user_id(text)
    if not user_id:
        await msg.answer(f"❌ Пользователь {text} не найден.")
        return

    wait_msg = await msg.answer("⏳ Запрос к API...")

    stats, names, gifts, diag = await get_user_stats_with_diagnostic(user_id)

    if not stats:
        status = diag["stats"]["status"]
        raw = diag["stats"]["raw"]
        
        out = f"❌ Ошибка API (/{user_id}/stats)\n"
        out += f"├ Код: {status}\n"
        out += f"└ Ответ сервера:\n{raw}\n\n"
        
        if status == 401:
            out += "🔒 **Токен недействителен.** Обнови JWT в .env"
        elif status == 403:
            out += "🔒 **Недостаточно баланса.** Пополни счёт в FunStat"
        elif status == 404:
            out += "❓ **Пользователь не найден** в базе FunStat"
        elif status == 429:
            out += "⏳ **Лимит запросов.** Подожди 1-2 минуты"
        elif status == 500:
            out += "⚙️ **Сервер FunStat упал.** Попробуй позже"
        else:
            out += f"ℹ️ Неизвестный код. Проверь токен и URL."
        
        await wait_msg.edit_text(out)
        return

    # ===== УСПЕШНЫЙ ОТВЕТ =====
    uid = stats.get("id", user_id)
    reg_ts = stats.get("registration_date")
    reg_str = parse_date(reg_ts) if reg_ts else "неизвестно"

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

    out = f"""🔎 Результат по @{cur_username or uid}

👤 Аккаунт
├ ID: {uid}
├ Имя: {cur_name or "не указано"}
└ Регистрация: ~ {reg_str}

👤 История имён ({len(names) if names else 0})
{name_history}

🎁 Отправлено: {sent}
🎁 Получено: {received}
"""

    await wait_msg.edit_text(out)

async def main():
    print("🤖 Запуск...")
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Вебхук удалён")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
