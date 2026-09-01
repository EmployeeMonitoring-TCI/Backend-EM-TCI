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
    destination: str
    purpose: str
    receipts: List[Dict[str, Any]] # Menampung berkas dokumen / foto
    userEmail: str
    userName: Optional[str] = "Karyawan"

class AuditTripClaimRequest(BaseModel):
    status: str # APPROVED | REJECTED

@router.post("/request")
def request_trip_claim(req: CreateTripClaimRequest):
    if not req.receipts:
        raise HTTPException(
            status_code=400, 
            detail="Wajib melampirkan minimal 1 dokumen/nota pendukung."
        )

    db = get_db()
    ref = db.collection("business_trips").document()
    
    ref.set({
        "destination": req.destination.strip(),
        "purpose": req.purpose.strip(),
        "receipts": req.receipts,
        "userEmail": req.userEmail.lower().strip(),
        "userName": req.userName,
        "status": "PENDING",
        "createdAt": google_firestore.SERVER_TIMESTAMP,
    })

    return {
        "status": "success",
        "message": "Pengajuan berkas perjalanan bisnis berhasil dibuat.",
        "claimId": ref.id
    }

@router.patch("/{claim_id}/audit")
def audit_trip_claim(claim_id: str, req: AuditTripClaimRequest):
    if req.status not in ["APPROVED", "REJECTED"]:
        raise HTTPException(status_code=400, detail="Status audit tidak valid (APPROVED / REJECTED).")

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