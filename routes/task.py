from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Any, Literal, Optional
from datetime import datetime
import firebase_admin
from firebase_admin import firestore
from firebase_admin import storage
from google.cloud import firestore as google_firestore
import pandas as pd
from fastapi import UploadFile, File, Form
from fastapi.responses import Response
from fpdf import FPDF
from firestore_db import get_db
from routes.profile import get_current_uid
import io
import uuid
from services.mailer import send_task_assignment_email

router_projects = APIRouter(prefix="/api/projects", tags=["Projects"])
router_clients = APIRouter(prefix="/api/clients", tags=["Clients"])
router = APIRouter(prefix="/api/tasks", tags=["Task Management"])

def get_db():
    app = firebase_admin.get_app()
    return firestore.client(app=app)


def get_leader_identity(uid: str = Depends(get_current_uid)) -> dict[str, str]:
    snapshot = get_db().collection("users").document(uid).get()
    if not snapshot.exists:
        raise HTTPException(status_code=403, detail="Akun tidak memiliki profil pengguna.")

    profile = snapshot.to_dict() or {}
    role = str(profile.get("role") or "").strip().lower().replace("_", "-")
    if role not in {"leader", "lead", "lead-department", "hr", "admin"}:
        raise HTTPException(status_code=403, detail="Aksi ini hanya tersedia untuk Leader atau HR.")

    return {
        "uid": uid,
        "role": role,
        "email": str(profile.get("email") or "").strip().lower(),
        "name": str(profile.get("fullName") or profile.get("name") or profile.get("email") or "Leader").strip(),
        "departmentId": str(
            profile.get("departmentId")
            or profile.get("department")
            or profile.get("departmentName")
            or ""
        ).strip(),
    }


class LeaderTaskAssignmentRequest(BaseModel):
    title: str
    description: str
    projectId: str
    assignmentType: Literal["department", "employee"]
    detailTask: Optional[str] = ""
    mandays: Optional[str] = ""
    endpointApi: Optional[str] = ""
    projectName: Optional[str] = ""
    clientName: Optional[str] = ""
    internalProduct: Optional[str] = ""
    departmentId: Optional[str] = ""
    departmentName: Optional[str] = ""
    departmentLeadId: Optional[str] = ""
    assignedToId: Optional[str] = ""
    assignedToName: Optional[str] = ""
    assignedToEmail: Optional[str] = ""
    assignedEmployeeIds: Optional[list[str]] = None
    userName: Optional[str] = ""
    userEmail: Optional[str] = ""
    priority: Optional[Literal["LOW", "MEDIUM", "HIGH"]] = "MEDIUM"
    startDate: Optional[str] = ""
    deadline: Optional[str] = ""
    relatedTaskId: Optional[str] = ""
    relatedTaskTitle: Optional[str] = ""
    # Legacy clients used hierarchy fields for a task relation.
    parentTaskId: Optional[str] = ""
    parentTaskTitle: Optional[str] = ""
    rootTaskId: Optional[str] = ""


def collect_task_tree(db: Any, initial_tasks: list[Any]) -> list[Any]:
    task_docs: dict[str, Any] = {}
    pending = list(initial_tasks)

    while pending:
        task_doc = pending.pop()
        if task_doc.id in task_docs:
            continue
        task_docs[task_doc.id] = task_doc
        for field in ("parentTaskId", "rootTaskId"):
            pending.extend(
                child
                for child in db.collection("tasks").where(field, "==", task_doc.id).stream()
                if child.id not in task_docs
            )

    return list(task_docs.values())


def archive_task_docs(db: Any, task_docs: list[Any], identity: dict[str, str]) -> int:
    active_docs = [
        task_doc
        for task_doc in task_docs
        if not (task_doc.to_dict() or {}).get("isArchived")
    ]
    for offset in range(0, len(active_docs), 450):
        batch = db.batch()
        for task_doc in active_docs[offset : offset + 450]:
            batch.update(task_doc.reference, {
                "isArchived": True,
                "archivedAt": google_firestore.SERVER_TIMESTAMP,
                "archivedByUid": identity["uid"],
                "archivedByEmail": identity["email"],
                "archivedByName": identity["name"],
            })
        batch.commit()
    return len(active_docs)


