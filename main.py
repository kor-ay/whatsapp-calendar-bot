from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from openai import OpenAI
import os
import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from twilio.rest import Client
import dateparser
import pytz
import json

app = Flask(__name__)

# API Anahtarları
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

tasks_file = "tasks.json"
personnel = [
    "Koray Yalçın",
    "Taraneh Hafizi",
    "Tannaz Samavatian",
    "Tutia Mohammadaliniah",
    "Ceyhan İrfanoğlu",
    "Özlem Özyurt",
    "Nevin Tekbacak",
    "Dağhan Fellahoğlu"
]

def load_tasks():
    try:
        with open(tasks_file, "r") as f:
            return json.load(f)
    except:
        return []

def save_tasks():
    with open(tasks_file, "w") as f:
        json.dump(task_list, f)

# Görev listesi
task_list = load_tasks()
scheduler = BackgroundScheduler()
scheduler.start()

# Zamanı gelen görevleri kontrol et
def check_tasks():
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    for task in list(task_list):
        task_time = datetime.datetime.strptime(task['time'], "%Y-%m-%d %H:%M").replace(tzinfo=datetime.timezone.utc)
        diff = (task_time - now_utc).total_seconds()
        if 0 <= diff <= 60 and task['status'] == 'pending':
            message = f"🔔 Hatırlatma: {task['task']}"
            if task.get("assignee"):
                message += f" ({task['assignee']})"
            twilio_client.messages.create(
                body=message,
                from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                to=task['user']
            )
            task['status'] = 'done'
            task['triggered_at'] = now_utc.strftime("%Y-%m-%d %H:%M")
    save_tasks()

# Günlük sabah özeti
def send_daily_summary():
    ist_time = datetime.datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d")
    for task in task_list:
        if task['status'] == 'pending' and task['time'].startswith(ist_time):
            twilio_client.messages.create(
                body=f"🗓 Bugünkü görev: {task['task']} - {task['time']}" + (f" ({task['assignee']})" if task.get('assignee') else ""),
                from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                to=task['user']
            )

# Eğlenceli mesajlar ve hatırlatıcılar

def send_fun_messages():
    now = datetime.datetime.now(pytz.timezone("Europe/Istanbul"))
    hour = now.hour
    messages = {
        9: "☀️ Günaydın! Yeni bir gün, yeni başarılar! Hadi başlayalım!",
        12: "🍽️ Ohh be, yemek saati! Enerji toplama vakti.",
        14: "☕ Kahve molası! Yemek sonrası uyku moduna geçmeyelim!",
        16: "🧠 Bir kahve daha içmeli miyiz? Hadi biraz daha odaklanalım.",
        18: "🎉 Mesai bitiyor! Bugün harikaydınız, dinlenmeyi unutmayın."
    }
    if hour in messages:
        for task in task_list:
            if task['status'] == 'pending':
                twilio_client.messages.create(
                    body=messages[hour],
                    from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                    to=task['user']
                )
                break

scheduler.add_job(check_tasks, 'interval', seconds=30)
scheduler.add_job(send_daily_summary, 'cron', hour=8, minute=30, timezone='Europe/Istanbul')
scheduler.add_job(send_fun_messages, 'cron', hour='9,12,14,16,18', minute=0, timezone='Europe/Istanbul')

@app.route("/webhook", methods=['POST'])
def whatsapp_webhook():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')

    istanbul_now = datetime.datetime.now(pytz.timezone("Europe/Istanbul"))
    formatted_now = istanbul_now.strftime("%Y-%m-%d %H:%M")

    system_prompt = (
        f"Bugünün tarihi {formatted_now}. Sen bir görev yöneticisisin ama aynı zamanda sohbet edebilen bir kişisel asistan gibisin.\n"
        "Kullanıcılardan gelen mesajları analiz ederek görev, tarih ve gerekirse ilgili kişiyi çıkartırsın.\n"
        "Cevabını yalnızca şu formatta ver: `görev açıklaması | YYYY-MM-DD HH:MM | kişi (isteğe bağlı)`\n"
        "Tarih yoksa en yakın mantıklı zamanı tahmin et, ama tamamen belirsizse 'Tarih algılanamadı' yaz.\n"
        "Selam, nasılsın, kimim ben gibi sorulara da sıcak şekilde sohbet edebilirsin.\n"
        "Kişi adlarını değiştirme.\n"
        f"Personel listesi: {', '.join(personnel)}\n"
        "Örnek: '5 dakika sonra su iç' → `Su iç | 2025-05-06 15:02`"
    )

    try:
        chat = client.chat.completions.create(
            model="gpt-4-1106-preview",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": incoming_msg}
            ]
        )

        reply = chat.choices[0].message.content.strip()

        if reply.lower().startswith("tarih algılanamadı"):
            final_reply = "📝 Lütfen bir tarih ve saat içeren görev girin. Örneğin: '7 dakika sonra su içmeyi hatırlat'."
        elif "|" in reply:
            parts = [p.strip() for p in reply.split("|")]
            task_text = parts[0]
            time_text = parts[1] if len(parts) > 1 else ""
            assignee = parts[2] if len(parts) > 2 else ""

            now = datetime.datetime.now(pytz.timezone("Europe/Istanbul"))
            parsed_time = dateparser.parse(
                time_text,
                settings={
                    "RELATIVE_BASE": now,
                    "TIMEZONE": "Europe/Istanbul",
                    "TO_TIMEZONE": "UTC",
                    "RETURN_AS_TIMEZONE_AWARE": True
                }
            )

            if parsed_time:
                task_time = parsed_time.astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
                task_list.append({
                    "owner": "Koray",
                    "task": task_text,
                    "time": task_time,
                    "assignee": assignee,
                    "user": from_number,
                    "status": "pending"
                })
                save_tasks()
                readable_time = parsed_time.astimezone(pytz.timezone("Europe/Istanbul")).strftime("%d %B %Y %H:%M")
                final_reply = f"✅ Görev eklendi: {task_text} ({readable_time}) {f'- {assignee}' if assignee else ''}"
            else:
                final_reply = "📝 Zamanı anlayamadım. Lütfen daha açık yaz."
        elif incoming_msg.lower() in ["liste", "görevleri listele"]:
            user_tasks = [t for t in task_list if t['user'] == from_number and t['status'] == 'pending']
            if not user_tasks:
                final_reply = "📒 Görev listesi boş."
            else:
                final_reply = "📒 Görevler:\n" + "\n".join([
                    f"{t['task']} - {t['time']} ({t['assignee']})" if t.get('assignee') else f"{t['task']} - {t['time']}"
                    for t in user_tasks
                ])
        elif incoming_msg.lower() in ["personelleri listele", "çalışanları listele"]:
            final_reply = "👥 Personel Listesi:\n" + "\n".join(personnel)
        else:
            final_reply = reply

    except Exception as e:
        final_reply = f"⛔️ Hata oluştu: {e}"

    twilio_response = MessagingResponse()
    twilio_response.message(final_reply)
    return str(twilio_response)

@app.route("/ping", methods=["GET"])
def ping():
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
