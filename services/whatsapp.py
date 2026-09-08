import os

from dotenv import load_dotenv
import requests

load_dotenv()
FONNTE_TOKEN = os.getenv("OTP_TOKEN_FONNTE")

def send_whatsapp_message(phone_number: str, message: str):
    """
    Mengirimkan pesan WhatsApp OTP menggunakan Fonnte Gateway API
    """
    # 1. Normalisasi Format Nomor HP Indonesia (misal: 0812xxx -> 62812xxx)
    clean_phone = phone_number.strip().replace("-", "").replace(" ", "").replace("+", "")
    if clean_phone.startswith("0"):
        clean_phone = "62" + clean_phone[1:]

    # 3. Request ke API Fonnte
    url = "https://api.fonnte.com/send"
    headers = {
        "Authorization": FONNTE_TOKEN
    }
    payload = {
        "target": clean_phone,
        "message": message,
        "countryCode": "62"
    }

    try:
        response = requests.post(url, data=payload, headers=headers, timeout=10) # type: ignore
        res_data = response.json()
        print(f"📩 Response Fonnte: {res_data}")
        return res_data
    except Exception as e:
        print(f"❌ Error sending WA OTP via Fonnte: {str(e)}")
        return None


def send_whatsapp_otp(phone_number: str, otp_code: str):
    return send_whatsapp_message(
        phone_number,
        f"🔒 *Tri Cipta Integra - Kode Verifikasi*\n\n"
        f"Kode OTP Registrasi Anda adalah: *{otp_code}*\n\n"
        f"Kode ini berlaku selama 5 menit. Harap JANGAN memberikan kode ini kepada siapapun.",
    )