@router.post("/leader-assignment")
def create_leader_assignment(
    req: LeaderTaskAssignmentRequest,
    identity: dict[str, str] = Depends(get_leader_identity),
):
    if not req.title.strip() or not req.description.strip() or not req.projectId.strip():
        raise HTTPException(status_code=400, detail="Judul, brief, dan project wajib diisi.")

    db = get_db()
    project_ref = db.collection("projects").document(req.projectId.strip())
    project_snapshot = project_ref.get()
    if not project_snapshot.exists or (project_snapshot.to_dict() or {}).get("isArchived"):
        raise HTTPException(status_code=404, detail="Project tidak ditemukan atau sudah diarsipkan.")

    department_id = (req.departmentId or "").strip()
    department_lead_id = ""
    assigned_to_id = (req.assignedToId or "").strip()
    assigned_to_email = (req.assignedToEmail or "").strip().lower()
    employee = None
    employees = []
    department_lead = None
    if req.assignmentType == "employee":
        employee_ids = list(dict.fromkeys(
            employee_id.strip()
            for employee_id in (req.assignedEmployeeIds or [assigned_to_id])
            if employee_id and employee_id.strip()
        ))
        if not employee_ids:
            raise HTTPException(status_code=400, detail="Penerima employee belum lengkap.")
        if assigned_to_id and assigned_to_id != employee_ids[0]:
            raise HTTPException(status_code=400, detail="Penerima utama harus menjadi employee pertama dalam daftar.")
        assigned_to_id = employee_ids[0]
        for employee_id in employee_ids:
            employee_snapshot = db.collection("users").document(employee_id).get()
            assigned_employee = employee_snapshot.to_dict() if employee_snapshot.exists else None
            employee_role = str((assigned_employee or {}).get("role") or "").strip().lower().replace("_", "-")
            employee_email = str((assigned_employee or {}).get("email") or "").strip().lower()
            if employee_role not in {"employee", "karyawan", "staff"} or not employee_email:
                raise HTTPException(status_code=400, detail="Semua penerima harus merupakan employee terdaftar dengan email.")
            if employee_id == assigned_to_id and assigned_to_email and employee_email != assigned_to_email:
                raise HTTPException(status_code=400, detail="Email penerima utama tidak sesuai dengan data employee.")
            employee_department_id = str(
                (assigned_employee or {}).get("departmentId")
                or (assigned_employee or {}).get("department")
                or (assigned_employee or {}).get("departmentName")
                or ""
            ).strip()
            if employee_id == assigned_to_id:
                if department_id and department_id != employee_department_id:
                    raise HTTPException(status_code=400, detail="Department assignment tidak sesuai dengan data employee.")
                department_id = employee_department_id
            employees.append({
                "id": employee_id,
                "fullName": str((assigned_employee or {}).get("fullName") or (assigned_employee or {}).get("name") or employee_email).strip(),
                "email": employee_email,
                "departmentId": employee_department_id,
                "departmentName": str(
                    (assigned_employee or {}).get("departmentName")
                    or (assigned_employee or {}).get("department")
                    or employee_department_id
                ).strip(),
            })
        employee = db.collection("users").document(assigned_to_id).get().to_dict() or {}
        assigned_to_email = str(employee.get("email") or "").strip().lower()
    else:
        department_lead_id = (req.departmentLeadId or "").strip()
        if not department_lead_id:
            raise HTTPException(status_code=400, detail="Penerima Lead Department atau Leader wajib dipilih.")
        lead_snapshot = db.collection("users").document(department_lead_id).get()
        department_lead = lead_snapshot.to_dict() if lead_snapshot.exists else None
        lead_role = str((department_lead or {}).get("role") or "").strip().lower().replace("_", "-")
        if lead_role not in {"leader", "lead", "lead-department"}:
            raise HTTPException(status_code=400, detail="Penerima harus merupakan akun Leader atau Lead Department terdaftar.")
        lead_department_id = str(
            (department_lead or {}).get("departmentId")
            or (department_lead or {}).get("department")
            or (department_lead or {}).get("departmentName")
            or ""
        ).strip()
        if department_id and lead_department_id and department_id != lead_department_id:
            raise HTTPException(status_code=400, detail="Department tujuan tidak sesuai dengan Lead yang dipilih.")
        department_id = lead_department_id or department_id
        if lead_role != "leader" and not department_id:
            raise HTTPException(status_code=400, detail="Department tujuan wajib dipilih.")

    if identity["role"] == "lead-department":
        own_department = identity["departmentId"]
        if not own_department or department_id != own_department:
            raise HTTPException(status_code=403, detail="Task hanya dapat dibuat untuk department Anda.")
        if req.assignmentType == "employee" and not department_id:
            raise HTTPException(status_code=403, detail="Employee tujuan belum terdaftar di department Anda.")
        if req.assignmentType == "employee" and any(
            assigned_employee["departmentId"] != own_department for assigned_employee in employees
        ):
            raise HTTPException(status_code=403, detail="Semua employee tujuan harus berasal dari department Anda.")

    project = project_snapshot.to_dict() or {}
    task_ref = db.collection("tasks").document()
    task_data = {
        "title": req.title.strip(),
        "detailTask": (req.detailTask or "").strip(),
        "mandays": (req.mandays or "").strip(),
        "endpointApi": (req.endpointApi or "").strip(),
        "description": req.description.strip(),
        "projectId": req.projectId.strip(),
        "projectName": project.get("name") or req.projectName or "",
        "clientName": project.get("clientName") or req.clientName or "",
        "internalProduct": project.get("internalProduct") or req.internalProduct or "",
        "assignmentType": req.assignmentType,
        "departmentId": department_id,
        "departmentName": str(
            (employee or {}).get("departmentName")
            or (employee or {}).get("department")
            or (department_lead or {}).get("departmentName")
            or (department_lead or {}).get("department")
            or req.departmentName
            or ""
        ).strip(),
        "departmentLeadId": department_lead_id,
        "priority": req.priority or "MEDIUM",
        "startDate": (req.startDate or "").strip(),
        "deadline": (req.deadline or "").strip(),
        "status": "PENDING",
        "createdByRole": identity["role"],
        "createdByUid": identity["uid"],
        "createdByEmail": identity["email"],
        "assignedByUid": identity["uid"],
        "assignedByEmail": identity["email"],
        "sourceLeaderEmail": identity["email"],
        "attachments": [],
        "createdAt": google_firestore.SERVER_TIMESTAMP,
    }
    if req.assignmentType == "employee":
        task_data.update({
            "assignedToId": assigned_to_id,
            "userId": assigned_to_id,
            "assignedToName": str((employee or {}).get("fullName") or (employee or {}).get("name") or req.assignedToName or req.userName or "").strip(),
            "assignedToEmail": assigned_to_email,
            "userName": str((employee or {}).get("fullName") or (employee or {}).get("name") or req.userName or req.assignedToName or "").strip(),
            "userEmail": assigned_to_email,
            "assignedEmployees": employees,
        })
    else:
        task_data["departmentLeadEmail"] = str((department_lead or {}).get("email") or "").strip().lower()

    related_task_id = (req.relatedTaskId or req.parentTaskId or "").strip()
    if related_task_id:
        related_snapshot = db.collection("tasks").document(related_task_id).get()
        if not related_snapshot.exists or (related_snapshot.to_dict() or {}).get("isArchived"):
            raise HTTPException(status_code=404, detail="Task yang direlasikan tidak ditemukan atau sudah diarsipkan.")
        related_task = related_snapshot.to_dict() or {}
        task_data["relatedTaskId"] = related_task_id
        task_data["relatedTaskTitle"] = str(
            related_task.get("title") or req.relatedTaskTitle or req.parentTaskTitle or ""
        ).strip()

    task_ref.set(task_data)
    return {"status": "success", "taskId": task_ref.id}


