#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import asyncio
import requests
from datetime import datetime, timezone
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
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

def parse_registration_date(ts):
    """Форматирует дату регистрации как 'март 2025'"""
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
# ФУНКЦИИ ИЗ ТВОЕГО СКРИПТА
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
    """История юзернеймов (для отображения в истории имён)"""
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
        "Показывает компактный отчёт: ID, регистрация, история имён, подарки."
    )

@dp.message()
async def handle_user_query(msg: Message):
    text = msg.text.strip()
    
    user_id = get_user_id(text)
    if not user_id:
        await msg.answer(f"❌ Пользователь {text} не найден.")
        return

    wait_msg = await msg.answer("⏳ Загружаю данные...")

    # Получаем данные
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

    # ===== ФОРМИРУЕМ КОМПАКТНЫЙ ОТВЕТ =====
    uid = stats.get("id", user_id)
    username = stats.get("username", "")
    
    # Регистрация
    first_msg = stats.get("first_msg_date")
    reg_str = parse_registration_date(first_msg) if first_msg else "неизвестно"

    # ===== ИСТОРИЯ ИМЁН (с юзернеймами) =====
    name_history = ""
    
    # Собираем историю из names и usernames
    history_items = []
    
    # Добавляем имена
    if names and isinstance(names, list):
        for item in names:
            fn = item.get("first_name", "")
            ln = item.get("last_name", "")
            full = f"{fn} {ln}".strip()
            date_str = parse_date(item.get("date"))
            history_items.append({
                "date": item.get("date"),
                "date_str": date_str,
                "text": full,
                "type": "name"
            })
    
    # Добавляем юзернеймы
    if usernames_history and isinstance(usernames_history, list):
        for item in usernames_history:
            uname = item.get("username", "")
            date_str = parse_date(item.get("date"))
            history_items.append({
                "date": item.get("date"),
                "date_str": date_str,
                "text": f"@{uname}",
                "type": "username"
            })
    
    # Сортируем по дате (новые сверху)
    history_items.sort(key=lambda x: x.get("date", 0), reverse=True)
    
    # Формируем вывод (максимум 10 записей)
    for item in history_items[:10]:
        date_str = item["date_str"]
        text = item["text"]
        if text:
            name_history += f"├ {date_str} → {text}\n"
    
    if not name_history:
        name_history = "└ нет данных\n"

    # ===== ПОДАРКИ =====
    sent = "нет"
    received = "нет"
    if gifts and isinstance(gifts, dict):
        sent_list = gifts.get("sent", [])
        recv_list = gifts.get("received", [])
        if sent_list:
            sent = ", ".join(str(x) for x in sent_list[:3])
            if len(sent_list) > 3:
                sent += f" ... и ещё {len(sent_list)-3}"
        if recv_list:
            received = ", ".join(str(x) for x in recv_list[:3])
            if len(recv_list) > 3:
                received += f" ... и ещё {len(recv_list)-3}"

    # ===== КОМПАКТНЫЙ ВЫВОД =====
    out = f"""🔎 Результат поиска по @{username or uid}

👤 Аккаунт Telegram
├ ID: {uid}
└ Регистрация: ~ {reg_str}

👤 История изменения имени ({len(history_items)})
{name_history}

🎁 Кому отправлял(-а) подарки: {sent}
🎁 От кого получал(-а) подарки: {received}
"""

    # Кнопка для полного отчёта (если нужно)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📎 Полный отчёт", callback_data=f"full_{uid}")]
    ])

    await wait_msg.edit_text(out, reply_markup=keyboard)

# ============================================================
# ОБРАБОТКА КНОПКИ "ПОЛНЫЙ ОТЧЁТ"
# ============================================================

@dp.callback_query(lambda c: c.data and c.data.startswith("full_"))
async def full_report_callback(callback: types.CallbackQuery):
    user_id = callback.data.split("_")[1]
    
    await callback.answer("⏳ Загружаю полный отчёт...")
    
    stats = get_user_stats_min(user_id)
    names = get_user_names(user_id)
    gifts = get_user_gifts(user_id)
    usernames_history = get_user_usernames(user_id)
    
    if not stats:
        await callback.message.edit_text(f"❌ Не удалось получить данные по ID {user_id}.")
        return
    
    # Полный отчёт (со статистикой)
    uid = stats.get("id", user_id)
    username = stats.get("username", "")
    first_name = stats.get("first_name", "")
    last_name = stats.get("last_name", "")
    cur_name = f"{first_name} {last_name}".strip() or "не указано"
    
    first_msg = stats.get("first_msg_date")
    reg_str = parse_date(first_msg) if first_msg else "неизвестно"
    
    total_msgs = stats.get("total_msg_count", 0)
    total_groups = stats.get("total_groups", 0)
    names_count = stats.get("names_count", 0)
    usernames_count = stats.get("usernames_count", 0)
    is_bot = "🤖 Бот" if stats.get("is_bot") else "👤 Человек"
    is_active = "🟢 Активен" if stats.get("is_active") else "🔴 Неактивен"
    
    # История имён (полная)
    name_history_full = ""
    history_items = []
    if names and isinstance(names, list):
        for item in names:
            fn = item.get("first_name", "")
            ln = item.get("last_name", "")
            full = f"{fn} {ln}".strip()
            date_str = parse_date(item.get("date"))
            history_items.append({
                "date": item.get("date"),
                "date_str": date_str,
                "text": full,
                "type": "name"
            })
    if usernames_history and isinstance(usernames_history, list):
        for item in usernames_history:
            uname = item.get("username", "")
            date_str = parse_date(item.get("date"))
            history_items.append({
                "date": item.get("date"),
                "date_str": date_str,
                "text": f"@{uname}",
                "type": "username"
            })
    history_items.sort(key=lambda x: x.get("date", 0), reverse=True)
    
    for item in history_items[:20]:
        date_str = item["date_str"]
        text = item["text"]
        if text:
            name_history_full += f"├ {date_str} → {text}\n"
    if not name_history_full:
        name_history_full = "└ нет данных\n"
    
    # Подарки (полные)
    sent_full = "нет"
    received_full = "нет"
    if gifts and isinstance(gifts, dict):
        sent_list = gifts.get("sent", [])
        recv_list = gifts.get("received", [])
        if sent_list:
            sent_full = ", ".join(str(x) for x in sent_list[:10])
            if len(sent_list) > 10:
                sent_full += f" ... и ещё {len(sent_list)-10}"
        if recv_list:
            received_full = ", ".join(str(x) for x in recv_list[:10])
            if len(recv_list) > 10:
                received_full += f" ... и ещё {len(recv_list)-10}"
    
    out_full = f"""📊 Полный отчёт по @{username or uid}

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

👤 Полная история изменения имени ({len(history_items)})
{name_history_full}

🎁 Кому отправлял(-а) подарки: {sent_full}
🎁 От кого получал(-а) подарки: {received_full}
"""
    
    await callback.message.edit_text(out_full)

# ============================================================
# ЗАПУСК
# ============================================================

async def main():
    print("🤖 Бот запускается (компактный формат)...")
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Вебхук удалён")
    print(f"📡 API: {BASE_URL}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
