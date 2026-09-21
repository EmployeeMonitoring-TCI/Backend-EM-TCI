from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import firebase_admin
from firebase_admin import firestore
from google.cloud import firestore as google_firestore

router = APIRouter(prefix="/api/business-trip", tags=["Business Trip Claims"])

def get_db():
    app = firebase_admin.get_app()
    return firestore.client(app=app)

class CreateTripClaimRequest(BaseModel):
    userId: str
    type: str # TRANSPORT | OVERTIME | STANDBY | ALLOWANCE
    transportType: Optional[str] = ""
    claimDate: str # Tanggal Kegiatan/Transaksi
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