@router_projects.patch("/{project_id}/archive")
def archive_project(
    project_id: str,
    identity: dict[str, str] = Depends(get_leader_identity),
):
    db = get_db()
    project_ref = db.collection("projects").document(project_id)
    project_snapshot = project_ref.get()
    if not project_snapshot.exists:
        raise HTTPException(status_code=404, detail="Project tidak ditemukan.")
    if (project_snapshot.to_dict() or {}).get("isArchived"):
        return {"status": "success", "archivedTaskCount": 0}

    project_tasks = list(db.collection("tasks").where("projectId", "==", project_id).stream())
    task_docs = collect_task_tree(db, project_tasks)
    archived_task_count = archive_task_docs(db, task_docs, identity)
    project_ref.update({
        "isArchived": True,
        "archivedAt": google_firestore.SERVER_TIMESTAMP,
        "archivedByUid": identity["uid"],
        "archivedByEmail": identity["email"],
        "archivedByName": identity["name"],
    })
    return {"status": "success", "archivedTaskCount": archived_task_count}


@router.patch("/{task_id}/archive")
def archive_task(
    task_id: str,
    identity: dict[str, str] = Depends(get_leader_identity),
):
    db = get_db()
    task_snapshot = db.collection("tasks").document(task_id).get()
    if not task_snapshot.exists:
        raise HTTPException(status_code=404, detail="Task tidak ditemukan.")

    task_docs = collect_task_tree(db, [task_snapshot])
    archived_task_count = archive_task_docs(db, task_docs, identity)
    return {"status": "success", "archivedTaskCount": archived_task_count}

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

