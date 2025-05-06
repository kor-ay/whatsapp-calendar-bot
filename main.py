from flask import Flask, request
from twilio.rest import Client
from apscheduler.schedulers.background import BackgroundScheduler
import openai
import json
import os
from datetime import datetime

app = Flask(__name__)
reminder_file = reminders.json

# OpenAI (ChatGPT) ayarları
openai.api_key = os.environ.get(OPENAI_API_KEY)

# Twilio ayarları
TWILIO_ACCOUNT_SID = os.environ.get(TWILIO_ACCOUNT_SID)
TWILIO_AUTH_TOKEN = os.environ.get(TWILIO_AUTH_TOKEN)
TWILIO_PHONE_NUMBER = os.environ.get(TWILIO_PHONE_NUMBER)
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Hatırlatma verilerini saklamak için JSON dosyası oluştur
def load_reminders()
    try
        with open(reminder_file, r) as f
            return json.load(f)
    except
        return []

def save_reminders(data)
    with open(reminder_file, w) as f
        json.dump(data, f, indent=2)

# Zamanı gelen hatırlatmaları gönder
def check_reminders()
    now = datetime.now().strftime(%Y-%m-%d %H%M)
    reminders = load_reminders()
    remaining = []
    for r in reminders
        if r[time] == now
            client.messages.create(
                from_=TWILIO_PHONE_NUMBER,
                to=r[to],
                body=f🔔 Hatırlatma zamanı {r['message']}
            )
        else
            remaining.append(r)
    save_reminders(remaining)

# Her dakika kontrol eden zamanlayıcı
scheduler = BackgroundScheduler()
scheduler.add_job(func=check_reminders, trigger=interval, minutes=1)
scheduler.start()

# Webhook WhatsApp mesajı geldiğinde çalışır
@app.route(webhook, methods=[POST])
def whatsapp_webhook()
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')
    print(fGelen mesaj {incoming_msg})

    # ChatGPT'den tarihsaat bulmasını iste
    prompt = fŞu metindeki tarih ve saati net bir şekilde belirt '{incoming_msg}'. Format YYYY-MM-DD HHMM. Sadece tarih ve saati ver, başka bir şey yazma.
    response = openai.ChatCompletion.create(
        model=gpt-3.5-turbo,
        messages=[{role user, content prompt}]
    )

    result = response.choices[0].message.content.strip()

    try
        # Format kontrolü
        reminder_time = datetime.strptime(result, %Y-%m-%d %H%M)
        save_data = load_reminders()
        save_data.append({
            to from_number,
            message incoming_msg,
            time result
        })
        save_reminders(save_data)
        return ✅ Hatırlatma kaydedildi!
    except
        return ⛔️ Tarihsaat algılanamadı. Lütfen net bir tarih ve saat içeren bir mesaj gönder.

if __name__ == __main__
    app.run(host=0.0.0.0, port=10000)
