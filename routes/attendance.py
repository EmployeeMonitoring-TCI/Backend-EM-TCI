import base64
from datetime import datetime, time
import io
import math
from typing import Optional
import face_recognition
from fastapi import APIRouter, HTTPException, Depends
import numpy as np
from PIL import Image, ImageOps
from pydantic import BaseModel, EmailStr
from firestore_db import get_db
from firebase_admin import firestore
from google.cloud import firestore as google_firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from routes.profile import get_current_uid

router = APIRouter(prefix="/api/attendance", tags=["Attendance"])

db_firestore = get_db()


@router.get("/history")
def get_attendance_history(uid: str = Depends(get_current_uid)):
    """Return the authenticated user's attendance history through Admin SDK."""
    db = get_db()
    user_snapshot = db.collection("users").document(uid).get()
    user_role = str((user_snapshot.to_dict() or {}).get("role", "")).lower()
    attendance_query = db.collection("attendances")
    if user_role not in {"hr", "admin", "leader"}:
        attendance_query = attendance_query.where(filter=FieldFilter("uid", "==", uid))
    docs = attendance_query.stream()

    history = []
    for document in docs:
        data = document.to_dict() or {}
        timestamp = data.get("timestamp")
        if hasattr(timestamp, "isoformat"):
            data["timestamp"] = timestamp.isoformat()
        data["id"] = document.id
        history.append(data)

    return {"status": "success", "data": history}

class AttendanceRequest(BaseModel):
    uid: str
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

def has_already_attended(uid: str, attendance_type: str) -> bool:
    db_firestore = get_db()
    today = datetime.now().date()
    start_of_day = datetime.combine(today, time.min)
    end_of_day = datetime.combine(today, time.max)

    docs = db_firestore.collection("attendances") \
        .where(filter=FieldFilter("uid", "==", uid)) \
        .get()

    for doc in docs:
        data = doc.to_dict() or {}
        timestamp = data.get("timestamp")
        if getattr(timestamp, "tzinfo", None) is not None:
            assert timestamp is not None
            timestamp = timestamp.replace(tzinfo=None)
        if (
            data.get("type") == attendance_type
            and timestamp is not None
            and start_of_day <= timestamp <= end_of_day
        ):
            return True

    return False

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

        # Jarak euclidean antara 2 fitur wajah
        face_distances = face_recognition.face_distance([known_encoding], unknown_encoding)
        match_results = face_recognition.compare_faces([known_encoding], unknown_encoding, tolerance=0.55)

        print(f"[FACE MATCH LOG] Jarak Wajah: {face_distances[0]:.4f} | Cocok: {match_results[0]}")
        return match_results[0]
    except Exception as e:
        print(f"[VERIFY FACE ERROR]: {str(e)}")
        return False

