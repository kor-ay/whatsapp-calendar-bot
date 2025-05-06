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
    now = datetime.datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d %H:%M")
    for task in list(task_list):
        if task['time'] == now and task['status'] == 'pending':
            message = f"🔔 Hatırlatma: {task['task']}"
            if task.get("assignee"):
                message += f" ({task['assignee']})"
            twilio_client.messages.create(
                body=message,
                from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                to=task['user']
            )
            task['status'] = 'done'
    save_tasks()

scheduler.add_job(check_tasks, 'interval', minutes=1)

@app.route("/webhook", methods=['POST'])
def whatsapp_webhook():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')

    system_prompt = (
        "Sen şirket içi bir WhatsApp asistanısın. Kullanıcılara yardım edersin."
        " Mesajdan görev, tarih ve kişiyi çıkartırsın."
        " Şu formatta yanıt ver: `görev metni | YYYY-MM-DD HH:MM | kişi (isteğe bağlı)`"
        " Eğer tarih yoksa 'Tarih algılanamadı' yaz."
        " Sohbet mesajlarını da anlayabilir, yanıtlayabilirsin."
        " Koray senin ana kullanıcın. Tanıdığın kişiler: Ahmet (tasarımcı), Zeynep (reklam), Can (sosyal medya), Merve (yönetici)."
    )

    try:
        chat = client.chat.completions.create(
            model="gpt-3.5-turbo",
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
                readable_time = parsed_time.strftime("%d %B %Y %H:%M")
                final_reply = f"✅ Görev eklendi: {task_text} ({readable_time}) {f'- {assignee}' if assignee else ''}"
            else:
                final_reply = "📝 Zamanı anlayamadım. Lütfen daha açık yaz."
        elif incoming_msg.lower().startswith("liste"):
            user_tasks = [t for t in task_list if t['user'] == from_number and t['status'] == 'pending']
            if not user_tasks:
                final_reply = "📒 Görev listesi boş."
            else:
                final_reply = "📒 Görevler:\n" + "\n".join([
                    f"{t['task']} - {t['time']} ({t['assignee']})" if t.get('assignee') else f"{t['task']} - {t['time']}"
                    for t in user_tasks
                ])
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
