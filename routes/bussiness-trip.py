from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from zoneinfo import ZoneInfo
import firebase_admin
from firebase_admin import auth, firestore
from google.cloud import firestore as google_firestore
from google.cloud.firestore_v1.base_query import FieldFilter

router = APIRouter(prefix="/api/business-trip", tags=["Business Trip Claims"])
bearer_scheme = HTTPBearer(auto_error=False)
JAKARTA_TZ = ZoneInfo("Asia/Jakarta")

def get_db():
    app = firebase_admin.get_app()
    return firestore.client(app=app)

class CreateTripClaimRequest(BaseModel):
    userId: str
    type: str # TRANSPORT | OVERTIME | STANDBY | ALLOWANCE
    transportType: Optional[str] = ""
    claimDate: str # Tanggal Kegiatan/Transaksi
    tripStartDate: Optional[str] = None
    tripEndDate: Optional[str] = None
    clientId: Optional[str] = ""
    clientName: str
    destination: Optional[str] = ""
    purpose: str
    amount: float # Nilai Bruto
    receipts: List[Dict[str, Any]] # Menampung berkas dokumen / foto
    userEmail: str
    userName: Optional[str] = "Karyawan"
    startTime: Optional[str] = None
    endTime: Optional[str] = None
    otHours: Optional[float] = None
    mealAllowance: Optional[float] = None
    allowanceType: Optional[str] = None

class AuditTripClaimRequest(BaseModel):
    status: str # APPROVED | REJECTED

class BulkApproveRequest(BaseModel):
    claim_ids: List[str]
    approved_by: str

class AdminTeamTripRequest(BaseModel):
    leaderId: str = Field(min_length=1)
    destination: str = Field(min_length=1, max_length=250)
    amount: float = Field(gt=0, allow_inf_nan=False)
    purpose: str = Field(default="", max_length=1000)
    transportType: str = Field(default="SPD")
    claimDate: Optional[str] = None
    tripStartDate: Optional[str] = None
    tripEndDate: Optional[str] = None

