from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import os
import json
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client
import dateparser
import pytz

app = Flask(__name__)

# API Anahtarları
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Basit bir görev listesi (bellekte tutulur, her restart'ta sıfırlanır)
task_list = []
scheduler = BackgroundScheduler()
scheduler.start()

# Zamanı gelen görevleri kontrol et ve WhatsApp'tan gönder
def check_tasks():
    now = datetime.datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d %H:%M")
    for task in list(task_list):
        if task['time'] == now:
            twilio_client.messages.create(
                body=f"🔔 Hatırlatma: {task['text']}",
                from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                to=task['user']
            )
            task_list.remove(task)

scheduler.add_job(check_tasks, 'interval', minutes=1)

@app.route("/webhook", methods=['POST'])
def whatsapp_webhook():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')

    # Tarihi doğru timezone ile parse et
    now = datetime.datetime.now(pytz.timezone("Europe/Istanbul"))
    parsed_time = dateparser.parse(
        incoming_msg,
        settings={
            "RELATIVE_BASE": now,
            "TIMEZONE": "Europe/Istanbul",
            "TO_TIMEZONE": "UTC",
            "RETURN_AS_TIMEZONE_AWARE": True
        }
    )

    if parsed_time:
        task_text = incoming_msg
        task_time = parsed_time.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
        task_list.append({"text": task_text, "time": task_time, "user": from_number})
        readable_time = parsed_time.strftime("%d %B %Y %H:%M")
        reply = f"✅ Anladım! {readable_time} tarihinde '{task_text}' görevini hatırlatacağım."
    elif incoming_msg.lower().startswith("liste"):
        user_tasks = [t for t in task_list if t['user'] == from_number]
        if not user_tasks:
            reply = "📒 Görev listesi boş."
        else:
            reply = "📒 Görevler:\n" + "\n".join([f"{t['text']} ({t['time']})" for t in user_tasks])
    else:
        reply = "📝 Lütfen bir tarih ve saat içeren görev girin. Örneğin: '7 dakika sonra su içmeyi hatırlat'."

    twilio_response = MessagingResponse()
    twilio_response.message(reply)
    return str(twilio_response)

@app.route("/ping", methods=["GET"])
def ping():
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
