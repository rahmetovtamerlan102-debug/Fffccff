#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
from flask import Flask, request
from datetime import datetime

app = Flask(__name__)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TELELOG_TOKEN = os.environ.get("TELELOG_TOKEN")
if not TELELOG_TOKEN:
    raise ValueError("❌ TELELOG_TOKEN не задан!")

BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Опционально, для Telegram-бота

BASE = "https://telelog.info/api/v1"
HEADERS = {"accept": "text/plain", "Authorization": f"Bearer {TELELOG_TOKEN}"}

# === ФУНКЦИИ API ===

def get_user_id(identifier):
    identifier = str(identifier).strip()
    if identifier.isdigit():
        return identifier
    
    username = identifier.replace('@', '').strip()
    url = f"{BASE}/users/resolve_username?username={username}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
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

def fetch(endpoint):
    url = f"{BASE}{endpoint}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return None
    except:
        return None

def format_date_short(date_str):
    if not date_str:
        return "???"
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        months = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек']
        return f"{dt.day} {months[dt.month-1]} {dt.year}"
    except:
        return date_str[:10]

def get_registration_date(user_id):
    data = fetch(f"/users/{user_id}/usernames")
    if data and data.get('success'):
        items = data.get('data', [])
        if items:
            oldest = items[-1]
            date_str = oldest.get('date_time', '')
            if date_str:
                try:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    months = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек']
                    return f"~ {months[dt.month-1]} {dt.year}"
                except:
                    pass
    
    data = fetch(f"/users/{user_id}/names")
    if data and data.get('success'):
        items = data.get('data', [])
        if items:
            oldest = items[-1]
            date_str = oldest.get('date_time', '')
            if date_str:
                try:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    months = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек']
                    return f"~ {months[dt.month-1]} {dt.year}"
                except:
                    pass
    
    return "неизвестно"

def search_user(identifier):
    user_id = get_user_id(identifier)
    if not user_id:
        return f"❌ Пользователь {identifier} не найден."

    lines = []
    
    username = identifier
    if identifier.isdigit():
        info = fetch(f"/users/basic_info_by_id?req={user_id}")
        if info and info.get('success'):
            data = info.get('data', {})
            if data.get('username'):
                username = f"@{data.get('username')}"
            else:
                username = f"ID: {user_id}"
    
    lines.append(f"🔎 Результат поиска по {username}\n")
    lines.append("👤 Аккаунт Telegram")
    lines.append(f"├ ID: {user_id}")
    lines.append(f"└ Регистрация: {get_registration_date(user_id)}")
    
    # История
    usernames_data = fetch(f"/users/{user_id}/usernames")
    names_data = fetch(f"/users/{user_id}/names")
    
    changes = []
    if usernames_data and usernames_data.get('success'):
        for item in usernames_data.get('data', []):
            changes.append({'date': item.get('date_time', ''), 'username': item.get('name', ''), 'name': None})
    if names_data and names_data.get('success'):
        for item in names_data.get('data', []):
            changes.append({'date': item.get('date_time', ''), 'username': None, 'name': item.get('name', '')})
    
    changes.sort(key=lambda x: x['date'], reverse=True)
    
    if changes:
        lines.append(f"\n👤 История изменения имени ({len(changes)})")
        for i, item in enumerate(changes[:2], 1):
            date_str = format_date_short(item.get('date', ''))
            username_part = f"@{item['username']}" if item.get('username') else ""
            name_part = item.get('name') if item.get('name') else ""
            
            if username_part and name_part:
                line = f"├ {date_str} → {username_part}, {name_part}"
            elif username_part:
                line = f"├ {date_str} → {username_part}"
            elif name_part:
                line = f"├ {date_str} → {name_part}"
            else:
                line = f"├ {date_str} → (изменение)"
            
            if i == len(changes[:2]):
                line = line.replace('├', '└')
            lines.append(line)
    else:
        lines.append("\n👤 История изменения имени (0)\n└ Нет данных")
    
    # Подарки
    gifts_data = fetch(f"/users/{user_id}/gifts_relation")
    if gifts_data and gifts_data.get('success'):
        items = gifts_data.get('data', [])
        sent_to = []
        received_from = []
        for item in items:
            from_id = str(item.get('from_user_id', ''))
            to_id = str(item.get('to_user_id', ''))
            if from_id == user_id:
                sent_to.append(to_id)
            else:
                received_from.append(from_id)
        
        sent_to = list(set(sent_to))
        received_from = list(set(received_from))
        
        if sent_to or received_from:
            lines.append("\n🎁 Подарки:")
            if sent_to:
                lines.append(f"├ Кому отправлял: {', '.join(sent_to[:3])}")
            if received_from:
                lines.append(f"└ От кого получал: {', '.join(received_from[:3])}")
    
    return "\n".join(lines)

# === ЭНДПОИНТЫ ===

@app.route('/')
def home():
    return "🔎 Telelog Bot\nИспользование: /search?q=username или /search?q=id"

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return "❌ Укажите q=username или q=id"
    
    result = search_user(query)
    return result, 200, {'Content-Type': 'text/plain; charset=utf-8'}

# === TELEGRAM WEBHOOK (если задан BOT_TOKEN) ===
if BOT_TOKEN:
    @app.route(f'/{BOT_TOKEN}', methods=['POST'])
    def webhook():
        data = request.get_json()
        if not data or 'message' not in data:
            return 'ok', 200
        
        chat_id = data['message']['chat']['id']
        text = data['message'].get('text', '').strip()
        
        if not text:
            send_message(chat_id, "❌ Введите юзернейм или ID")
            return 'ok', 200
        
        # Убираем команду /start
        if text.startswith('/start'):
            send_message(chat_id, "🔎 Отправьте юзернейм или ID для поиска")
            return 'ok', 200
        
        result = search_user(text)
        send_message(chat_id, result)
        return 'ok', 200

    def send_message(chat_id, text):
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text[:4096],
            'parse_mode': 'Markdown'
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except:
            pass

    @app.route('/set_webhook')
    def set_webhook():
        if not BOT_TOKEN:
            return "❌ BOT_TOKEN не задан"
        
        url = os.environ.get('RENDER_EXTERNAL_URL', '')
        if not url:
            return "❌ RENDER_EXTERNAL_URL не задан"
        
        webhook_url = f"{url}/{BOT_TOKEN}"
        resp = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}")
        return resp.json()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
