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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ============================================================
# ФУНКЦИИ ФОРМАТИРОВАНИЯ (как в твоём скрипте)
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

def parse_registration_date(ts):
    """Формат: март 2025"""
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

# ============================================================
# ФУНКЦИИ ЗАПРОСОВ (как в твоём скрипте)
# ============================================================

def get_id_by_username(username):
    username = username.replace('@', '').strip()
    url = f"{BASE_URL}/users/resolve_username?username={username}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                d = data.get('data', {})
                if isinstance(d, dict):
                    return d.get('id')
                elif isinstance(d, list) and d:
                    return d[0].get('id')
        return None
    except:
        return None

def find_id_by_historical_username(username):
    username = username.replace('@', '').strip()
    url = f"{BASE_URL}/users/username_usage?username={username}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                users = data.get('data', {}).get('active_users', [])
                if users:
                    return users[0].get('id')
        return None
    except:
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
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        return None
    except:
        return None

def get_user_names(user_id):
    url = f"{BASE_URL}/users/{user_id}/names"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                return data.get('data', [])
            return data if isinstance(data, list) else []
        return []
    except:
        return []

def get_user_gifts(user_id):
    url = f"{BASE_URL}/users/{user_id}/gifts_relation"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                return data.get('data', {})
            return data if isinstance(data, dict) else {}
        return {}
    except:
        return {}

def get_user_usernames(user_id):
    url = f"{BASE_URL}/users/{user_id}/usernames"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                return data.get('data', [])
            return data if isinstance(data, list) else []
        return []
    except:
        return []

# ============================================================
# ОБРАБОТЧИКИ
# ============================================================

@dp.message(Command("start"))
async def start_command(msg: Message):
    await msg.answer(
        "👋 Бот для FunStat API\n\n"
        "📌 Отправь @username или ID цифрами.\n"
        "Выдаёт отчёт как в твоём скрипте."
    )

@dp.message()
async def handle_user_query(msg: Message):
    text = msg.text.strip()
    
    user_id = get_user_id(text)
    if not user_id:
        await msg.answer(f"❌ Пользователь {text} не найден.")
        return

    wait_msg = await msg.answer("⏳ Загружаю данные...")

    # Получаем все данные
    stats = get_user_stats_min(user_id)
    names = get_user_names(user_id)
    gifts = get_user_gifts(user_id)
    usernames_history = get_user_usernames(user_id)

    if not stats:
        await wait_msg.edit_text(
            f"❌ Не удалось получить данные по ID {user_id}.\n"
            f"Проверь баланс или попробуй позже."
        )
        return

    # ===== ФОРМИРУЕМ ВЫВОД (как в твоём скрипте) =====
    uid = stats.get("id", user_id)
    username = stats.get("username", "")
    
    # Регистрация
    first_msg = stats.get("first_msg_date")
    reg_str = parse_registration_date(first_msg) if first_msg else "неизвестно"

    # ===== ИСТОРИЯ ИМЁН + ЮЗЕРНЕЙМОВ =====
    history_items = []
    
    if names and isinstance(names, list):
        for item in names:
            fn = item.get("first_name", "")
            ln = item.get("last_name", "")
            full = f"{fn} {ln}".strip()
            if full:
                history_items.append({
                    "date": item.get("date"),
                    "date_str": parse_date(item.get("date")),
                    "text": full,
                    "type": "name"
                })
    
    if usernames_history and isinstance(usernames_history, list):
        for item in usernames_history:
            uname = item.get("username", "")
            if uname:
                history_items.append({
                    "date": item.get("date"),
                    "date_str": parse_date(item.get("date")),
                    "text": f"@{uname}",
                    "type": "username"
                })
    
    # Сортируем по дате (новые сверху)
    history_items.sort(key=lambda x: x.get("date", 0), reverse=True)
    
    name_history = ""
    for item in history_items:
        name_history += f"├ {item['date_str']} → {item['text']}\n"
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
    out = f"""🔎 Результат поиска по @{username or uid}

👤 Аккаунт Telegram
├ ID: {uid}
└ Регистрация: ~ {reg_str}

👤 История изменения имени ({len(history_items)})
{name_history}

🎁 Кому отправлял(-а) подарки: {sent}
🎁 От кого получал(-а) подарки: {received}
"""

    await wait_msg.edit_text(out)

# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    print("🤖 Бот запускается (формат как в твоём скрипте)...")
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Вебхук удалён")
    print(f"📡 API: {BASE_URL}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
