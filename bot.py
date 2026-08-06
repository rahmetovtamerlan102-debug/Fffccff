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
BASE_URL = os.getenv("FUNSTAT_BASE_URL", "http://telelog.info/api/v1")

if not BOT_TOKEN or not API_TOKEN:
    raise RuntimeError("BOT_TOKEN и FUNSTAT_API_TOKEN обязательны")

HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def parse_date(ts):
    if not ts:
        return "неизвестно"
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%d %b %y").lower()
    except:
        return str(ts)

async def api_get_full(endpoint, params=None):
    """Возвращает (данные, статус, текст_ошибки, full_response)"""
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=params) as resp:
            status = resp.status
            reason = resp.reason
            try:
                data = await resp.json()
            except:
                data = await resp.text()
            return data, status, reason

async def get_user_stats_full(user_id):
    """Возвращает stats, names, gifts и диагностику по каждому"""
    stats_data, stats_status, stats_reason = await api_get_full(f"/users/{user_id}/stats")
    names_data, names_status, _ = await api_get_full(f"/users/{user_id}/names")
    gifts_data, gifts_status, _ = await api_get_full(f"/users/{user_id}/gifts_relation")
    
    diagnostic = {
        "stats": {"status": stats_status, "reason": stats_reason, "data": stats_data},
        "names": {"status": names_status, "data": names_data},
        "gifts": {"status": gifts_status, "data": gifts_data}
    }
    
    stats = stats_data if stats_status == 200 else None
    names = names_data if names_status == 200 else None
    gifts = gifts_data if gifts_status == 200 else None
    
    return stats, names, gifts, diagnostic

@dp.message(Command("start"))
async def start_command(msg: Message):
    await msg.answer(
        "👋 Бот для FunStat API\n\n"
        "📌 Отправь @username или ID цифрами.\n"
        "При ошибке покажу точную причину."
    )

@dp.message()
async def handle_user_query(msg: Message):
    text = msg.text.strip()
    user_id = None

    if text.isdigit():
        user_id = int(text)
    elif text.startswith("@"):
        # Пробуем resolve
        async with aiohttp.ClientSession() as sess:
            async with sess.get(f"{BASE_URL}/users/resolve_username", headers=HEADERS, params={"username": text.lstrip("@")}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and "id" in data:
                        user_id = data["id"]
        if not user_id:
            await msg.answer(f"❌ Юзер {text} не найден через resolve. Попробуй ввести ID вручную.")
            return
    else:
        await msg.answer("❌ Отправь @username или ID цифрами.")
        return

    wait_msg = await msg.answer("⏳ Запрос к FunStat...")

    stats, names, gifts, diag = await get_user_stats_full(user_id)

    # ===== ДИАГНОСТИКА =====
    if not stats:
        status = diag["stats"]["status"]
        reason = diag["stats"]["reason"] or "нет данных"
        raw_data = diag["stats"]["data"]
        
        out = f"❌ Ошибка API (/{user_id}/stats)\n"
        out += f"├ Код: {status}\n"
        out += f"├ Причина: {reason}\n"
        out += f"└ Ответ сервера: {raw_data}\n\n"
        
        if status == 403:
            out += "🔒 **JWT токен недействителен или истёк.**\nОбнови токен в .env и перезапусти бота."
        elif status == 404:
            out += "❓ **Пользователь не найден в базе FunStat.**\nВозможно, аккаунт новый или скрыт."
        elif status == 429:
            out += "⏳ **Лимит запросов.** Подожди 1-2 минуты."
        elif status == 500:
            out += "⚙️ **Сервер FunStat упал.** Попробуй позже."
        else:
            out += f"ℹ️ Неизвестный код. Проверь токен и URL API."
        
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

🎁 Отправлено подарков: {sent}
🎁 Получено подарков: {received}
"""

    await wait_msg.edit_text(out)

async def main():
    print("🤖 Запуск...")
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Вебхук удалён")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
