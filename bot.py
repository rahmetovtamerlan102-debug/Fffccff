#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
from flask import Flask, request, jsonify, render_template_string
from datetime import datetime

app = Flask(__name__)

# === ВСЕ СЕКРЕТЫ ЧЕРЕЗ ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TOKEN = os.environ.get("TELELOG_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELELOG_TOKEN не задан! Установите переменную окружения.")

BASE = os.environ.get("TELELOG_BASE", "https://telelog.info/api/v1")
HEADERS = {"accept": "text/plain", "Authorization": f"Bearer {TOKEN}"}

# === Функции API ===

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

    result = []
    
    username = identifier
    if identifier.isdigit():
        info = fetch(f"/users/basic_info_by_id?req={user_id}")
        if info and info.get('success'):
            data = info.get('data', {})
            if data.get('username'):
                username = f"@{data.get('username')}"
            else:
                username = f"ID: {user_id}"
    
    result.append(f"🔎 Результат поиска по {username}\n")
    
    result.append("👤 Аккаунт Telegram")
    result.append(f"├ ID: {user_id}")
    
    reg_date = get_registration_date(user_id)
    result.append(f"└ Регистрация: {reg_date}")
    
    usernames_data = fetch(f"/users/{user_id}/usernames")
    names_data = fetch(f"/users/{user_id}/names")
    
    changes = []
    
    if usernames_data and usernames_data.get('success'):
        for item in usernames_data.get('data', []):
            changes.append({
                'date': item.get('date_time', ''),
                'username': item.get('name', ''),
                'name': None
            })
    
    if names_data and names_data.get('success'):
        for item in names_data.get('data', []):
            changes.append({
                'date': item.get('date_time', ''),
                'username': None,
                'name': item.get('name', '')
            })
    
    changes.sort(key=lambda x: x['date'], reverse=True)
    
    if changes:
        result.append(f"\n👤 История изменения имени ({len(changes)})")
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
            result.append(line)
    
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
        
        if sent_to:
            result.append(f"\n🎁 Кому отправлял(-а) подарки: {', '.join(sent_to[:3])}")
        if received_from:
            result.append(f"🎁 От кого получал(-а) подарки: {', '.join(received_from[:3])}")
    
    return "\n".join(result)

# === Flask Routes ===

@app.route('/')
def home():
    return '''
    <h1>🔎 Telelog Search Bot</h1>
    <p>Использование:</p>
    <code>/search?q=vnxwi</code> — поиск по юзернейму<br>
    <code>/search?q=8276815852</code> — поиск по ID<br>
    <code>/search?q=vnxwi&raw=true</code> — сырой текст (для ботов)
    <hr>
    <form action="/search" method="get">
        <input type="text" name="q" placeholder="Юзернейм или ID">
        <button type="submit">Найти</button>
    </form>
    '''

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    raw = request.args.get('raw', 'false').lower() == 'true'
    
    if not query:
        return jsonify({"error": "Введите q=username или q=id"}), 400
    
    result = search_user(query)
    
    if raw:
        return result, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Результат поиска</title>
        <meta charset="utf-8">
        <style>
            body { font-family: monospace; background: #0d1117; color: #c9d1d9; padding: 20px; }
            .result { white-space: pre-wrap; background: #161b22; padding: 20px; border-radius: 8px; border: 1px solid #30363d; }
            a { color: #58a6ff; }
        </style>
    </head>
    <body>
        <div class="result">{{ result }}</div>
        <br>
        <a href="/">← Назад</a>
    </body>
    </html>
    ''', result=result)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
