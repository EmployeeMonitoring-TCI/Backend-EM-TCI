import base64
from datetime import datetime, time
import io
import math
from typing import Optional
import face_recognition
from fastapi import APIRouter, HTTPException
import numpy as np
from PIL import Image, ImageOps
from pydantic import BaseModel, EmailStr
from firestore_db import get_db
from firebase_admin import firestore
from google.cloud import firestore as google_firestore
from google.cloud.firestore_v1.base_query import FieldFilter

router = APIRouter(prefix="/api/attendance", tags=["Attendance"])

db_firestore = get_db()

class AttendanceRequest(BaseModel):
    email: EmailStr
    latitude: float
    longitude: float
    photoBase64: Optional[str] = ""

class CheckInRequest(BaseModel):
    uid: str
    email: str
    photoBase64: str
    latitude: float
    longitude: float

def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    
    return R * c

def verify_face_match(known_encoding_list: list, unknown_base64: str) -> bool:
    """Membandingkan foto selfie dengan face_encoding master di database."""
    try:
        if "," in unknown_base64:
            unknown_base64 = unknown_base64.split(",")[1]

        missing_padding = len(unknown_base64) % 4
        if missing_padding:
            unknown_base64 += '=' * (4 - missing_padding)

        image_data = base64.b64decode(unknown_base64)
        pil_image = ImageOps.exif_transpose(Image.open(io.BytesIO(image_data))).convert('RGB')
        image_np = np.array(pil_image)

        face_locations = face_recognition.face_locations(
            image_np, number_of_times_to_upsample=2, model="hog"
        )
        unknown_encodings = face_recognition.face_encodings(image_np, face_locations)
        if not unknown_encodings:
            return False

        known_encoding = np.array(known_encoding_list)
        unknown_encoding = unknown_encodings[0]

        # Jarak euclidean antara 2 fitur wajah (Threshold default = 0.6)
        face_distances = face_recognition.face_distance([known_encoding], unknown_encoding)
        match_results = face_recognition.compare_faces([known_encoding], unknown_encoding, tolerance=0.55)

        print(f"[FACE MATCH LOG] Jarak Wajah: {face_distances[0]:.4f} | Cocok: {match_results[0]}")
        return match_results[0]
    except Exception as e:
        print(f"[VERIFY FACE ERROR]: {str(e)}")
        return False

@router.post("/check-in")
def check_in_attendance(req: CheckInRequest):
    db_firestore = get_db()
    db = firestore.client()
    now = datetime.now() # Waktu saat absensi dilakukan
    
    # 1. Tentukan batas jam masuk kantor: pukul 09:00:00
    work_start_time = time(9, 0, 0)
    current_time = now.time()
    
    # 2. Cek Apakah Karyawan Terlambat
    is_late = current_time > work_start_time
    
    # Hitung estimasi menit keterlambatan
    late_minutes = 0
    if is_late:
        today_start = datetime.combine(now.date(), work_start_time)
        late_minutes = max(1, int((now - today_start).total_seconds() // 60))

    # 3. Simpan ke Firestore Koleksi 'attendances'
    attendance_ref = db.collection("attendances").document()
    attendance_data = {
        "uid": req.uid,
        "email": req.email,
        "status": "SUCCESS",
        "type": "CHECK_IN",
        "timestamp": google_firestore.SERVER_TIMESTAMP,
        "latitude": req.latitude,
        "longitude": req.longitude,
        "isLate": is_late,             # True jika terlambat
        "lateMinutes": late_minutes     # Jumlah menit terlambat
    }
    attendance_ref.set(attendance_data)

    # 4. Berikan Response dengan Peringatan (Warning)
    if is_late:
        return {
            "status": "warning",
            "isLate": True,
            "lateMinutes": late_minutes,
            "message": f"Kamu terlambat {late_minutes} menit. Absensi tetap berhasil dicatat. (Batas masuk: 09:00)"
        }
    
    return {
        "status": "success",
        "isLate": False,
        "lateMinutes": 0,
        "message": "Absensi tepat waktu berhasil dicatat!"
    }

@router.post("/check-out")
def check_out_attendance(req: AttendanceRequest):
    clean_email = req.email.lower().strip()

    # 1. Geofence Check
    office_doc = db_firestore.collection("offices").document("main_office").get()
    if office_doc.exists:
        office_data = office_doc.to_dict() or {}
        office_lat = float(office_data.get("latitude", -6.868741))
        office_lon = float(office_data.get("longitude", 109.138472))
        radius_limit = float(office_data.get("radius_meters", 100.0))
    else:
        office_lat, office_lon, radius_limit = -6.44871, 106.73431, 100.0

    distance_meters = calculate_haversine_distance(req.latitude, req.longitude, office_lat, office_lon)
    if distance_meters > radius_limit:
        raise HTTPException(
            status_code=400,
            detail=f"Gagal Absen Pulang: Di luar area kantor ({int(distance_meters)}m). Maksimal {int(radius_limit)}m."
        )

    # 2. User & Face Verification
    user_docs = db_firestore.collection("users").where(filter=FieldFilter("email", "==", clean_email)).limit(1).get()
    if not user_docs:
        raise HTTPException(status_code=404, detail="Data pengguna tidak ditemukan.")

    user_data = user_docs[0].to_dict() or {}
    known_encoding = user_data.get("face_encoding")
    if not user_data.get("face_registered") or not known_encoding:
        raise HTTPException(status_code=400, detail="Wajah Anda belum terdaftar.")

    if not req.photoBase64 or not verify_face_match(known_encoding, req.photoBase64):
        raise HTTPException(status_code=400, detail="Gagal Absen Pulang: Wajah tidak sesuai dengan master data terdaftar.")

    # 3. Simpan Record CHECK_OUT
    attendance_data = {
        "email": clean_email,
        "latitude": req.latitude,
        "longitude": req.longitude,
        "distance_meters": round(distance_meters, 2),
        "face_verified": True,
        "timestamp": google_firestore.SERVER_TIMESTAMP,
        "type": "CHECK_OUT",
        "status": "SUCCESS"
    }

    db_firestore.collection("attendances").add(attendance_data)

    return {
        "status": "success",
        "message": f"Absen Pulang Berhasil! Jarak Anda ke kantor: {int(distance_meters)} meter.",
        "distance": round(distance_meters, 2)
    }