@router_clients.delete("/{client_id}")
def delete_client(
    client_id: str,
    identity: dict[str, str] = Depends(get_leader_identity),
):
    db = get_db()
    client_ref = db.collection("clients").document(client_id)
    if not client_ref.get().exists:
        raise HTTPException(status_code=404, detail="Client tidak ditemukan.")

    active_projects = [
        project
        for project in db.collection("projects").where("clientId", "==", client_id).stream()
        if not (project.to_dict() or {}).get("isArchived")
    ]
    if active_projects:
        raise HTTPException(
            status_code=409,
            detail=f"Client masih digunakan oleh {len(active_projects)} project aktif.",
        )

    client_ref.delete()
    return {"status": "success", "message": "Client berhasil dihapus."}

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
def create_task(req: CreateTaskRequest, background_tasks: BackgroundTasks):
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

    if req.userEmail and "@" in req.userEmail:
        background_tasks.add_task(
            send_task_assignment_email,
            task_id=task_ref.id,
            task_title=req.title.strip(),
            task_description=req.description.strip(),
            assigned_to_email=req.userEmail.lower().strip(),
            assigned_to_name=req.userName or "Karyawan",
            assigned_by_name="Leader",
        )

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
    daily_reports = [doc.to_dict() for doc in db.collection("task_daily_reports").stream()]

    export_rows = []

    for task in tasks:
        assert task is not None
        export_rows.append({
            "source": "task",
            "taskId": task.get("id") or task.get("taskId") or "",
            "rootTaskId": task.get("rootTaskId") or "",
            "projectId": task.get("projectId") or "",
            "projectName": task.get("projectName") or "",
            "title": task.get("title") or "",
            "description": task.get("description") or "",
            "status": task.get("status") or "",
            "employeeName": task.get("userName") or task.get("assignedToName") or task.get("employeeName") or "",
            "employeeEmail": task.get("userEmail") or task.get("assignedToEmail") or task.get("employeeEmail") or "",
            "workDate": task.get("workDate") or task.get("date") or "",
            "submittedAt": task.get("submittedAt") or "",
            "reportDescription": "",
        })

    for report in daily_reports:
        assert report is not None
        export_rows.append({
            "source": "daily_report",
            "taskId": report.get("taskId") or "",
            "rootTaskId": report.get("rootTaskId") or report.get("taskId") or "",
            "projectId": report.get("projectId") or "",
            "projectName": report.get("projectName") or "",
            "title": report.get("taskTitle") or "",
            "description": report.get("description") or report.get("taskTitle") or "",
            "status": "DAILY_REPORT",
            "employeeName": report.get("employeeName") or "",
            "employeeEmail": report.get("employeeEmail") or "",
            "workDate": report.get("workDate") or "",
            "submittedAt": report.get("submittedAt") or "",
            "reportDescription": report.get("description") or "",
        })

    if not export_rows:
        raise HTTPException(status_code=404, detail="Tidak ada data tugas atau daily report.")

    df = pd.DataFrame(export_rows)
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
    daily_reports = [doc.to_dict() for doc in db.collection("task_daily_reports").stream()]

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="Laporan Status Proyek & Tugas", ln=True, align="C") # type: ignore

    for task in tasks:
        pdf.cell(200, 10, txt=f"Project: {task.get('projectId', 'N/A')} | Task: {task.get('title', '')} | Status: {task.get('status', '')}", ln=True) # type: ignore

    for report in daily_reports:
        pdf.cell(200, 10, txt=f"Daily Report: {report.get('employeeName', 'Unknown')} | {report.get('taskTitle', report.get('title', ''))} | {report.get('workDate', '')}", ln=True) # type: ignore

    pdf_bytes = pdf.output(dest="S").encode("latin-1") # type: ignore

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=Laporan_Tugas.pdf"}
    )