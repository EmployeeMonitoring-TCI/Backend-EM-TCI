from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import random
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import firestore
from google.cloud import firestore as google_firestore
from services.whatsapp import send_whatsapp_otp

router = APIRouter(prefix="/api/otp", tags=["OTP Security"])

def get_db():
    app = firebase_admin.get_app()
    return firestore.client(app=app)

class RequestOTP(BaseModel):
    userId: str
    phoneNumber: str

class VerifyOTP(BaseModel):
    userId: str
    otpCode: str

@router.post("/send")
def request_otp(req: RequestOTP):
    """
    Membuat kode OTP 6 digit dan mengirimi pesan WhatsApp
    """
    db = get_db()
    
    # Generate 6 digit angka acak
    otp_code = str(random.randint(100000, 999999))
    
    # Set waktu kadaluarsa 5 menit dari sekarang
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)

    # Simpan OTP ke Firestore 'otp_codes/{userId}'
    otp_ref = db.collection("otp_codes").document(req.userId)
    otp_ref.set({
        "userId": req.userId,
        "phoneNumber": req.phoneNumber,
        "otpCode": otp_code,
        "expiresAt": expires_at.isoformat(),
        "createdAt": google_firestore.SERVER_TIMESTAMP
    })

    # Kirim pesan via WhatsApp API
    wa_response = send_whatsapp_otp(req.phoneNumber, otp_code)

    return {
        "status": "success",
        "whatsappSent": bool(wa_response and wa_response.get("status") is True),
        "message": f"Kode OTP telah dikirimkan via WhatsApp ke {req.phoneNumber}."
    }

@router.post("/verify")
def verify_otp(req: VerifyOTP):
    """
    Memvalidasi kode OTP yang diinputkan pengguna
    """
    db = get_db()
    otp_ref = db.collection("otp_codes").document(req.userId)
    otp_doc = otp_ref.get()

    if not otp_doc.exists:
        raise HTTPException(status_code=400, detail="Kode OTP tidak ditemukan atau belum diminta.")

    otp_data = otp_doc.to_dict()
    
    # 1. Cek Batas Waktu Expired
    expires_at = datetime.fromisoformat(otp_data["expiresAt"]) # type: ignore
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=400, detail="Kode OTP sudah kadaluarsa. Silakan minta kode baru.")

    # 2. Cek Kesesuaian Kode
    if otp_data["otpCode"] != req.otpCode.strip(): # type: ignore
        raise HTTPException(status_code=400, detail="Kode OTP yang Anda masukkan salah.")

    # OTP hanya memverifikasi nomor. Akun tetap menunggu keputusan HR.
    user_ref = db.collection("users").document(req.userId)
    user_ref.update({
        "status": "pending_approval",
        "isPhoneVerified": True,
        "verifiedAt": google_firestore.SERVER_TIMESTAMP
    })

    # Hapus dokumen OTP setelah berhasil diverifikasi
    otp_ref.delete()
    return {
        "status": "success",
        "message": "Akun berhasil diverifikasi!"
    }