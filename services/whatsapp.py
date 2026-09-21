import os
import requests
from dotenv import load_dotenv

load_dotenv()

def send_whatsapp_message(phone_number: str, message: str):
    # Ambil token secara dinamis inside function
    fonnte_token = os.getenv("OTP_TOKEN_FONNTE") or os.getenv("FONNTE_TOKEN")
    
    if not fonnte_token:
        print("⚠️ Warning: OTP_TOKEN_FONNTE belum terpasang di .env")
        return {"status": False, "reason": "Token .env belum dikonfigurasi"}

    clean_phone = phone_number.strip().replace("-", "").replace(" ", "").replace("+", "")
    if clean_phone.startswith("0"):
        clean_phone = "62" + clean_phone[1:]

    url = "https://api.fonnte.com/send"
    headers = {
        "Authorization": fonnte_token
    }
    payload = {
        "target": clean_phone,
        "message": f"*Notifikasi Sistem*\n\nPemberitahuan:\n{message}\n\n_Pesan ini dikirim secara otomatis, terimakasih telah mendaftar di sistem kami._",
        "countryCode": "62"
    }

    try:
        response = requests.post(url, data=payload, headers=headers, timeout=10)
        res_data = response.json()
        print(f"📩 Response Fonnte: {res_data}")
        return res_data
    except Exception as e:
        print(f"❌ Error sending WA OTP via Fonnte: {str(e)}")
        return None
