from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
import random
from datetime import datetime, timedelta, timezone
import firebase_admin
from firebase_admin import firestore
from google.cloud import firestore as google_firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from services.whatsapp import send_whatsapp_message
from services.mailer import send_account_registration_submitted_email, SENDER_EMAIL

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
    wa_response = send_whatsapp_message(req.phoneNumber, otp_code)

    return {
        "status": "success",
        "whatsappSent": bool(wa_response and wa_response.get("status") is True),
        "message": f"Kode OTP telah dikirimkan via WhatsApp ke {req.phoneNumber}."
    }

@router.post("/verify")
def verify_otp(req: VerifyOTP, background_tasks: BackgroundTasks):
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
    user_doc = user_ref.get()
    if not user_doc.exists:
        raise HTTPException(
            status_code=404,
            detail="Data akun tidak ditemukan. Silakan ulangi proses registrasi.",
        )

    try:
        user_ref.update({
            "status": "pending_approval",
            "isPhoneVerified": True,
            "verifiedAt": google_firestore.SERVER_TIMESTAMP
        })

        # Notifikasi Email ke HRD/Admin bahwa ada akun baru yang menunggu approval
        user_data = user_doc.to_dict() or {}
        emp_name = user_data.get("fullName") or "Calon Karyawan"
        emp_email = user_data.get("email") or ""
        emp_phone = user_data.get("phone") or req.phoneNumber
        emp_dept = user_data.get("departmentId") or ""
        emp_id = user_data.get("employeeId") or ""

        admin_emails = [SENDER_EMAIL] if SENDER_EMAIL else []
        try:
            users_ref = db.collection("users")
            for r in ["hr", "admin"]:
                for u in users_ref.where(filter=FieldFilter("role", "==", r)).stream():
                    em = (u.to_dict() or {}).get("email")
                    if em and "@" in em and em.lower().strip() not in admin_emails:
                        admin_emails.append(em.lower().strip())
        except Exception:
            pass

        if admin_emails and emp_email:
            background_tasks.add_task(
                send_account_registration_submitted_email,
                admin_emails=admin_emails,
                employee_name=emp_name,
                employee_email=emp_email,
                phone=emp_phone,
                department_id=emp_dept,
                employee_id=emp_id,
            )
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal memperbarui status akun: {error}",
        )

    # Hapus dokumen OTP setelah berhasil diverifikasi
    otp_ref.delete()
    return {
        "status": "success",
        "message": "Akun berhasil diverifikasi!"
    }