from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import firebase_admin
from firebase_admin import firestore
from google.cloud import firestore as google_firestore

router = APIRouter(prefix="/api/tasks", tags=["Task Management"])

def get_db():
    app = firebase_admin.get_app()
    return firestore.client(app=app)

# --- Pydantic Schemas ---
class CreateTaskRequest(BaseModel):
    title: str
    description: str
    userEmail: str
    userId: Optional[str] = None
    userName: Optional[str] = "Karyawan"

class UpdateTaskStatusRequest(BaseModel):
    status: str  # PENDING | IN_PROGRESS | COMPLETED | REVISION
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    durationMinutes: Optional[int] = None

# --- Endpoints ---

@router.post("/create")
def create_task(req: CreateTaskRequest):
    """
    Endpoint untuk Karyawan mendaftarkan tugas baru di hari itu
    """
    if not req.title.strip() or not req.description.strip():
        raise HTTPException(status_code=400, detail="Judul dan deskripsi tugas wajib diisi.")

    db = get_db()
    task_ref = db.collection("tasks").document()
    
    # Format tanggal hari ini (YYYY-MM-DD)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    task_data = {
        "title": req.title.strip(),
        "description": req.description.strip(),
        "userEmail": req.userEmail.lower().strip(),
        "userId": req.userId,
        "userName": req.userName,
        "date": today_str,
        "status": "PENDING",  # Status awal: PENDING (Belum Dimulai)
        "startTime": None,
        "endTime": None,
        "durationMinutes": 0,
        "createdAt": google_firestore.SERVER_TIMESTAMP,
    }
    
    task_ref.set(task_data)

    return {
        "status": "success",
        "message": "Tugas berhasil dibuat!",
        "taskId": task_ref.id
    }


@router.patch("/{task_id}/status")
def update_task_status(task_id: str, req: UpdateTaskStatusRequest):
    """
    Endpoint untuk mengupdate status pengerjaan beserta rentang waktu (startTime / endTime)
    """
    valid_statuses = ["PENDING", "IN_PROGRESS", "REVISION", "COMPLETED"]
    if req.status not in valid_statuses:
        raise HTTPException(
            status_code=400, 
            detail=f"Status tidak valid. Pilih salah satu dari: {', '.join(valid_statuses)}"
        )

    db = get_db()
    task_ref = db.collection("tasks").document(task_id)
    task_doc = task_ref.get()

    if not task_doc.exists:
        raise HTTPException(status_code=404, detail="Tugas tidak ditemukan.")

    update_payload = {
        "status": req.status,
        "updatedAt": google_firestore.SERVER_TIMESTAMP
    }

    if req.startTime:
        update_payload["startTime"] = req.startTime
    if req.endTime:
        update_payload["endTime"] = req.endTime
    if req.durationMinutes is not None:
        update_payload["durationMinutes"] = req.durationMinutes

    task_ref.update(update_payload)

    return {
        "status": "success",
        "message": f"Status tugas berhasil diperbarui menjadi {req.status}."
    }