#!/usr/bin/env python3
import os
import requests
import time
from flask import Flask, request

BOT_TOKEN = "8702092529:AAE5flVgkhZJCvHJY6IdkfA8zdmWGos3oAs"

app = Flask(__name__)

# === ПОЛЛИНГ ===
def poll():
    print("🔄 Бот запущен в режиме Polling...")
    last_id = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            resp = requests.get(url, params={'offset': last_id + 1, 'timeout': 30}, timeout=35)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('ok'):
                    for update in data.get('result', []):
                        last_id = update['update_id']
                        if 'message' in update:
                            chat_id = update['message']['chat']['id']
                            text = update['message'].get('text', '')
                            send_message(chat_id, f"✅ Я получил: {text}")
            time.sleep(1)
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(5)

def send_message(chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={'chat_id': chat_id, 'text': text}, timeout=10)
    except:
        pass

# === ВЕБ-СЕРВЕР ДЛЯ RENDER ===
@app.route('/')
def home():
    return "✅ Бот работает", 200

if __name__ == '__main__':
    import threading
    threading.Thread(target=poll).start()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
