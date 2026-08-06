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

# ============================================================
# АВТОМАТИЧЕСКИЙ ПОИСК РАБОЧЕГО ПРОКСИ
# ============================================================

def get_working_proxy():
    """Скачивает список прокси и возвращает первый рабочий"""
    sources = [
        "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/http.txt",
        "https://raw.githubusercontent.com/theriturajps/proxy-list/main/proxies.txt",
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies.txt"
    ]
    
    for url in sources:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            proxies = resp.text.splitlines()
            for proxy in proxies[:50]:
                proxy = proxy.strip()
                if not proxy or proxy.startswith('#'):
                    continue
                # Формат: ip:port
                proxy_url = f"http://{proxy}"
                # Проверяем, работает ли прокси (проверка через telegram.org)
                try:
                    test_resp = requests.get(
                        "https://telegram.org",
                        proxies={"http": proxy_url, "https": proxy_url},
                        timeout=5
                    )
                    if test_resp.status_code == 200:
                        print(f"✅ Найден рабочий прокси: {proxy_url}")
                        return proxy_url
                except:
                    continue
        except:
            continue
    return None

PROXY = get_working_proxy()
PROXIES = None
if PROXY:
    PROXIES = {"http": PROXY, "https": PROXY}
    print(f"✅ Используется прокси: {PROXY}")
else:
    print("⚠️ Прокси не найдены, работаем без прокси")

# ============================================================
# ОСНОВНАЯ ЛОГИКА БОТА
# ============================================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

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

def get_user_id(identifier):
    identifier = str(identifier).strip()
    if identifier.isdigit():
        return identifier
    return None

def get_user_stats_min(user_id):
    url = f"{BASE_URL}/users/{user_id}/stats_min"
    try:
        resp = requests.get(url, headers=HEADERS, proxies=PROXIES, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")
        return None

@dp.message(Command("start"))
async def start_command(msg: Message):
    await msg.answer(
        "👋 Бот для FunStat API (с автоматическим прокси)\n\n"
        "📌 Отправь **числовой ID** пользователя.\n"
        "Например: `8276815852`\n\n"
        "✅ Прокси подбирается автоматически при каждом запуске."
    )

@dp.message()
async def handle_user_query(msg: Message):
    text = msg.text.strip()
    
    if not text.isdigit():
        await msg.answer("❌ Отправь **числовой ID**. Например: `8276815852`")
        return
    
    user_id = int(text)
    wait_msg = await msg.answer("⏳ Загружаю данные...")

    stats = get_user_stats_min(user_id)

    if not stats:
        await wait_msg.edit_text(
            f"❌ Не удалось получить данные по ID {user_id}.\n"
            f"Попробуй позже или перезапусти бота."
        )
        return

    uid = stats.get("id", user_id)
    username = stats.get("username", "")
    first_name = stats.get("first_name", "")
    last_name = stats.get("last_name", "")
    cur_name = f"{first_name} {last_name}".strip() or "не указано"
    
    first_msg = stats.get("first_msg_date")
    reg_str = parse_registration_date(first_msg) if first_msg else "неизвестно"
    
    total_msgs = stats.get("total_msg_count", 0)
    total_groups = stats.get("total_groups", 0)
    names_count = stats.get("names_count", 0)
    usernames_count = stats.get("usernames_count", 0)
    is_bot = "🤖 Бот" if stats.get("is_bot") else "👤 Человек"
    is_active = "🟢 Активен" if stats.get("is_active") else "🔴 Неактивен"

    out = f"""🔎 Результат поиска по @{username or uid}

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

📅 Регистрация: ~ {reg_str}
"""

    await wait_msg.edit_text(out)

async def main():
    print("🤖 Бот запускается с автоматическим прокси...")
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Вебхук удалён")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
