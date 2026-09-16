from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import firebase_admin
from firebase_admin import firestore
from firebase_admin import storage
from google.cloud import firestore as google_firestore
import pandas as pd
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi import Form
from fastapi.responses import Response
from fpdf import FPDF
from firestore_db import get_db
import io
import uuid

router_projects = APIRouter(prefix="/api/projects", tags=["Projects"])
router_clients = APIRouter(prefix="/api/clients", tags=["Clients"])
router = APIRouter(prefix="/api/tasks", tags=["Task Management"])

def get_db():
    app = firebase_admin.get_app()
    return firestore.client(app=app)

# --- Pydantic Schemas ---
class CreateClientRequest(BaseModel):
    name: str
    company: str

class CreateProjectRequest(BaseModel):
    name: str
    clientId: str
    clientName: str
    internalProduct: str
    picName: str
    startDate: Optional[str] = ""
    deadline: str
    status: Optional[str] = "PLANNING"

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

@router_clients.post("/create")
def create_client(req: CreateClientRequest):
    if not req.name.strip() or not req.company.strip():
        raise HTTPException(status_code=400, detail="Nama PIC dan nama perusahaan wajib diisi.")

    db = get_db()
    client_ref = db.collection("clients").document()
    client_ref.set({
        "name": req.name.strip(),
        "company": req.company.strip(),
        "createdAt": google_firestore.SERVER_TIMESTAMP,
    })

    return {
        "status": "success",
        "message": "Client baru berhasil dibuat.",
        "clientId": client_ref.id,
    }

@router_projects.post("/create")
def create_project(req: CreateProjectRequest):
    if not req.name.strip() or not req.clientId.strip() or not req.deadline.strip():
        raise HTTPException(status_code=400, detail="Nama project, client, dan deadline wajib diisi.")

    db = get_db()
    project_ref = db.collection("projects").document()
    project_ref.set({
        "name": req.name.strip(),
        "clientId": req.clientId.strip(),
        "clientName": req.clientName.strip(),
        "internalProduct": req.internalProduct.strip(),
        "picName": req.picName.strip(),
        "startDate": req.startDate.strip() if req.startDate else "",
        "deadline": req.deadline.strip(),
        "status": req.status or "PLANNING",
        "createdAt": google_firestore.SERVER_TIMESTAMP,
    })

    return {
        "status": "success",
        "message": "Project baru berhasil dibuat.",
        "projectId": project_ref.id,
    }

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

@router_projects.post("/upload-attachment")
async def upload_attachment(
    task_id: str = Form(...),
    file: UploadFile = File(...),
):
    if not task_id.strip() or not file.filename:
        raise HTTPException(status_code=400, detail="Task dan file wajib diisi.")

    try:
        bucket = storage.bucket()
        safe_name = "".join(char if char.isalnum() or char in ".-_" else "_" for char in file.filename)
        object_path = f"tasks/{task_id}/{uuid.uuid4().hex}_{safe_name}"
        blob = bucket.blob(object_path)
        blob.upload_from_file(
            file.file,
            content_type=file.content_type or "application/octet-stream",
        )

        download_token = uuid.uuid4().hex
        blob.metadata = {"firebaseStorageDownloadTokens": download_token}
        blob.patch()

        file_url = (
            f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}/o/"
            f"{object_path.replace('/', '%2F')}?alt=media&token={download_token}"
        )
        return {"status": "success", "fileUrl": file_url, "fileName": file.filename}
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Upload Firebase gagal: {error}") from error

@router_projects.get("/export/csv")
def export_tasks_csv():
    db = get_db()
    tasks = [doc.to_dict() for doc in db.collection("tasks").stream()]
    
    if not tasks:
        raise HTTPException(status_code=404, detail="Tidak ada data tugas.")

    df = pd.DataFrame(tasks)
    csv_data = df.to_csv(index=False)
    
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=Laporan_Tugas.csv"}
    )

@router_projects.get("/export/pdf")
def export_tasks_pdf():
    db = get_db()
    tasks = [doc.to_dict() for doc in db.collection("tasks").stream()]
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Laporan Status Proyek & Tugas", ln=True, align="C") # type: ignore
    
    for t in tasks:
        pdf.cell(200, 10, txt=f"Project: {t.get('projectId', 'N/A')} | Task: {t.get('title', '')} | Status: {t.get('status', '')}", ln=True) # type: ignore
        
    pdf_bytes = pdf.output(dest="S").encode("latin-1") # type: ignore
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=Laporan_Tugas.pdf"}
    )