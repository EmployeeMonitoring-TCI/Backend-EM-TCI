from typing import Optional

import firebase_admin
from fastapi import APIRouter, Depends, Header, HTTPException
from firebase_admin import auth, firestore
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/profile", tags=["Profile"])


class ProfileUpdate(BaseModel):
    fullName: Optional[str] = Field(default=None, max_length=120)
    phone: Optional[str] = Field(default=None, max_length=30)
    departmentId: Optional[str] = Field(default=None, max_length=120)
    photoURL: Optional[str] = None


def get_db():
    return firestore.client(app=firebase_admin.get_app())


def get_current_uid(authorization: Optional[str] = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Token autentikasi diperlukan.")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Token autentikasi kosong.")
    try:
        decoded_token = auth.verify_id_token(token, clock_skew_seconds=300)
        return decoded_token["uid"]
    except auth.ExpiredIdTokenError as error:
        raise HTTPException(status_code=401, detail="Token autentikasi sudah kadaluarsa.") from error
    except auth.RevokedIdTokenError as error:
        raise HTTPException(status_code=401, detail="Token autentikasi sudah dicabut.") from error
    except auth.InvalidIdTokenError as error:
        print(f"[AUTH] Invalid Firebase ID token: {error}")
        raise HTTPException(status_code=401, detail="Token Firebase tidak valid atau berasal dari project berbeda.") from error
    except Exception as error:
        print(f"[AUTH] Firebase token verification failed: {type(error).__name__}: {error}")
        raise HTTPException(status_code=401, detail="Token autentikasi tidak dapat diverifikasi oleh server.") from error


@router.get("/me")
def get_my_profile(uid: str = Depends(get_current_uid)):
    snapshot = get_db().collection("users").document(uid).get()
    if not snapshot.exists:
        raise HTTPException(status_code=404, detail="Profil pengguna tidak ditemukan.")

    data = snapshot.to_dict() or {}
    data["uid"] = uid
    data["phone"] = data.get("phone", data.get("phoneNumber", ""))
    return {"status": "success", "data": data}


@router.patch("/me")
def update_my_profile(payload: ProfileUpdate, uid: str = Depends(get_current_uid)):
    updates = payload.model_dump(exclude_unset=True)
    if "fullName" in updates and not updates["fullName"].strip():
        raise HTTPException(status_code=400, detail="Nama lengkap tidak boleh kosong.")

    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada data profil yang diubah.")

    if "fullName" in updates:
        updates["fullName"] = updates["fullName"].strip()
        auth.update_user(uid, display_name=updates["fullName"])
    if "phone" in updates:
        updates["phone"] = updates["phone"].strip()
        updates["phoneNumber"] = updates["phone"]

    profile_ref = get_db().collection("users").document(uid)
    profile_ref.update(updates)
    return get_my_profile(uid)