from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import openai
import os
import json
import datetime

app = Flask(__name__)

# API Anahtarları
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

# Basit bir görev listesi (bellekte tutulur, her restart'ta sıfırlanır)
task_list = []

@app.route("/webhook", methods=['POST'])
def whatsapp_webhook():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')

    system_prompt = (
        "Sen bir kişisel asistan botsun. Görevleri hatırlatırsın, görevleri listelersin ve WhatsApp üzerinden verilen görevleri takip edersin. "
        "Eğer kullanıcı yeni bir görev yazarsa, bunu kaydet ve uygun şekilde yanıt ver. "
        "Eğer kullanıcı görevleri görmek istiyorsa, görev listesini yaz."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": incoming_msg}
    ]

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",  # GPT-4 varsa, yoksa 'gpt-3.5-turbo'
            messages=messages,
            temperature=0.5,
            max_tokens=500
        )

        reply = response['choices'][0]['message']['content'].strip()
    except Exception as e:
        reply = f"⛔️ Hata oluştu: {e}"

    twilio_response = MessagingResponse()
    twilio_response.message(reply)
    return str(twilio_response)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
