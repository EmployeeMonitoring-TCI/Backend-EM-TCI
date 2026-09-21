from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from services.whatsapp import send_whatsapp_message
from typing import Optional
import firebase_admin
from firebase_admin import auth, firestore
from google.cloud import firestore as google_firestore
from google.cloud.firestore_v1.base_query import FieldFilter

router = APIRouter(prefix="/api/employees", tags=["Employee Management"])
bearer_scheme = HTTPBearer(auto_error=False)

class ApprovalDecision(BaseModel):
    status: str

class AdminUserCreate(BaseModel):
    fullName: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    role: str = "employee"
    departmentId: str = ""
    phone: str = ""

class AdminUserUpdate(BaseModel):
    userId: Optional[str] = None
    fullName: str = Field(min_length=1, max_length=120)
    email: EmailStr
    role: Optional[str] = None
    departmentId: str = ""
    phone: str = ""
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)

class AdminUserDelete(BaseModel):
    userId: str = Field(min_length=1)

def require_admin(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    if not credentials:
        raise HTTPException(status_code=401, detail="Token autentikasi wajib disertakan.")

    try:
        decoded_token = auth.verify_id_token(credentials.credentials)
    except Exception as error:
        raise HTTPException(status_code=401, detail="Token autentikasi tidak valid atau sudah kedaluwarsa.") from error

    db = get_db()
    user_doc = db.collection("users").document(decoded_token["uid"]).get()
    if not user_doc.exists or (user_doc.to_dict() or {}).get("role") not in {"admin", "hr"}:
        raise HTTPException(status_code=403, detail="Hanya HR/Admin yang dapat mengelola akun pengguna.")
    return decoded_token["uid"]

def validate_role(role: str) -> str:
    normalized_role = role.strip().lower().replace("_", "-")
    if normalized_role not in {"employee", "lead-department", "lead", "leader", "hr", "admin"}:
        raise HTTPException(status_code=400, detail="Role tidak valid.")
    return normalized_role

@router.patch("/{user_id}/approval")
def decide_employee_account(user_id: str, decision: ApprovalDecision):
    if decision.status not in {"approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Status keputusan tidak valid.")

    db = get_db()
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="Data pengguna tidak ditemukan.")

    user_data = user_doc.to_dict() or {}
    user_ref.update({
        "status": decision.status,
        "approvedAt": google_firestore.SERVER_TIMESTAMP,
    })
    db.collection("approval_history").add({
        "userId": user_id,
        "fullName": user_data.get("fullName", ""),
        "email": user_data.get("email", ""),
        "employeeId": user_data.get("employeeId", ""),
        "departmentId": user_data.get("departmentId", ""),
        "role": user_data.get("role", "employee"),
        "status": decision.status,
        "processedAt": google_firestore.SERVER_TIMESTAMP,
    })

    phone = str(user_data.get("phone", "")).strip()
    name = user_data.get("fullName", "Karyawan")
    if decision.status == "approved":
        message = (
            f"✅ *Akun Anda Disetujui*\n\n"
            f"Halo {name}, akun Employee Monitoring Anda telah disetujui oleh HR. "
            f"Silakan login menggunakan email dan kata sandi Anda."
        )
    else:
        message = (
            f"❌ *Pengajuan Akun Ditolak*\n\n"
            f"Halo {name}, pengajuan akun Employee Monitoring Anda ditolak oleh HR. "
            f"Silakan hubungi HR untuk informasi lebih lanjut."
        )

    whatsapp_response = send_whatsapp_message(phone, message) if phone else None
    return {
        "status": "success",
        "whatsappSent": bool(whatsapp_response and whatsapp_response.get("status") is True),
    }

def get_db():
    app = firebase_admin.get_app()
    return firestore.client(app=app)

@router.post("/admin/users/create")
def create_user_by_admin(payload: AdminUserCreate, admin_uid: str = Depends(require_admin)):
    del admin_uid
    clean_email = payload.email.lower().strip()
    role = validate_role(payload.role)
    db = get_db()

    try:
        user_record = auth.create_user(
            email=clean_email,
            password=payload.password,
            display_name=payload.fullName.strip(),
        )
    except auth.EmailAlreadyExistsError as error:
        raise HTTPException(status_code=409, detail="Email sudah digunakan oleh akun lain.") from error
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Gagal membuat akun: {error}") from error

    try:
        db.collection("users").document(user_record.uid).set({
            "uid": user_record.uid,
            "fullName": payload.fullName.strip(),
            "email": clean_email,
            "role": role,
            "departmentId": payload.departmentId.strip(),
            "phone": payload.phone.strip(),
            "status": "approved",
            "createdBy": "admin",
            "createdAt": google_firestore.SERVER_TIMESTAMP,
        })
    except Exception as error:
        auth.delete_user(user_record.uid)
        raise HTTPException(status_code=500, detail=f"Gagal menyimpan profil akun: {error}") from error

    return {"status": "success", "userId": user_record.uid}

