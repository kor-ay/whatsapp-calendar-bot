from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import json
import os
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

REMINDERS_FILE = 'reminders.json'

if not os.path.exists(REMINDERS_FILE):
    with open(REMINDERS_FILE, 'w') as f:
        json.dump([], f)

def load_reminders():
    with open(REMINDERS_FILE, 'r') as f:
        return json.load(f)

def save_reminders(reminders):
    with open(REMINDERS_FILE, 'w') as f:
        json.dump(reminders, f)

def check_reminders():
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    reminders = load_reminders()
    to_send = [r for r in reminders if r['time'] == now]
    for r in to_send:
        send_whatsapp(r['number'], f"🔔 Hatırlatma: {r['text']}")
        reminders.remove(r)
    save_reminders(reminders)

def send_whatsapp(to, message):
    from twilio.rest import Client
    client = Client(os.environ['TWILIO_ACCOUNT_SID'], os.environ['TWILIO_AUTH_TOKEN'])
    client.messages.create(
        from_=os.environ['TWILIO_PHONE_NUMBER'],
        body=message,
        to=to
    )

@app.route("/webhook", methods=['POST'])
def whatsapp_webhook():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '').replace('whatsapp:', '')

    resp = MessagingResponse()

    try:
        if "|" not in incoming_msg:
            raise ValueError
        time_str, text = incoming_msg.split("|", 1)
        dt = datetime.strptime(time_str.strip(), '%d.%m.%Y %H:%M')
        reminder = {'time': dt.strftime('%Y-%m-%d %H:%M'), 'text': text.strip(), 'number': f'whatsapp:{from_number}'}
        reminders = load_reminders()
        reminders.append(reminder)
        save_reminders(reminders)
        resp.message(f"✅ Hatırlatma ayarlandı: {time_str.strip()} -> {text.strip()}")
    except:
        resp.message("⛔ Format geçersiz. Lütfen şöyle yaz:\n`25.05.2025 14:00 | Toplantı`")

    return str(resp)

# Zamanlayıcı başlat
scheduler = BackgroundScheduler()
scheduler.add_job(check_reminders, 'interval', minutes=1)
scheduler.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