@router.post("/check-in")
def check_in_attendance(req: CheckInRequest):
    clean_email = req.email.lower().strip()

    db_firestore = get_db()
    user_ref = db_firestore.collection("users").document(req.uid)
    user_doc = user_ref.get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="Data pengguna tidak ditemukan.")

    user_data = user_doc.to_dict() or {}
    registered_email = str(user_data.get("email", "")).lower().strip()
    if registered_email != clean_email:
        raise HTTPException(status_code=403, detail="Data pengguna tidak sesuai. Silakan buka ulang aplikasi agar email tersinkronisasi.")

    # 1. CEK APABILA SUDAH CHECK-IN HARI INI
    if has_already_attended(req.uid, "CHECK_IN"):
        raise HTTPException(
            status_code=400,
            detail="Gagal Absen Masuk: Anda sudah melakukan presensi masuk untuk hari ini."
        )

    now = datetime.now()
    current_time = now.time()

    # 2. VALIDASI JAM MASUK (09:00 - 18:00 WIB)
    work_start_time = time(9, 0, 0)
    work_end_time = time(18, 0, 0)

    if not (work_start_time <= current_time < work_end_time):
        raise HTTPException(
            status_code=400,
            detail="Gagal Absen Masuk: Presensi masuk hanya dapat dilakukan pada jam 09:00 - 18:00 WIB."
        )

    # 3. GEOFENCE CHECK
    office_doc = db_firestore.collection("offices").document("main_office").get()
    if office_doc.exists:
        office_data = office_doc.to_dict() or {}
        office_lat = float(office_data.get("latitude", -6.4488101))
        office_lon = float(office_data.get("longitude", 106.7342183))
        radius_limit = float(office_data.get("radius_meters", 100.0))
    else:
        office_lat, office_lon, radius_limit = -6.4488101, 106.7342183, 100.0

    distance_meters = calculate_haversine_distance(req.latitude, req.longitude, office_lat, office_lon)
    if distance_meters > radius_limit:
        raise HTTPException(
            status_code=400,
            detail=f"Gagal Absen Masuk: Di luar area kantor ({int(distance_meters)}m). Maksimal {int(radius_limit)}m."
        )

    # 4. VERIFIKASI USER & WAJAH
    known_encoding = user_data.get("face_encoding")
    if not user_data.get("face_registered") or not known_encoding:
        raise HTTPException(status_code=400, detail="Wajah Anda belum terdaftar.")

    if not req.photoBase64 or not verify_face_match(known_encoding, req.photoBase64):
        raise HTTPException(status_code=400, detail="Gagal Absen Masuk: Wajah tidak sesuai dengan master data terdaftar.")
    
    # 5. CEK KETERLAMBATAN
    is_late = current_time > work_start_time
    late_minutes = 0
    if is_late:
        today_start = datetime.combine(now.date(), work_start_time)
        late_minutes = max(1, int((now - today_start).total_seconds() // 60))

    # 6. SIMPAN KE FIRESTORE
    attendance_ref = db_firestore.collection("attendances").document()
    attendance_data = {
        "uid": req.uid,
        "email": clean_email,
        "status": "SUCCESS",
        "type": "CHECK_IN",
        "timestamp": google_firestore.SERVER_TIMESTAMP,
        "latitude": req.latitude,
        "longitude": req.longitude,
        "distance_meters": round(distance_meters, 2),
        "face_verified": True,
        "isLate": is_late,
        "lateMinutes": late_minutes
    }
    attendance_ref.set(attendance_data)

    if is_late:
        return {
            "status": "warning",
            "isLate": True,
            "lateMinutes": late_minutes,
            "message": f"Kamu terlambat {late_minutes} menit. Absensi tetap berhasil dicatat."
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

    # 1. CEK DUA KONDISI PRASYARAT
    if not has_already_attended(req.uid, "CHECK_IN"):
        raise HTTPException(
            status_code=400,
            detail="Gagal Absen Pulang: Anda belum melakukan presensi masuk hari ini."
        )

    if has_already_attended(req.uid, "CHECK_OUT"):
        raise HTTPException(
            status_code=400,
            detail="Gagal Absen Pulang: Anda sudah melakukan presensi pulang hari ini."
        )

    now = datetime.now()
    current_time = now.time()

    # 2. VALIDASI JAM PULANG (Sesudah 18:00 WIB)
    work_end_time = time(18, 0, 0)
    if current_time < work_end_time:
        raise HTTPException(
            status_code=400,
            detail="Gagal Absen Pulang: Presensi pulang belum dibuka. Absen pulang hanya dapat dilakukan setelah pukul 18:00 WIB."
        )

    # 3. GEOFENCE CHECK
    office_doc = db_firestore.collection("offices").document("main_office").get()
    if office_doc.exists:
        office_data = office_doc.to_dict() or {}
        office_lat = float(office_data.get("latitude", -6.4488101))
        office_lon = float(office_data.get("longitude", 106.7342183))
        radius_limit = float(office_data.get("radius_meters", 100.0))
    else:
        office_lat, office_lon, radius_limit = -6.4488101, 106.7342183, 100.0

    distance_meters = calculate_haversine_distance(req.latitude, req.longitude, office_lat, office_lon)
    if distance_meters > radius_limit:
        raise HTTPException(
            status_code=400,
            detail=f"Gagal Absen Pulang: Di luar area kantor ({int(distance_meters)}m). Maksimal {int(radius_limit)}m."
        )

    # 4. USER & FACE VERIFICATION
    user_doc = db_firestore.collection("users").document(req.uid).get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="Data pengguna tidak ditemukan.")

    user_data = user_doc.to_dict() or {}
    registered_email = str(user_data.get("email", "")).lower().strip()
    if registered_email != clean_email:
        raise HTTPException(status_code=403, detail="Data pengguna tidak sesuai. Silakan buka ulang aplikasi agar email tersinkronisasi.")
    known_encoding = user_data.get("face_encoding")
    if not user_data.get("face_registered") or not known_encoding:
        raise HTTPException(status_code=400, detail="Wajah Anda belum terdaftar.")

    if not req.photoBase64 or not verify_face_match(known_encoding, req.photoBase64):
        raise HTTPException(status_code=400, detail="Gagal Absen Pulang: Wajah tidak sesuai dengan master data terdaftar.")

    # 5. SIMPAN RECORD CHECK_OUT
    attendance_data = {
        "uid": req.uid,
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