@router.post("/admin/team-trip")
def create_admin_team_trip(
    req: AdminTeamTripRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Token autentikasi wajib disertakan.")

    try:
        decoded_token = auth.verify_id_token(credentials.credentials)
    except Exception as error:
        raise HTTPException(status_code=401, detail="Token autentikasi tidak valid atau sudah kedaluwarsa.") from error

    db = get_db()
    admin_doc = db.collection("users").document(decoded_token["uid"]).get()
    admin_data = admin_doc.to_dict() or {}
    admin_role = str(admin_data.get("role", "")).strip().lower().replace("_", "-")
    if not admin_doc.exists or admin_role not in {"admin", "hr"}:
        raise HTTPException(status_code=403, detail="Hanya HR/Admin yang dapat mencatat perjalanan bisnis tim.")

    leader_doc = db.collection("users").document(req.leaderId.strip()).get()
    if not leader_doc.exists:
        raise HTTPException(status_code=404, detail="Data leader tidak ditemukan.")

    leader = leader_doc.to_dict() or {}
    leader_role = str(leader.get("role", "")).strip().lower().replace("_", "-")
    if leader_role not in {"leader", "lead", "lead-department"}:
        raise HTTPException(status_code=400, detail="Akun yang dipilih bukan leader atau lead department.")
    if str(leader.get("status", "")).strip().lower() not in {"approved", "active"}:
        raise HTTPException(status_code=400, detail="Akun leader belum aktif.")

    department_id = str(leader.get("departmentId", "")).strip()
    if not department_id:
        raise HTTPException(status_code=400, detail="Leader belum memiliki departemen.")
    destination = req.destination.strip()
    if not destination:
        raise HTTPException(status_code=400, detail="Tujuan perjalanan wajib diisi.")

    transport_type = req.transportType.strip().upper()
    if transport_type not in {"PP", "SPD"}:
        raise HTTPException(status_code=400, detail="Jenis perjalanan harus PP atau SPD.")

    today = datetime.now(JAKARTA_TZ).date()
    if transport_type == "PP":
        if not req.claimDate:
            raise HTTPException(status_code=400, detail="Tanggal kegiatan perjalanan PP wajib diisi.")
        try:
            claim_date = date.fromisoformat(req.claimDate)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Tanggal kegiatan perjalanan tidak valid.") from error
        if claim_date > today:
            raise HTTPException(status_code=400, detail="Tanggal perjalanan tidak boleh melewati hari ini.")
        trip_start_date = None
        trip_end_date = None
    else:
        if not req.tripStartDate or not req.tripEndDate:
            raise HTTPException(status_code=400, detail="Tanggal mulai dan selesai perjalanan SPD wajib diisi.")
        try:
            trip_start_date = date.fromisoformat(req.tripStartDate)
            trip_end_date = date.fromisoformat(req.tripEndDate)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Tanggal perjalanan SPD tidak valid.") from error
        if trip_start_date > today or trip_end_date > today:
            raise HTTPException(status_code=400, detail="Tanggal perjalanan tidak boleh melewati hari ini.")
        if trip_end_date < trip_start_date:
            raise HTTPException(status_code=400, detail="Tanggal selesai tidak boleh sebelum tanggal mulai.")
        claim_date = trip_start_date

    participants = [{
        "userId": leader_doc.id,
        "fullName": str(leader.get("fullName") or leader.get("name") or leader.get("email") or "Leader"),
        "email": str(leader.get("email", "")),
        "role": leader_role,
    }]
    department_users = db.collection("users").where(
        filter=FieldFilter("departmentId", "==", department_id)
    ).stream()
    for user_doc in department_users:
        if user_doc.id == leader_doc.id:
            continue
        user = user_doc.to_dict() or {}
        role = str(user.get("role", "")).strip().lower().replace("_", "-")
        status = str(user.get("status", "")).strip().lower()
        if role not in {"employee", "staff", "karyawan"} or status not in {"approved", "active"}:
            continue
        participants.append({
            "userId": user_doc.id,
            "fullName": str(user.get("fullName") or user.get("name") or user.get("email") or "Karyawan"),
            "email": str(user.get("email", "")),
            "role": role,
        })

    leader_name = str(leader.get("fullName") or leader.get("name") or leader.get("email") or "Leader")
    purpose = req.purpose.strip() or f"Perjalanan bisnis tim {leader_name}"
    trip_ref = db.collection("business_trips").document()
    trip_ref.set({
        "userId": leader_doc.id,
        "userName": leader_name,
        "userEmail": str(leader.get("email", "")).lower().strip(),
        "type": "TRANSPORT",
        "transportType": transport_type,
        "claimDate": claim_date.isoformat(),
        "tripStartDate": trip_start_date.isoformat() if trip_start_date else None,
        "tripEndDate": trip_end_date.isoformat() if trip_end_date else None,
        "clientName": destination,
        "destination": destination,
        "purpose": purpose,
        "amount": req.amount,
        "approvedAmount": req.amount,
        "netTransferred": req.amount,
        "receipts": [],
        "status": "APPROVED",
        "recordSource": "ADMIN_TEAM_TRIP",
        "teamLeaderId": leader_doc.id,
        "teamLeaderName": leader_name,
        "departmentId": department_id,
        "participants": participants,
        "createdBy": decoded_token["uid"],
        "createdByName": str(admin_data.get("fullName") or admin_data.get("name") or ""),
        "createdAt": google_firestore.SERVER_TIMESTAMP,
    })

    return {
        "status": "success",
        "message": "Catatan perjalanan bisnis tim berhasil dibuat.",
        "tripId": trip_ref.id,
        "participantsCount": len(participants),
    }

@router.post("/request")
def request_trip_claim(req: CreateTripClaimRequest):
    claim_type = req.type.upper().strip()
    if claim_type not in ["TRANSPORT", "OVERTIME", "STANDBY", "ALLOWANCE"]:
        raise HTTPException(status_code=400, detail="Tipe klaim tidak valid.")

    transport_type = (req.transportType or "").upper().strip()
    if claim_type == "TRANSPORT" and transport_type not in ["PP", "SPD"]:
        raise HTTPException(status_code=400, detail="Jenis transport harus PP atau SPD.")

    if not req.claimDate.strip():
        raise HTTPException(status_code=400, detail="Tanggal kegiatan/transaksi wajib diisi.")

    trip_start_date = (req.tripStartDate or "").strip()
    trip_end_date = (req.tripEndDate or "").strip()
    if claim_type == "TRANSPORT" and transport_type == "SPD":
        if not trip_start_date or not trip_end_date:
            raise HTTPException(status_code=400, detail="Tanggal mulai dan selesai perjalanan SPD wajib diisi.")
        try:
            parsed_start = date.fromisoformat(trip_start_date)
            parsed_end = date.fromisoformat(trip_end_date)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="Tanggal perjalanan SPD tidak valid.") from error
        if parsed_end < parsed_start:
            raise HTTPException(status_code=400, detail="Tanggal selesai perjalanan tidak boleh sebelum tanggal mulai.")

    if not req.clientName.strip():
        raise HTTPException(status_code=400, detail="Perusahaan client wajib dipilih.")
        
    if not req.receipts:
        raise HTTPException(
            status_code=400, 
            detail="Wajib melampirkan minimal 1 dokumen/nota pendukung."
        )

    db = get_db()
    ref = db.collection("business_trips").document()
    
    ref.set({
        "userId": req.userId,
        "type": claim_type,
        "transportType": transport_type if claim_type == "TRANSPORT" else "",
        "claimDate": req.claimDate.strip(),
        **(
            {"tripStartDate": trip_start_date, "tripEndDate": trip_end_date}
            if claim_type == "TRANSPORT" and transport_type == "SPD"
            else {}
        ),
        "clientId": req.clientId.strip() if req.clientId else "",
        "clientName": req.clientName.strip(),
        "destination": req.destination.strip() if req.destination else "",
        "purpose": req.purpose.strip(),
        "amount": req.amount,
        "receipts": req.receipts,
        "userEmail": req.userEmail.lower().strip(),
        "userName": req.userName,
        "status": "PENDING_FINANCE",
        "createdAt": google_firestore.SERVER_TIMESTAMP,
        **({"startTime": req.startTime, "endTime": req.endTime, "otHours": req.otHours, "mealAllowance": req.mealAllowance} if claim_type == "OVERTIME" else {}),
        **({"allowanceType": req.allowanceType} if claim_type == "ALLOWANCE" else {}),
    })

    return {
        "status": "success",
        "message": "Pengajuan berkas perjalanan bisnis berhasil dibuat.",
        "claimId": ref.id
    }

