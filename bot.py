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

async def api_get_diagnostic(endpoint, params=None):
    """Возвращает (данные, статус, текст_ошибки)"""
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=params) as resp:
            status = resp.status
            try:
                data = await resp.json()
            except:
                data = await resp.text()
            return data, status, resp.reason

async def api_get(endpoint, params=None):
    data, status, _ = await api_get_diagnostic(endpoint, params)
    if status == 200:
        return data
    return None

async def resolve_username_v1(username):
    data = await api_get("/users/resolve_username", {"username": username.lstrip("@")})
    if data and isinstance(data, dict) and "id" in data:
        return data["id"]
    return None

async def resolve_username_v2(username):
    data = await api_get("/users/basic_info_by_id", {"identifier": username.lstrip("@")})
    if data and isinstance(data, dict) and "id" in data:
        return data["id"]
    return None

async def get_user_id_by_username(username):
    clean = username.lstrip("@")
    uid = await resolve_username_v1(clean)
    if uid:
        return uid
    uid = await resolve_username_v2(clean)
    if uid:
        return uid
    return None

async def get_user_stats_with_diagnostic(user_id):
    """Возвращает stats, names, gifts, а также diagnostic-словарь"""
    stats_data, stats_status, stats_reason = await api_get_diagnostic(f"/users/{user_id}/stats")
    names_data, names_status, _ = await api_get_diagnostic(f"/users/{user_id}/names")
    gifts_data, gifts_status, _ = await api_get_diagnostic(f"/users/{user_id}/gifts_relation")
    
    diagnostic = {
        "stats": {"status": stats_status, "reason": stats_reason},
        "names": {"status": names_status},
        "gifts": {"status": gifts_status}
    }
    
    stats = stats_data if stats_status == 200 else None
    names = names_data if names_status == 200 else None
    gifts = gifts_data if gifts_status == 200 else None
    
    return stats, names, gifts, diagnostic

@dp.message(Command("start"))
async def start_command(msg: Message):
    await msg.answer(
        "👋 Бот для поиска по FunStat API\n\n"
        "📌 Отправь:\n"
        "• @username\n"
        "• или ID цифрами\n\n"
        "⚠️ Если ошибка — бот покажет код и причину."
    )

@dp.message()
async def handle_user_query(msg: Message):
    text = msg.text.strip()
    user_id = None

    if text.isdigit():
        user_id = int(text)
    else:
        user_id = await get_user_id_by_username(text)
        if not user_id:
            await msg.answer(
                f"❌ Пользователь @{text.lstrip('@')} не найден в FunStat.\n\n"
                f"💡 Попробуй ввести ID вручную, если знаешь его."
            )
            return

    wait_msg = await msg.answer("⏳ Загружаю данные...")

    stats, names, gifts, diagnostic = await get_user_stats_with_diagnostic(user_id)

    # ===== ДИАГНОСТИКА =====
    if not stats:
        diag_text = f"❌ Ошибка API при запросе /users/{user_id}/stats\n"
        diag_text += f"├ Код: {diagnostic['stats']['status']}\n"
        diag_text += f"└ Причина: {diagnostic['stats']['reason'] or 'неизвестно'}\n\n"
        
        if diagnostic['stats']['status'] == 403:
            diag_text += "🔒 Доступ запрещён. Проверь JWT токен — возможно, истёк или недействителен.\n"
        elif diagnostic['stats']['status'] == 404:
            diag_text += "❓ Пользователь не найден в базе FunStat.\n"
        elif diagnostic['stats']['status'] == 429:
            diag_text += "⏳ Слишком много запросов. Подожди минуту и попробуй снова.\n"
        elif diagnostic['stats']['status'] == 500:
            diag_text += "⚙️ Внутренняя ошибка сервера FunStat. Попробуй позже.\n"
        else:
            diag_text += f"ℹ️ Неизвестный код. Проверь токен и доступ к API.\n"
        
        await wait_msg.edit_text(diag_text)
        return

    # ===== ФОРМИРОВАНИЕ ОТВЕТА (если всё ОК) =====
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
