import logging
import atexit
import os
import json
import datetime
import uuid
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from twilio.request_validator import RequestValidator
import openai
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import dateparser
import portalocker
from tenacity import retry, stop_after_attempt, wait_exponential

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
        logging.error(f"Tasks yükleme sırasında genel hata: {e}")
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
        run_time = datetime.datetime.strptime(task['time'], "%Y-%m-%d %H:%M").replace(tzinfo=pytz.timezone("Europe/Istanbul"))
        current_time = datetime.datetime.now(pytz.timezone("Europe/Istanbul"))
        if run_time < current_time:
            logging.info(f"Görev zamanı geçmiş: {task['task']} at {task['time']}, durumu 'done' olarak işaretleniyor.")
            task['status'] = 'done'
            task['triggered_at'] = current_time.strftime("%Y-%m-%d %H:%M")
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
            id=f"reminder_{task['id']}",
            max_instances=1,
            replace_existing=True
        )
        logging.info(f"Görev zamanlandı: {task['task']} at {task['time']}, ID: {task['id']}")
        jobs = scheduler.get_jobs()
        logging.info(f"Zamanlanmış görevler: {[str(job) for job in jobs]}")
    except Exception as e:
        logging.error(f"Görev zamanlama hatası: {e}")

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=5))
def send_twilio_message(user, message):
    return twilio_client.messages.create(
        body=message,
        from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
        to=user
    )

def send_reminder(task):
    try:
        tasks = load_tasks()
        for t in tasks:
            if t['id'] == task['id']:
                if t['status'] != 'pending':
                    logging.info(f"Görev zaten tamamlanmış: {task['task']}, durumu: {t['status']}")
                    return
                message = f"🔔 Hatırlatma: {task['task']}"
                if task.get("assignee"):
                    message += f" ({task['assignee']})"
                send_twilio_message(task['user'], message)
                t['status'] = 'done'
                t['triggered_at'] = datetime.datetime.now(pytz.timezone("Europe/Istanbul")).strftime("%Y-%m-%d %H:%M")
                logging.info(f"Hatırlatma gönderildi: {message}, Görev ID: {task['id']}")
                break
        save_tasks(tasks)
    except Exception as e:
        logging.error(f"Hatırlatma gönderme hatası (Görev ID: {task['id']}): {e}")

def validate_twilio_request():
    signature = request.headers.get('X-Twilio-Signature', '')
    url = request.url
    params = request.form.to_dict()
    return validator.validate(url, params, signature)

@app.route("/webhook", methods=['POST'])
def whatsapp_webhook():
    if not validate_twilio_request():
        logging.error("Geçersiz Twilio isteği")
        return "Unauthorized", 403

    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')

    logging.info(f"Gelen mesaj: {incoming_msg}, gönderen: {from_number}")

    if incoming_msg.lower() in ["görevlerim", "liste", "listele", "görevleri listele"]:
        tasks = load_tasks()
        user_tasks = [t for t in tasks if t.get('user') == from_number and t.get('status') == 'pending']
        if not user_tasks:
            reply = "📭 Bekleyen göreviniz yok."
        else:
            reply = "📋 Görevleriniz:\n" + "\n".join([f"- {t['task']} ({t['time']})" for t in user_tasks])
        twilio_response = MessagingResponse()
        twilio_response.message(reply)
        return str(twilio_response)

    system_prompt = (
        f"Bugünün tarihi {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%Y-%m-%d %H:%M')}."
        " Sen bir görev yöneticisi ve asistan botsun. Cevabını şu formatta ver: `görev açıklaması | YYYY-MM-DD HH:MM | kişi (isteğe bağlı)`"
        " Tarih yoksa en yakın mantıklı zamanı tahmin et, belirsizse 'Tarih algılanamadı' yaz."
        f" Kişiler: {', '.join(personnel)}"
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
            final_reply = "📝 Lütfen bir tarih ve saat içeren görev girin. Örnek: 'Yarın 14:00'te toplantı' veya '5 dakika sonra su iç'."
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
                        "RETURN_AS_TIMEZONE_AWARE": True
                    }
                )
                if parsed_time:
                    task_id = str(uuid.uuid4())
                    task = {
                        "id": task_id,
                        "owner": from_number,
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
                    final_reply = f"✅ {task_text} görevi eklendi ({parsed_time.strftime('%d %B %Y %H:%M')}) {f'- {assignee}' if assignee else ''}"
                else:
                    final_reply = "📝 Zamanı anlayamadım. Örnek: 'Yarın 14:00'te toplantı' veya '5 dakika sonra su iç'."
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

# Uygulama başlatıldığında mevcut görevleri yeniden zamanla
def reschedule_existing_tasks():
    tasks = load_tasks()
    for task in tasks:
        if task.get('status') == 'pending':
            # Eski görevlerde 'id' anahtarı yoksa bir tane oluştur
            if 'id' not in task:
                task['id'] = str(uuid.uuid4())
                tasks = load_tasks()
                for t in tasks:
                    if t['task'] == task['task'] and t['time'] == task['time'] and t['user'] == task['user']:
                        t['id'] = task['id']
                        break
                save_tasks(tasks)
            schedule_task(task)
            logging.info(f"Mevcut görev yeniden zamanlandı: {task['task']}, ID: {task['id']}")

# Uygulama başlatıldığında mevcut görevleri kontrol et ve zamanla
reschedule_existing_tasks()

atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
