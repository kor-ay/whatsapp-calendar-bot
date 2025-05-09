import logging
import atexit
import uuid
import random
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import openai
import os
import datetime
import json
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import dateparser
import portalocker
from tenacity import retry, stop_after_attempt, wait_exponential
from twilio.request_validator import RequestValidator

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
validator = RequestValidator(TWILIO_AUTH_TOKEN)

scheduler = BackgroundScheduler(timezone="Europe/Istanbul")
scheduler.start()
tasks_file = "tasks.json"
personnel = [
    "Koray Yalçın", "Taraneh Hafizi", "Tannaz Samavatian",
    "Tutia Mohammadaliniah", "Ceyhan İrfanoğlu", "Özlem Özyurt",
    "Nevin Tekbacak", "Dağhan Fellahoğlu"
]

def load_tasks():
    try:
        with portalocker.Lock(tasks_file, 'r', timeout=5) as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Tasks yükleme hatası: {e}")
        return []

def save_tasks(tasks):
    try:
        with portalocker.Lock(tasks_file, 'w', timeout=5) as f:
            json.dump(tasks, f, indent=2)
        logging.info("Görevler kaydedildi")
    except Exception as e:
        logging.error(f"Tasks kayıt hatası: {e}")

def schedule_task(task):
    tz = pytz.timezone("Europe/Istanbul")
    naive_time = datetime.datetime.strptime(task['time'], "%Y-%m-%d %H:%M")
    run_time = tz.localize(naive_time)
    now = datetime.datetime.now(tz)
    if run_time < now:
        task['status'] = 'done'
        return
    try:
        scheduler.add_job(func=send_reminder, trigger='date', run_date=run_time, args=[task], id=task['id'], max_instances=1)
        logging.info(f"Zamanlandı: {task['task']} - {task['time']}")
    except Exception as e:
        logging.error(f"Zamanlama hatası: {e}")

def send_reminder(task):
    if task['status'] == 'pending':
        message = f"🔔 Hatırlatma: {task['task']}"
        if task.get("assignee"):
            message += f" ({task['assignee']})"
        try:
            twilio_client.messages.create(
                body=message,
                from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                to=task['user']
            )
            task_list = load_tasks()
            for t in task_list:
                if t['id'] == task['id']:
                    t['status'] = 'done'
                    t['triggered_at'] = datetime.datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d %H:%M")
            save_tasks(task_list)
            logging.info(f"Görev gönderildi: {message}")
        except Exception as e:
            logging.error(f"Twilio mesaj hatası: {e}")

def send_daily_motivation():
    motivational_messages = [
        "Yeni bir gün, yeni fırsatlar demek! 💪",
        "Bugün hedeflerine bir adım daha yaklaş!",
        "Başarı küçük adımlarla gelir. İlerle! ✨"
    ]
    message = random.choice(motivational_messages)
    try:
        twilio_client.messages.create(
            body=message,
            from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
            to="whatsapp:+905xxxxxxxxx"
        )
        logging.info("🎉 Günlük motivasyon mesajı gönderildi.")
    except Exception as e:
        logging.error(f"Motivasyon mesajı hatası: {e}")

def reschedule_existing_tasks():
    tasks = load_tasks()
    for task in tasks:
        if task['status'] == 'pending':
            schedule_task(task)
    logging.info(f"Toplam {len(tasks)} görev yeniden zamanlandı.")

def validate_twilio_request():
    signature = request.headers.get('X-Twilio-Signature', '')
    url = request.url
    params = request.form.to_dict()
    return validator.validate(url, params, signature)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=5))
@app.route("/webhook", methods=['POST'])
def whatsapp_webhook():
    if not validate_twilio_request():
        return "Unauthorized", 403

    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')

    if incoming_msg.lower() in ["görevlerim", "liste", "listele", "görevleri listele"]:
        task_list = load_tasks()
        user_tasks = [t for t in task_list if t['user'] == from_number and t['status'] == 'pending']
        reply = "📋 Görevleriniz:\n" + "\n".join([f"{t['task']} ({t['time']})" for t in user_tasks]) if user_tasks else "📭 Bekleyen göreviniz yok."
        twilio_response = MessagingResponse()
        twilio_response.message(reply)
        return str(twilio_response)

    system_prompt = (
        f"Bugünün tarihi {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%Y-%m-%d %H:%M')}.
        Sen bir görev yöneticisi ve asistan botsun. Cevabını şu formatta ver: `görev açıklaması | YYYY-MM-DD HH:MM | kişi (isteğe bağlı)`.
        Kişiler: " + ", ".join(personnel) + ".\n"
        "Relatif zaman ifadelerini (örneğin '15 dakika sonra') anlayabilir ve yorumlayabilirsin.\n"
        "Eğer tekrarlayan görev ise yanıtın sonunda REPEATING yaz."
    )

    try:
        chat = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": incoming_msg}
            ]
        )
        reply = chat.choices[0].message["content"].strip()

        if reply.lower().startswith("tarih algılanamadı"):
            final_reply = "📝 Lütfen bir tarih ve saat içeren görev girin."
        elif "|" in reply:
            parts = [p.strip() for p in reply.split("|")]
            task_text, time_text, assignee = parts[0], parts[1], parts[2] if len(parts) > 2 else ""
            parsed_time = dateparser.parse(
                time_text,
                settings={
                    "RELATIVE_BASE": datetime.datetime.now(pytz.timezone("Europe/Istanbul")),
                    "TIMEZONE": "Europe/Istanbul",
                    "RETURN_AS_TIMEZONE_AWARE": True,
                    "PREFER_DATES_FROM": "future"
                },
                languages=["tr"]
            )
            if parsed_time:
                task_id = str(uuid.uuid4())
                task = {
                    "id": task_id,
                    "owner": "Koray",
                    "task": task_text,
                    "time": parsed_time.strftime("%Y-%m-%d %H:%M"),
                    "assignee": assignee,
                    "user": from_number,
                    "status": "pending"
                }
                task_list = load_tasks()
                task_list.append(task)
                save_tasks(task_list)
                schedule_task(task)
                final_reply = f"✅ Görev eklendi: {task_text} ({parsed_time.strftime('%d %B %Y %H:%M')}) {f'- {assignee}' if assignee else ''}"
            else:
                final_reply = "📝 Zamanı anlayamadım. Lütfen daha açık yaz."
        else:
            final_reply = reply

    except Exception as e:
        logging.error(f"OpenAI hatası: {e}")
        final_reply = "⛔️ Bir hata oluştu."

    twilio_response = MessagingResponse()
    twilio_response.message(final_reply)
    return str(twilio_response)

@app.route("/ping", methods=["GET"])
def ping():
    return "OK", 200

def log_scheduled_jobs():
    for job in scheduler.get_jobs():
        logging.info(f"Zamanlanmış görev: {job.id} - {job.next_run_time}")

# Her sabah 09:00'da motivasyon mesajı
scheduler.add_job(send_daily_motivation, 'cron', hour=9, minute=0, id="daily_motivation")

atexit.register(lambda: scheduler.shutdown())
reschedule_existing_tasks()
log_scheduled_jobs()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
