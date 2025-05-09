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

# Logging yapılandırması
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Çevresel değişken kontrolü
required_env_vars = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER", "OPENAI_API_KEY"]
for var in required_env_vars:
    if not os.environ.get(var):
        logging.error(f"Eksik çevresel değişken: {var}")
        raise EnvironmentError(f"Eksik çevresel değişken: {var}")

# API Anahtarları
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
validator = RequestValidator(TWILIO_AUTH_TOKEN)

scheduler = BackgroundScheduler(timezone=pytz.timezone("Europe/Istanbul"))
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
            tasks = json.load(f)
            logging.info(f"tasks.json içeriği: {json.dumps(tasks)}")
            return tasks
    except FileNotFoundError:
        logging.info(f"{tasks_file} bulunamadı, boş liste döndürülüyor.")
        return []
    except json.JSONDecodeError:
        logging.error(f"{tasks_file} geçerli bir JSON dosyası değil.")
        return []
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
    try:
        tz = pytz.timezone("Europe/Istanbul")
        naive_time = datetime.datetime.strptime(task['time'], "%Y-%m-%d %H:%M")
        run_time = tz.localize(naive_time)
        now = datetime.datetime.now(tz)
        if run_time < now:
            logging.info(f"Görev zamanı geçmiş: {task['task']} at {task['time']}, durumu 'done' olarak işaretleniyor.")
            task['status'] = 'done'
            task['triggered_at'] = now.strftime("%Y-%m-%d %H:%M")
            tasks = load_tasks()
            for t in tasks:
                if t['id'] == task['id']:
                    t.update(task)
                    break
            save_tasks(tasks)
            return
        scheduler.add_job(
            func=send_reminder,
            trigger='date',
            run_date=run_time,
            args=[task],
            id=task['id'],
            max_instances=1,
            replace_existing=True
        )
        logging.info(f"Zamanlandı: {task['task']} - {task['time']}, ID: {task['id']}")
        jobs = scheduler.get_jobs()
        logging.info(f"Zamanlanmış görevler: {[str(job) for job in jobs]}")
    except Exception as e:
        logging.error(f"Zamanlama hatası: {e}")

def send_reminder(task):
    logging.info(f"send_reminder tetiklendi: {task['task']}, ID: {task['id']}")
    try:
        if task['status'] != 'pending':
            logging.info(f"Görev zaten tamamlanmış: {task['task']}, durumu: {task['status']}")
            return
        message = f"🔔 Hatırlatma: {task['task']}"
        if task.get("assignee"):
            message += f" ({task['assignee']})"
        twilio_client.messages.create(
            body=message,
            from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
            to=task['user']
        )
        tasks = load_tasks()
        for t in tasks:
            if t['id'] == task['id']:
                t['status'] = 'done'
                t['triggered_at'] = datetime.datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d %H:%M")
                break
        save_tasks(tasks)
        logging.info(f"Görev gönderildi: {message}, ID: {task['id']}")
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
        # Görev listesinden kullanıcıları al
        tasks = load_tasks()
        users = set(task['user'] for task in tasks if 'user' in task)
        for user in users:
            twilio_client.messages.create(
                body=message,
                from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                to=user
            )
        logging.info(f"🎉 Günlük motivasyon mesajı gönderildi: {message}")
    except Exception as e:
        logging.error(f"Motivasyon mesajı hatası: {e}")

def reschedule_existing_tasks():
    tasks = load_tasks()
    for task in tasks:
        if task.get('status') == 'pending':
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
        logging.error("Geçersiz Twilio isteği")
        return "Unauthorized", 403

    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')

    logging.info(f"Gelen mesaj: {incoming_msg}, gönderen: {from_number}")

    if incoming_msg.lower() in ["görevlerim", "liste", "listele", "görevleri listele"]:
        task_list = load_tasks()
        user_tasks = [t for t in task_list if t.get('user') == from_number and t.get('status') == 'pending']
        if not user_tasks:
            reply = "📭 Bekleyen göreviniz yok."
        else:
            reply = "📋 Görevleriniz:\n" + "\n".join([f"- {t['task']} ({t['time']})" for t in user_tasks])
        twilio_response = MessagingResponse()
        twilio_response.message(reply)
        return str(twilio_response)

    system_prompt = (
        f"Bugünün tarihi {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%Y-%m-%d %H:%M')}.\n"
        "Sen bir görev yöneticisi ve asistan botsun. Kullanıcının mesajlarına göre görevleri şu formatta yanıt ver:\n"
        "- Tek seferlik görevler: `görev açıklaması | YYYY-MM-DD HH:MM | kişi (isteğe bağlı)`\n"
        "- Relatif zamanlı görevler (örneğin, '15 dakika sonra'): `görev açıklaması | relatif zaman | kişi (isteğe bağlı)`\n"
        "Tarih veya zaman belirsizse 'Tarih algılanamadı' yaz.\n"
        "Örnekler: 'Toplantı | 2025-05-10 14:00 | Koray', 'Su iç | 15 dakika sonra'.\n"
        f"Kişiler: {', '.join(personnel)}"
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": incoming_msg}
            ]
        )
        reply = response.choices[0].message.content.strip()
        logging.info(f"OpenAI cevabı: {reply}")

        if reply.lower().startswith("tarih algılanamadı"):
            final_reply = "📝 Lütfen bir tarih ve saat içeren görev girin. Örnek: '15 dakika sonra su iç' veya 'yarın 14:00 toplantı'."
        elif "|" in reply:
            parts = [p.strip() for p in reply.split("|")]
            if len(parts) < 2:
                final_reply = "📝 Görev formatı hatalı. Örnek: 'Toplantı | 2025-05-10 14:00 | Koray'."
            else:
                task_text, time_text = parts[0], parts[1]
                assignee = parts[2] if len(parts) > 2 else ""
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
                    tasks = load_tasks()
                    tasks.append(task)
                    save_tasks(tasks)
                    schedule_task(task)
                    final_reply = f"✅ Görev eklendi: {task_text} ({parsed_time.strftime('%d %B %Y %H:%M')}) {f'- {assignee}' if assignee else ''}"
                else:
                    final_reply = "📝 Zamanı anlayamadım. Lütfen '15 dakika sonra' veya 'yarın 14:00' gibi açık bir ifade kullanın."
        else:
            final_reply = reply

    except Exception as e:
        logging.error(f"OpenAI hatası: {e}")
        final_reply = "⛔️ Bir hata oluştu. Lütfen tekrar deneyin."

    twilio_response = MessagingResponse()
    twilio_response.message(final_reply)
    return str(twilio_response)

@app.route("/ping", methods=["GET"])
def ping():
    return "OK", 200

def log_scheduled_jobs():
    jobs = scheduler.get_jobs()
    if not jobs:
        logging.info("Zamanlanmış görev yok.")
    for job in jobs:
        logging.info(f"Zamanlanmış görev: {job.id} - {job.next_run_time}")

# Her sabah 09:00'da motivasyon mesajı
scheduler.add_job(send_daily_motivation, 'cron', hour=9, minute=0, id="daily_motivation")

atexit.register(lambda: scheduler.shutdown())
reschedule_existing_tasks()
log_scheduled_jobs()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
