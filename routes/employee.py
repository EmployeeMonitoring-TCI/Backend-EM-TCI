from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import firebase_admin
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

router = APIRouter(prefix="/api/employees", tags=["Employee Management"])

def get_db():
    app = firebase_admin.get_app()
    return firestore.client(app=app)

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