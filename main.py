from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import dateparser
from googleapiclient.discovery import build
from google.oauth2 import service_account
import os

app = Flask(__name__)

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")

SERVICE_ACCOUNT_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/calendar']
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES)
calendar_service = build('calendar', 'v3', credentials=credentials)

@app.route("/webhook", methods=['POST'])
def whatsapp_webhook():
    incoming_msg = request.values.get('Body', '').strip()
    print(f"Gelen mesaj: {incoming_msg}")
    from_number = request.values.get('From', '')

    date_time = dateparser.parse(incoming_msg, languages=['tr'])

    if date_time:
        event = {
            'summary': 'WhatsApp Hatırlatma',
            'description': f'Gelen mesaj: {incoming_msg}',
            'start': {'dateTime': date_time.isoformat(), 'timeZone': 'Europe/Istanbul'},
            'end': {'dateTime': (date_time.replace(minute=date_time.minute+30)).isoformat(), 'timeZone': 'Europe/Istanbul'},
        }
        calendar_service.events().insert(calendarId='primary', body=event).execute()
        reply = f'📅 Etkinlik eklendi: {date_time.strftime("%d %B %Y %H:%M")}'
    else:
        reply = "⛔️ Tarih/saat algılanamadı. Lütfen '25 Mayıs 14:00' gibi yaz."

    resp = MessagingResponse()
    resp.message(reply)
    return str(resp)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

