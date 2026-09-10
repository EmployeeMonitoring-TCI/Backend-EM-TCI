import firebase_admin
from firebase_admin import credentials
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
app = FastAPI(title="Tri Cipta Integra API")

CREDENTIAL_PATH = "serviceAccountKey.json"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate(CREDENTIAL_PATH)
    firebase_admin.initialize_app(cred)

from routes import auth, attendance, face, task, employee, profile, otp

app.include_router(auth.router)
app.include_router(attendance.router)
app.include_router(face.router)
app.include_router(task.router)
app.include_router(employee.router) 
app.include_router(profile.router)
app.include_router(otp.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=12046, reload=True)