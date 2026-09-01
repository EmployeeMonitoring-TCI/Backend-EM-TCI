from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
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
    userName: Optional[str] = "Karyawan"

class UpdateTaskStatusRequest(BaseModel):
    status: str  # PENDING | IN_PROGRESS | REVISION | COMPLETED

# --- Endpoints ---

@router.post("/create")
def create_task(req: CreateTaskRequest):
    """
    Endpoint untuk Karyawan mengirimkan tugas baru
    """
    if not req.title.strip() or not req.description.strip():
        raise HTTPException(status_code=400, detail="Judul dan deskripsi tugas wajib diisi.")

    db = get_db()
    task_ref = db.collection("tasks").document()
    
    task_data = {
        "title": req.title.strip(),
        "description": req.description.strip(),
        "userEmail": req.userEmail.lower().strip(),
        "userName": req.userName,
        "status": "IN_PROGRESS",  # Status awal pengerjaan
        "createdAt": google_firestore.SERVER_TIMESTAMP,
    }
    
    task_ref.set(task_data)

    return {
        "status": "success",
        "message": "Tugas berhasil dikirimkan!",
        "taskId": task_ref.id
    }


@router.patch("/{task_id}/status")
def update_task_status(task_id: str, req: UpdateTaskStatusRequest):
    """
    Endpoint untuk HR/Manager mengubah status tugas (REVISION / COMPLETED / IN_PROGRESS)
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

    task_ref.update({
        "status": req.status,
        "updatedAt": google_firestore.SERVER_TIMESTAMP
    })

    return {
        "status": "success",
        "message": f"Status tugas berhasil diperbarui menjadi {req.status}."
    }