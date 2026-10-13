
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.api import router
from app.jobs.scheduler import start_scheduler, scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


tags_metadata = [
    {"name": "Authentication", "description": "Register, login, logout and token management."},
    {"name": "User Management", "description": "Manage staff users."},
    {"name": "Departments", "description": "Create and manage hospital departments."},
    {"name": "Doctors", "description": "Manage doctors and doctor details."},
    {"name": "Schedules", "description": "Manage doctor schedules and availability."},
    {"name": "Leaves", "description": "Manage doctor leave periods."},
    {"name": "Appointments", "description": "Book, cancel, reschedule and check in appointments."},
    {"name": "Consultations", "description": "Manage appointment consultations."},
    {"name": "Patient History", "description": "View patient appointment history."},
    {"name": "Files", "description": "Upload, list and download appointment files."},
    {"name": "Live Queue", "description": "Manage and test the doctor queue."},
    {"name": "Reviews", "description": "Submit reviews for appointments."},
    {"name": "Reports", "description": "Hospital and doctor performance reports."},
    {"name": "System", "description": "Root and health-check endpoints."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Hospital Appointment Booking System",
    version="1.0.0",
    description=(
        "Hospital appointments, doctor schedules, live queues, "
        "consultations, notifications and reports."
    ),
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", tags=["System"])
def root():
    return {
        "message": "Hospital Appointment Booking System API",
        "docs": "/docs",
        "health": "ok",
    }


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok"}
