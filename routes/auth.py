from email.mime.text import MIMEText
import os
import random
import smtplib
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from firebase_admin import auth
from dotenv import load_dotenv

load_dotenv()

SENDER_EMAIL = os.getenv("SMTP_SENDER_EMAIL", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Store OTP Sementara
otp_store = {}

class SendOTPRequest(BaseModel):
    email: EmailStr

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    newPassword: str

@router.post("/send-otp")
def send_otp(req: SendOTPRequest):
    clean_email = req.email.lower().strip()
    
    try:
        user = auth.get_user_by_email(clean_email)
    except Exception:
        raise HTTPException(status_code=404, detail="Email tidak terdaftar di sistem.")

    otp_code = str(random.randint(100000, 999999))
    expires_at = time.time() + 300  # 5 Menit

    otp_store[clean_email] = {
        "otp": otp_code,
        "expires_at": expires_at
    }

    sender_email = SENDER_EMAIL
    sender_app_password = GMAIL_APP_PASSWORD

    if not sender_email or not sender_app_password:
        raise HTTPException(
            status_code=500,
            detail="SMTP belum dikonfigurasi. Set SMTP_SENDER_EMAIL dan GMAIL_APP_PASSWORD di .env",
        )

    try:
        msg = MIMEText(f"Kode OTP pemulihan kata sandi PT Tri Cipta Integra Anda adalah: {otp_code}\n\nKode ini berlaku selama 5 menit.")
        msg['Subject'] = 'Kode OTP Reset Password - PT Tri Cipta Integra'
        msg['From'] = f"TCI Support <{sender_email}>"
        msg['To'] = clean_email

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_app_password.replace(" ", ""))
        server.sendmail(sender_email, clean_email, msg.as_string())
        server.quit()

        return {"status": "success", "message": "Kode OTP berhasil dikirim ke email."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengirimkan email via SMTP: {str(e)}")

@router.post("/verify-otp")
def verify_otp(req: VerifyOTPRequest):
    clean_email = req.email.lower().strip()
    user_otp = req.otp.strip()

    if clean_email not in otp_store:
        raise HTTPException(status_code=400, detail="Kode OTP tidak ditemukan.")

    stored = otp_store[clean_email]

    if time.time() > stored["expires_at"]:
        del otp_store[clean_email]
        raise HTTPException(status_code=400, detail="Kode OTP telah kadaluarsa (lebih dari 5 menit).")

    if stored["otp"] != user_otp:
        raise HTTPException(status_code=400, detail="Kode OTP tidak sesuai.")

    return {"status": "success", "message": "OTP Valid."}

@router.post("/reset-password-otp")
def reset_password(req: ResetPasswordRequest):
    clean_email = req.email.lower().strip()

    if clean_email not in otp_store or otp_store[clean_email]["otp"] != req.otp.strip():
        raise HTTPException(status_code=400, detail="Sesi verifikasi OTP tidak valid.")

    try:
        user = auth.get_user_by_email(clean_email)
        auth.update_user(user.uid, password=req.newPassword)
        del otp_store[clean_email]
        return {"status": "success", "message": "Kata sandi berhasil diperbarui."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))