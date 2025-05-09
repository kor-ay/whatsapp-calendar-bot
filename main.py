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

# Tüm işlevler (load_tasks, save_tasks, schedule_task, send_reminder, send_daily_motivation, reschedule_existing_tasks)
# bu alanda yukarıdaki kodda belirtildiği gibi yer almalıdır
# Bu örnekte yalnızca webhook ve system_prompt kısmı gösterilmektedir

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

    # 🔥 Güncel ve zengin system_prompt burada
    system_prompt = f"""
Bugünün tarihi {datetime.datetime.now(pytz.timezone('Europe/Istanbul')).strftime('%Y-%m-%d %H:%M')}.
Sen bir görev yöneticisi ve asistan botsun. WhatsApp üzerinden verilen görevleri anlar, zamanı çıkarır ve kullanıcıya hatırlatacak şekilde planlarsın.
Kullanıcı sana doğal dilde yazabilir:
örneğin: "7 dakika sonra su içmeyi hatırlat" veya "3 gün sonra sabah 7’de ofise git".

Her zaman şu formatta cevap ver:
`görev açıklaması | YYYY-MM-DD HH:MM | kişi (isteğe bağlı)`

Kişiler: {', '.join(personnel)}

Tarih ya da zaman belirsizse 'Tarih algılanamadı' yaz.
Eğer kullanıcı "liste" derse, bekleyen görevleri listele.
"""

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

        # devamı aynı şekilde...

        # ...

    except Exception as e:
        logging.error(f"OpenAI hatası: {e}")
        final_reply = "⛔️ Bir hata oluştu. Lütfen tekrar deneyin."

    twilio_response = MessagingResponse()
    twilio_response.message(final_reply)
    return str(twilio_response)

# Diğer route'lar ve görev yönetim kodları bu noktadan sonra devam eder
