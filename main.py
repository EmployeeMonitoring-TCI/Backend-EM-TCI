import firebase_admin
from firebase_admin import credentials
from fastapi import FastAPI

CREDENTIAL_PATH = "serviceAccountKey.json"

try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate(CREDENTIAL_PATH)
    firebase_admin.initialize_app(cred)

from routes import auth, attendance, face, task, employee

app = FastAPI(title="Tri Cipta Integra API")

app.include_router(auth.router)
app.include_router(attendance.router)
app.include_router(face.router)
app.include_router(task.router)
app.include_router(employee.router) 

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)