import os
import requests
import firebase_admin
from firebase_admin import credentials, auth

CREDENTIAL_PATH = "serviceAccountKey.json"

if not os.path.exists(CREDENTIAL_PATH):
    raise FileNotFoundError(f"File '{CREDENTIAL_PATH}' tidak ditemukan!")

# 1. Inisialisasi Firebase Admin untuk Auth & Mengambil Access Token
cred = credentials.Certificate(CREDENTIAL_PATH)
try:
    firebase_admin.get_app()
except ValueError:
    firebase_admin.initialize_app(cred)

def create_hr_account(email, password, full_name):
    clean_email = email.lower().strip()
    
    try:
        # A. Dapatkan atau Buat User di Firebase Auth
        try:
            user_record = auth.get_user_by_email(clean_email)
            user_uid = user_record.uid
            print(f"🔑 User Auth ditemukan. UID: {user_uid}")
        except auth.UserNotFoundError:
            user_record = auth.create_user(
                email=clean_email,
                password=password,
                display_name=full_name
            )
            user_uid = user_record.uid
            print(f"✅ User Auth baru berhasil dibuat. UID: {user_uid}")

        # B. Dapatkan Access Token & Project ID dari Service Account
        access_token = cred.get_access_token().access_token
        project_id = cred.project_id

        # C. Tulis Langsung ke Firestore via REST API (Mem-bypass SDK yang Buggy)
        url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/users/{user_uid}?updateMask.fieldPaths=uid&updateMask.fieldPaths=fullName&updateMask.fieldPaths=email&updateMask.fieldPaths=role&updateMask.fieldPaths=status&updateMask.fieldPaths=departmentId"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "fields": {
                "uid": {"stringValue": user_uid},
                "fullName": {"stringValue": full_name},
                "email": {"stringValue": clean_email},
                "role": {"stringValue": "hr"},
                "status": {"stringValue": "approved"},
                "departmentId": {"stringValue": "hr"}
            }
        }

        response = requests.patch(url, json=payload, headers=headers)

        if response.status_code == 200:
            print(f"🎉 SUKSES SANGAT! Dokumen Firestore untuk HR ({clean_email}) berhasil dibuat!")
            print(f"👉 ID Dokumen: {user_uid}")
        else:
            print(f"❌ Gagal Firestore REST API ({response.status_code}): {response.text}")

    except Exception as e:
        print(f"❌ Error: {str(e)}")

if __name__ == "__main__":
    create_hr_account("fiismatunnissa@gmail.com", "Uid35k32!", "Halizah")