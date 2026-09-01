import base64
import io
import firebase_admin
import numpy as np
import face_recognition
from PIL import Image, ImageEnhance, ImageOps
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Optional

from firebase_admin import firestore, auth as firebase_auth
from google.cloud import firestore as google_firestore
from google.cloud.firestore_v1.base_query import FieldFilter

router = APIRouter(prefix="/api/face", tags=["Face Management"])

def get_db():
    app = firebase_admin.get_app()
    return firestore.client(app=app)

class RegisterFaceRequest(BaseModel):
    email: EmailStr
    photoBase64: str
    uid: Optional[str] = None

class RegistrationRequest(BaseModel):
    fullName: str
    email: EmailStr
    password: str
    countryCode: str = "+62"  # Contoh: +62, +1, +65
    phone: Optional[str] = None
    departmentId: str
    photoBase64: str

def convert_and_resize_base64(base64_str: str) -> Image.Image:
    if not base64_str:
        raise HTTPException(status_code=400, detail="Data foto tidak ditemukan.")
    try:
        if "," in base64_str:
            base64_str = base64_str.split(",")[1]
        base64_str = base64_str.strip()
        missing_padding = len(base64_str) % 4
        if missing_padding:
            base64_str += '=' * (4 - missing_padding)

        image_bytes = base64.b64decode(base64_str)
        pil_image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert('RGB')

        max_size = 1200
        if pil_image.width > max_size or pil_image.height > max_size:
            pil_image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        return pil_image
    except Exception as e:
        print(f"[RESIZE ERROR]: {str(e)}")
        raise HTTPException(status_code=400, detail="Format foto tidak valid.")

def detect_and_encode_face(pil_image: Image.Image):
    """Memproses deteksi biometrik wajah & mengekstrak vektor 128-digit."""
    enhancer = ImageEnhance.Contrast(pil_image)
    pil_image = enhancer.enhance(1.1)
    image_np = np.array(pil_image)

    face_locations = face_recognition.face_locations(
        image_np, number_of_times_to_upsample=2, model="hog"
    )

    if not face_locations:
        return None, "Wajah tidak terdeteksi. Pastikan pencahayaan cukup dan wajah menghadap lurus."

    encodings = face_recognition.face_encodings(image_np, face_locations)
    if not encodings:
        return None, "Gagal mengekstrak fitur biometrik wajah."

    return encodings[0].tolist(), None

# --- Endpoints ---
@router.post("/register-self-master")
def register_self_master_face(req: RegisterFaceRequest):
    clean_email = req.email.lower().strip()
    db = get_db()

    pil_image = convert_and_resize_base64(req.photoBase64)
    encoding_list, error_msg = detect_and_encode_face(pil_image)

    if error_msg:
        raise HTTPException(status_code=400, detail=error_msg)

    user_ref = db.collection("users").document(req.uid) if req.uid else None
    if user_ref:
        user_doc = user_ref.get()
        if not user_doc.exists:
            raise HTTPException(status_code=404, detail="Data akun pengguna belum tersedia.")
    else:
        user_docs = (
            db.collection("users")
            .where(filter=FieldFilter("email", "==", clean_email))
            .limit(1)
            .get()
        )
        if not user_docs:
            raise HTTPException(status_code=404, detail="Email pengguna belum terdaftar di database.")
        user_ref = user_docs[0].reference

    user_ref.update({
        "face_encoding": encoding_list,
        "face_registered": True
    })

    return {
        "status": "success",
        "message": "Registrasi wajah berhasil! Anda dapat menggunakan fitur absensi."
    }

def generate_auto_employee_id(db) -> str:
    users_ref = db.collection("users")
    docs = users_ref.get()
    next_number = len(docs) + 1
    return f"TCI-{next_number:02d}"

@router.post("/request-registration")
def request_registration(req: RegistrationRequest):
    clean_email = req.email.lower().strip()
    db = get_db()

    # 1. Cek Email Duplikat di Firestore
    existing_user = (
        db.collection("users")
        .where(filter=FieldFilter("email", "==", clean_email))
        .limit(1)
        .get()
    )
    if existing_user:
        raise HTTPException(
            status_code=400, 
            detail="Email sudah pernah diajukan atau terdaftar."
        )

    # 2. Ekstrak Biometrik Wajah
    pil_image = convert_and_resize_base64(req.photoBase64)
    encoding_list, error_msg = detect_and_encode_face(pil_image)
    if error_msg:
        raise HTTPException(status_code=400, detail=error_msg)

    # 3. Generate Auto Employee ID (TCI-01, TCI-02, dst)
    auto_emp_id = generate_auto_employee_id(db)

    # 4. Format Nomor Telepon Lengkap
    full_phone = f"{req.countryCode}{req.phone.lstrip('0')}" if req.phone else None

    # 5. Buat Akun Firebase Auth & Ambil UID
    try:
        user_record = firebase_auth.create_user(
            email=clean_email,
            password=req.password,
            display_name=req.fullName,
            disabled=False
        )
        user_uid = user_record.uid
    except firebase_auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=400, detail="Email tersebut sudah terdaftar di Firebase Auth.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Gagal membuat akun autentikasi: {str(e)}")

    # 6. Simpan ke Firestore
    db.collection("users").document(user_uid).set({
        "uid": user_uid,
        "fullName": req.fullName,
        "employeeId": auto_emp_id,  # ID Karyawan Otomatis
        "email": clean_email,
        "phone": full_phone,
        "departmentId": req.departmentId,
        "role": "employee",
        "status": "pending_approval",  # Menunggu Persetujuan HR
        "face_encoding": encoding_list,
        "face_registered": True,
        "createdAt": google_firestore.SERVER_TIMESTAMP,
    })

    return {
        "status": "success",
        "employeeId": auto_emp_id,
        "message": f"Pengajuan akun berhasil! ID Karyawan Anda: {auto_emp_id}. Silakan tunggu konfirmasi HRD."
    }