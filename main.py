from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import dateparser
from googleapiclient.discovery import build
from google.oauth2 import service_account
import json
import os

app = Flask(__name__)

# Load credentials from environment variable
credentials_info = json.loads(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"))
credentials = service_account.Credentials.from_service_account_info(
    credentials_info, scopes=["https://www.googleapis.com/auth/calendar"]
)
calendar_service = build("calendar", "v3", credentials=credentials)

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    print(f"Gelen mesaj: {incoming_msg}")

    date_time = dateparser.parse(incoming_msg, languages=["tr", "en"])

    if date_time:
        event = {
            "summary": "WhatsApp Hatırlatma",
            "description": f"Gelen mesaj: {incoming_msg}",
            "start": {"dateTime": date_time.isoformat(), "timeZone": "Europe/Istanbul"},
            "end": {
                "dateTime": (date_time.replace(minute=date_time.minute + 30)).isoformat(),
                "timeZone": "Europe/Istanbul",
            },
        }
        calendar_service.events().insert(calendarId="primary", body=event).execute()
        reply = f"📅 Etkinlik eklendi: {date_time.strftime('%d %B %Y %H:%M')}"
    else:
        reply = "⛔️ Tarih/saat algılanamadı. Lütfen '25 Mayıs 14:00' gibi yaz."

    resp = MessagingResponse()
    resp.message(reply)
    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