@router.post("/admin/users")
def create_user_legacy(payload: AdminUserCreate, admin_uid: str = Depends(require_admin)):
    return create_user_by_admin(payload, admin_uid)

@router.patch("/admin/users/update")
def update_user_by_admin(payload: AdminUserUpdate, admin_uid: str = Depends(require_admin)):
    user_id = (payload.userId or "").strip()
    if not user_id:
        raise HTTPException(status_code=422, detail="userId wajib diisi untuk memperbarui akun.")
    if user_id == admin_uid:
        raise HTTPException(status_code=400, detail="Akun admin yang sedang digunakan tidak dapat diubah dari sini.")

    clean_email = payload.email.lower().strip()
    db = get_db()
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="Data pengguna tidak ditemukan.")

    current_data = user_doc.to_dict() or {}
    current_role = str(current_data.get("role", "employee"))
    role = validate_role(payload.role or current_role)

    try:
        auth_updates = {"email": clean_email, "display_name": payload.fullName.strip()}
        if payload.password:
            auth_updates["password"] = payload.password
        auth.update_user(user_id, **auth_updates)
        user_ref.update({
            "fullName": payload.fullName.strip(),
            "email": clean_email,
            "role": role,
            "departmentId": payload.departmentId.strip(),
            "phone": payload.phone.strip(),
            "updatedAt": google_firestore.SERVER_TIMESTAMP,
        })
    except auth.EmailAlreadyExistsError as error:
        raise HTTPException(status_code=409, detail="Email sudah digunakan oleh akun lain.") from error
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Gagal memperbarui akun: {error}") from error

    return {"status": "success"}

@router.patch("/admin/users/{user_id}")
def update_user_legacy(user_id: str, payload: AdminUserUpdate, admin_uid: str = Depends(require_admin)):
    payload.userId = user_id
    return update_user_by_admin(payload, admin_uid)

@router.post("/admin/users/delete")
def delete_user_by_admin(payload: AdminUserDelete, admin_uid: str = Depends(require_admin)):
    user_id = payload.userId
    if user_id == admin_uid:
        raise HTTPException(status_code=400, detail="Admin tidak dapat menghapus akun yang sedang digunakan.")

    db = get_db()
    user_ref = db.collection("users").document(user_id)
    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="Data pengguna tidak ditemukan.")

    try:
        auth.delete_user(user_id)
        user_ref.delete()
    except auth.UserNotFoundError:
        user_ref.delete()
    except Exception as error:
        raise HTTPException(status_code=400, detail=f"Gagal menghapus akun: {error}") from error

    return {"status": "success"}

@router.delete("/admin/users/{user_id}")
def delete_user_legacy(user_id: str, admin_uid: str = Depends(require_admin)):
    return delete_user_by_admin(AdminUserDelete(userId=user_id), admin_uid)

@router.get("/list")
def get_employee_list(
    search: Optional[str] = None,
    department: Optional[str] = None
):
    """
    Endpoint untuk mengambil daftar karyawan aktif (approved)
    """
    db = get_db()
    try:
        # 1. Kueri dasar untuk mengambil user berstatus 'approved'
        query = db.collection("users").where(filter=FieldFilter("status", "==", "approved"))
        docs = query.get()

        employees = []
        search_lower = search.lower().strip() if search else ""
        dept_lower = department.lower().strip() if department and department != "semua" else ""

        for doc in docs:
            data = doc.to_dict()
            emp_id = doc.id
            assert data is not None
            full_name = data.get("fullName", "")
            email = data.get("email", "")
            employee_code = data.get("employeeId", "")
            dept_id = data.get("departmentId", "")
            role = data.get("role", "employee")
            phone = data.get("phone", "")

            # Filter Search (Nama, Email, atau ID Karyawan)
            matches_search = True
            if search_lower:
                matches_search = (
                    search_lower in full_name.lower() or
                    search_lower in email.lower() or
                    search_lower in employee_code.lower()
                )

            # Filter Departemen
            matches_dept = True
            if dept_lower:
                matches_dept = dept_lower in dept_id.lower()

            if matches_search and matches_dept:
                assert data is not None
                employees.append({
                    "id": emp_id,
                    "fullName": full_name,
                    "email": email,
                    "employeeId": employee_code,
                    "departmentId": dept_id,
                    "role": role,
                    "phone": phone,
                    "status": data.get("status", "approved")
                })

        return {
            "status": "success",
            "total": len(employees),
            "data": employees
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengambil data karyawan: {str(e)}")