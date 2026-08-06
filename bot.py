import os
import json
import asyncio
import aiohttp
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, Update
from aiohttp import web

# ===== ВСЁ ИЗ ОКРУЖЕНИЯ =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_TOKEN = os.getenv("FUNSTAT_API_TOKEN")
BASE_URL = os.getenv("FUNSTAT_BASE_URL", "http://telelog.info/api/v1")

if not BOT_TOKEN or not API_TOKEN:
    raise RuntimeError("BOT_TOKEN и FUNSTAT_API_TOKEN обязательны")

HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== API ФУНКЦИИ =====
def parse_date(ts):
    if not ts:
        return "неизвестно"
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%d %b %y").lower()
    except:
        return str(ts)

async def api_get(endpoint, params=None):
    async with aiohttp.ClientSession() as sess:
        async with sess.get(f"{BASE_URL}{endpoint}", headers=HEADERS, params=params) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

async def resolve_username(username):
    data = await api_get("/users/resolve_username", {"username": username.lstrip("@")})
    if data and isinstance(data, dict) and "id" in data:
        return data["id"]
    return None

async def get_user_stats(user_id):
    stats = await api_get(f"/users/{user_id}/stats")
    names = await api_get(f"/users/{user_id}/names")
    gifts = await api_get(f"/users/{user_id}/gifts_relation")
    return stats, names, gifts

# ===== ОБРАБОТЧИКИ =====
@dp.message(Command("start"))
async def start(msg: Message):
    await msg.answer("👋 Отправь @username или ID пользователя. Получишь полный отчёт.")

@dp.message()
async def handle_user(msg: Message):
    text = msg.text.strip()
    user_id = None

    if text.isdigit():
        user_id = int(text)
    elif text.startswith("@"):
        user_id = await resolve_username(text)
        if not user_id:
            await msg.answer("❌ Юзер не найден или ошибка API.")
            return
    else:
        await msg.answer("❌ Отправь ID или @username.")
        return

    stats, names, gifts = await get_user_stats(user_id)
    if not stats:
        await msg.answer("❌ Не удалось получить данные.")
        return

    uid = stats.get("id", user_id)
    reg_ts = stats.get("registration_date")
    reg_str = parse_date(reg_ts) if reg_ts else "неизвестно"

    name_history = ""
    if names and isinstance(names, list):
        for i, item in enumerate(names[:5]):
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
        if recv_list:
            received = ", ".join(str(x) for x in recv_list[:5])

    cur_username = stats.get("username", "")
    cur_name = stats.get("first_name", "") + " " + (stats.get("last_name") or "")
    cur_name = cur_name.strip()

    out = f"""🔎 Результат поиска по @{cur_username or uid}

👤 Аккаунт Telegram
├ ID: {uid}
└ Регистрация: ~ {reg_str}

👤 История изменения имени ({len(names) if names else 0})
{name_history}

🎁 Кому отправлял(-а) подарки: {sent}
🎁 От кого получал(-а) подарки: {received}
"""
    await msg.answer(out)

# ===== ВЕБХУК (для Render) =====
async def handle_webhook(request):
    data = await request.json()
    update = Update(**data)
    await dp.process_update(update)
    return web.Response(status=200)

async def on_startup(app):
    webhook_url = os.getenv("RENDER_EXTERNAL_URL")
    if webhook_url:
        await bot.set_webhook(f"{webhook_url}/webhook")
        print(f"Webhook set to {webhook_url}/webhook")

async def main():
    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    app.on_startup.append(on_startup)
    return app

if __name__ == "__main__":
    web.run_app(main(), host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