@router.patch("/{claim_id}/audit")
def audit_trip_claim(claim_id: str, req: AuditTripClaimRequest):
    if req.status not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Status audit tidak valid.")

    db = get_db()
    ref = db.collection("business_trips").document(claim_id)
    doc = ref.get()

    if not doc.exists:
        raise HTTPException(status_code=404, detail="Data pengajuan tidak ditemukan.")

    ref.update({
        "status": req.status,
        "auditedAt": google_firestore.SERVER_TIMESTAMP
    })

    return {
        "status": "success",
        "message": f"Pengajuan berkas berhasil diubah menjadi {req.status}."
    }

@router.post("/finance/bulk-approve")
def finance_bulk_approve(req: BulkApproveRequest):
    """
    Endpoint Backend untuk memproses massal klaim (Bulk Approve) dari HR/Finance
    sekaligus mencatat nominal pencairan.
    """
    db = get_db()
    batch = db.batch()
    
    processed_count = 0
    total_net_payout = 0

    try:
        for claim_id in req.claim_ids:
            claim_ref = db.collection("business_trips").document(claim_id)
            claim_doc = claim_ref.get()

            if not claim_doc.exists:
                continue
                
            data = claim_doc.to_dict()
                
            assert data is not None
            gross_amount = data.get("amount", 0)

            batch.update(claim_ref, {
                "status": "APPROVED",
                "approvedAmount": gross_amount,
                "netTransferred": gross_amount,
                "financeApprovedBy": req.approved_by,
                "processedByFinanceAt": google_firestore.SERVER_TIMESTAMP
            })
            
            processed_count += 1
            total_net_payout += gross_amount

        batch.commit()
        return {
            "status": "success",
            "message": f"Berhasil memproses pencairan untuk {processed_count} pengajuan.",
            "total_net_payout": total_net_payout
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))