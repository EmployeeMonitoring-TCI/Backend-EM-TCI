import datetime
from email.mime.text import MIMEText
import logging
import os
import secrets
import smtplib
from fastapi import APIRouter, HTTPException
import firebase_admin
from pydantic import BaseModel, EmailStr
from firebase_admin import auth, firestore
from typing import Optional

from dotenv import load_dotenv

from services.whatsapp import send_whatsapp_message
load_dotenv()

logger = logging.getLogger(__name__)

SENDER_EMAIL = os.getenv("SMTP_SENDER_EMAIL", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

def get_db():
    try:
        app = firebase_admin.get_app()
    except ValueError:
        cred = firebase_admin.credentials.Certificate("serviceAccountKey.json")
        app = firebase_admin.initialize_app(cred)
    return firestore.client(app=app)

# ==========================================
# MODEL SCHEMAS
# ==========================================
class SendOTPRequest(BaseModel):
    identifier: Optional[str] = None  # Bisa Email atau Nomor Telepon/WhatsApp
    email: Optional[str] = None  # Kompatibilitas client versi lama

class VerifyOTPRequest(BaseModel):
    identifier: str  # Email atau Nomor WhatsApp
    otp: str
    role: str = "employee"  # Pilihan role: 'employee' atau 'lead'

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    newPassword: str


# ==========================================
# HELPER: KIRIM OTP EMAIL SMTP
# ==========================================
def send_email_otp(to_email: str, otp_code: str):
    if not SENDER_EMAIL or not GMAIL_APP_PASSWORD:
        logger.error("OTP email delivery is unavailable because SMTP credentials are not configured.")
        raise HTTPException(
            status_code=503,
            detail="Layanan email OTP belum dikonfigurasi. Hubungi administrator.",
        )

    msg = MIMEText(
        f"Kode Verifikasi Akun PT Tri Cipta Integra Anda adalah: {otp_code}\n\n"
        f"Kode ini berlaku selama 5 menit. Jangan bagikan kode ini kepada siapapun."
    )
    msg["Subject"] = "Kode OTP Verifikasi Akun"
    msg["From"] = SENDER_EMAIL
    msg["To"] = to_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, GMAIL_APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, [to_email], msg.as_string())
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception("OTP email delivery failed.")
        raise HTTPException(
            status_code=502,
            detail="Email OTP gagal dikirim. Silakan coba lagi nanti.",
        )


# ==========================================
# 1. ENDPOINT SEND OTP (WHATSAPP & EMAIL)
# ==========================================
@router.post("/send-otp")
def send_otp(req: SendOTPRequest):
    raw_identifier = req.identifier or req.email or ""
    clean_identifier = raw_identifier.strip().lower()
    if not clean_identifier:
        raise HTTPException(status_code=400, detail="Identifier (Email / No HP) tidak boleh kosong.")

    is_email = "@" in clean_identifier
    if not is_email:
        clean_identifier = clean_identifier.replace(" ", "").replace("-", "")
    otp_code = str(secrets.randbelow(900000) + 100000)
    
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = now + datetime.timedelta(minutes=5)

    try:
        db = get_db()
        otp_ref = db.collection("otp_codes").document(clean_identifier)
        otp_payload = {
            "identifier": clean_identifier,
            "otp": otp_code,
            "expiresAt": expires_at.isoformat(),
            "createdAt": now.isoformat()
        }
        
        otp_ref.set(otp_payload)

    except Exception:
        logger.exception("Failed to persist an OTP in Firestore.")
        raise HTTPException(
            status_code=500, 
            detail="Gagal menyimpan kode OTP. Silakan coba lagi nanti.",
        )

    # Dispatch pengiriman berdasarkan jenis identifier (Email atau WhatsApp)
    gateway_response = None
    if is_email:
        try:
            send_email_otp(clean_identifier, otp_code)
        except HTTPException:
            try:
                otp_ref.delete()
            except Exception:
                logger.exception("Failed to remove an OTP after email delivery failed.")
            raise
    else:
        gateway_response = send_whatsapp_message(clean_identifier, otp_code)
        if not gateway_response or gateway_response.get("status") is not True:
            try:
                otp_ref.delete()
            except Exception:
                logger.exception("Failed to remove an OTP after WhatsApp delivery failed.")
            raise HTTPException(
                status_code=502,
                detail="Kode OTP gagal dikirim melalui WhatsApp. Silakan coba lagi nanti.",
            )

    return {
        "status": "success",
        "message": "Kode verifikasi berhasil dikirim.",
    }


# ==========================================
# 2. ENDPOINT VERIFY OTP
# ==========================================
@router.post("/verify-otp")
def verify_otp(req: VerifyOTPRequest):
    clean_identifier = req.identifier.strip().lower()
    if "@" not in clean_identifier:
        clean_identifier = clean_identifier.replace(" ", "").replace("-", "")
    
    db = get_db()
    otp_ref = db.collection("otp_codes").document(clean_identifier)
    otp_doc = otp_ref.get()

    if not otp_doc.exists:
        raise HTTPException(status_code=400, detail="Kode Verifikasi tidak ditemukan atau belum diminta.")

    otp_data = otp_doc.to_dict()

    # Perbaikan pengecekan waktu kadaluarsa (Handling Timezone UTC offset-aware)
    expires_at = datetime.datetime.fromisoformat(otp_data["expiresAt"]) # type: ignore
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    
    if now_utc > expires_at:
        raise HTTPException(status_code=400, detail="Kode Verifikasi sudah kadaluarsa. Silakan minta ulang.")

    # Cek Kesesuaian Kode Verifikasi
    if otp_data["otp"] != req.otp.strip(): # type: ignore
        raise HTTPException(status_code=400, detail="Kode Verifikasi yang Anda masukkan salah.")

    return {
        "status": "success",
        "message": "Verifikasi Verifikasi berhasil!",
        "role": req.role
    }


# ==========================================
# 3. ENDPOINT RESET PASSWORD VIA OTP
# ==========================================
@router.post("/reset-password-otp")
def reset_password(req: ResetPasswordRequest):
    clean_email = req.email.lower().strip()

    db = get_db()
    otp_ref = db.collection("otp_codes").document(clean_email)
    otp_doc = otp_ref.get()

    if not otp_doc.exists:
        raise HTTPException(status_code=400, detail="Sesi verifikasi Verifikasi tidak ditemukan atau expired.")

    otp_data = otp_doc.to_dict()
    expires_at = datetime.datetime.fromisoformat(otp_data["expiresAt"])  # type: ignore
    if datetime.datetime.now(datetime.timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Kode Verifikasi sudah kadaluarsa. Silakan minta ulang.")

    if otp_data["otp"] != req.otp.strip(): # type: ignore
        raise HTTPException(status_code=400, detail="Kode Verifikasi salah.")

    try:
        user = auth.get_user_by_email(clean_email)
        auth.update_user(user.uid, password=req.newPassword)
        
        # Hapus OTP setelah password berhasil direset
        otp_ref.delete()
        
        return {"status": "success", "message": "Kata sandi berhasil diperbarui."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))