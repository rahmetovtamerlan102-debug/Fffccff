#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import asyncio
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

# ===== АВТОПРОКСИ =====
def get_working_proxy():
    sources = [
        "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/http.txt",
        "https://raw.githubusercontent.com/theriturajps/proxy-list/main/proxies.txt"
    ]
    for url in sources:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            for proxy in resp.text.splitlines()[:50]:
                proxy = proxy.strip()
                if not proxy or proxy.startswith('#'):
                    continue
                proxy_url = f"http://{proxy}"
                try:
                    if requests.get("https://telegram.org", proxies={"http": proxy_url, "https": proxy_url}, timeout=5).status_code == 200:
                        return proxy_url
                except:
                    continue
        except:
            continue
    return None

PROXY = get_working_proxy()
PROXIES = {"http": PROXY, "https": PROXY} if PROXY else None
if PROXY:
    print(f"✅ Прокси: {PROXY}")
else:
    print("⚠️ Без прокси")

# ===== ФУНКЦИИ =====
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

def parse_registration_date(ts):
    if not ts:
        return "неизвестно"
    try:
        if isinstance(ts, int):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        months = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 
                  'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']
        return f"{months[dt.month-1]} {dt.year}"
    except:
        return str(ts)

def api_get_fast(url, timeout=5):
    """Быстрый запрос с коротким таймаутом"""
    try:
        resp = requests.get(url, headers=HEADERS, proxies=PROXIES, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        return None
    except:
        return None

# ===== МЕТОДЫ =====
def get_id_by_username(username):
    username = username.replace('@', '').strip()
    url = f"{BASE_URL}/users/resolve_username?username={username}"
    data = api_get_fast(url, timeout=10)
    if data and data.get('success'):
        d = data.get('data', {})
        if isinstance(d, dict):
            return d.get('id')
        elif isinstance(d, list) and d:
            return d[0].get('id')
    return None

def find_id_by_historical_username(username):
    username = username.replace('@', '').strip()
    url = f"{BASE_URL}/users/username_usage?username={username}"
    data = api_get_fast(url, timeout=10)
    if data and data.get('success'):
        users = data.get('data', {}).get('active_users', [])
        if users:
            return users[0].get('id')
    return None

def get_user_id(identifier):
    identifier = str(identifier).strip()
    if identifier.isdigit():
        return identifier
    uid = get_id_by_username(identifier)
    if uid:
        return uid
    uid = find_id_by_historical_username(identifier)
    if uid:
        return uid
    return None

def get_user_stats_min(user_id):
    url = f"{BASE_URL}/users/{user_id}/stats_min"
    return api_get_fast(url, timeout=10)

def get_user_names(user_id):
    url = f"{BASE_URL}/users/{user_id}/names"
    data = api_get_fast(url, timeout=5)  # короткий таймаут
    if data and data.get('success'):
        return data.get('data', [])
    return data if isinstance(data, list) else []

def get_user_gifts(user_id):
    url = f"{BASE_URL}/users/{user_id}/gifts_relation"
    data = api_get_fast(url, timeout=5)
    if data and data.get('success'):
        return data.get('data', {})
    return data if isinstance(data, dict) else {}

def get_user_usernames(user_id):
    url = f"{BASE_URL}/users/{user_id}/usernames"
    data = api_get_fast(url, timeout=5)
    if data and data.get('success'):
        return data.get('data', [])
    return data if isinstance(data, list) else []

# ===== БОТ =====
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(msg: Message):
    await msg.answer("👋 Бот для FunStat. Отправь @username или ID.")

@dp.message()
async def handle(msg: Message):
    text = msg.text.strip()
    user_id = get_user_id(text)
    if not user_id:
        await msg.answer(f"❌ {text} не найден.")
        return

    wait = await msg.answer("⏳ Загружаю данные...")

    stats = get_user_stats_min(user_id)
    if not stats:
        await wait.edit_text(f"❌ Ошибка по ID {user_id}. Проверь токен/баланс.")
        return

    # ---- Быстрые данные (ID + регистрация) ----
    uid = stats.get("id", user_id)
    username = stats.get("username", "")
    reg_str = parse_registration_date(stats.get("first_msg_date"))

    # ---- Пытаемся получить остальное, но не ждём долго ----
    names = get_user_names(user_id)
    usernames = get_user_usernames(user_id)
    gifts = get_user_gifts(user_id)

    # ---- Формируем историю ----
    history = []
    for item in (names or []):
        full = f"{item.get('first_name', '')} {item.get('last_name', '')}".strip()
        if full:
            history.append((item.get('date'), parse_date(item.get('date')), full))
    for item in (usernames or []):
        uname = item.get('username', '')
        if uname:
            history.append((item.get('date'), parse_date(item.get('date')), f"@{uname}"))
    history.sort(key=lambda x: x[0] or 0, reverse=True)

    name_history = "".join(f"├ {d} → {t}\n" for _, d, t in history)
    if not name_history:
        name_history = "└ нет данных\n"

    # ---- Подарки ----
    sent = received = "нет"
    if gifts:
        sl = gifts.get('sent', [])
        rl = gifts.get('received', [])
        if sl:
            sent = ", ".join(map(str, sl[:5]))
            if len(sl) > 5:
                sent += f" ... и ещё {len(sl)-5}"
        if rl:
            received = ", ".join(map(str, rl[:5]))
            if len(rl) > 5:
                received += f" ... и ещё {len(rl)-5}"

    out = f"""🔎 Результат поиска по @{username or uid}

👤 Аккаунт Telegram
├ ID: {uid}
└ Регистрация: ~ {reg_str}

👤 История изменения имени ({len(history)})
{name_history}

🎁 Кому отправлял(-а) подарки: {sent}
🎁 От кого получал(-а) подарки: {received}
"""

    await wait.edit_text(out)

# ===== ЗАПУСК =====
async def main():
    print("🚀 Бот запущен (быстрый режим)")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
