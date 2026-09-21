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
    firebase_admin.initialize_app(
        cred,
        {"storageBucket": "employeemonitoring-c76543.firebasestorage.app"},
    )

from routes import auth, attendance, face, task, employee, profile, otp
import importlib.util
from pathlib import Path

business_trip_spec = importlib.util.spec_from_file_location(
    "business_trip_route", Path(__file__).parent / "routes" / "bussiness-trip.py"
)
business_trip_route = importlib.util.module_from_spec(business_trip_spec)
assert business_trip_spec.loader is not None
business_trip_spec.loader.exec_module(business_trip_route)

app.include_router(auth.router)
app.include_router(attendance.router)
app.include_router(face.router)
app.include_router(task.router_clients)
app.include_router(task.router_projects)
app.include_router(task.router)
app.include_router(employee.router) 
app.include_router(profile.router)
app.include_router(otp.router)
app.include_router(business_trip_route.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=12046, reload=True)
