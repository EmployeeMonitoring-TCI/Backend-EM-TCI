import os
import sys

_DLL_DIRECTORY_HANDLE = (
    os.add_dll_directory(sys.prefix) if sys.platform == "win32" else None
)

import firebase_admin
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from firebase_admin import credentials

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

from routes import auth, attendance, face, task, employee, profile, otp, notifications
import importlib.util
from pathlib import Path

business_trip_spec = importlib.util.spec_from_file_location(
    "business_trip_route", Path(__file__).parent / "routes" / "bussiness-trip.py"
)
business_trip_route = importlib.util.module_from_spec(business_trip_spec) # type: ignore
assert business_trip_spec is not None
assert business_trip_spec.loader is not None
assert business_trip_spec is not None
business_trip_spec.loader.exec_module(business_trip_route)

# Daftar semua router dengan prefix aslinya (/api/...)
all_routers = [
    auth.router,
    attendance.router,
    attendance.legacy_router,
    face.router,
    task.router_clients,
    task.router_projects,
    task.router,
    employee.router,
    profile.router,
    profile.legacy_router,
    otp.router,
    business_trip_route.router,
    notifications.router,
]

for router in all_routers:
    # Mount dengan prefix asli: /api/xxx
    app.include_router(router)
    # Mount dengan prefix ganda: /api/api/xxx
    # Ini menangani kasus frontend yang mengirim BASE_API_URL=/api/ + /api/xxx
    app.include_router(router, prefix="/api")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=12046, reload=True)
