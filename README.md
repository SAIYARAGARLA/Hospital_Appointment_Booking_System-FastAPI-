# Hospital Appointment Booking System

A RESTful backend application built with **FastAPI** and **MySQL** to manage hospital departments, doctors, schedules, patient appointments, consultations, and appointment queues.

## Project Overview

The Hospital Appointment Booking System provides APIs for patients and hospital staff to manage the appointment lifecycle. It uses JWT-based authentication, role-based access control, SQLAlchemy ORM, and Alembic database migrations.

## Features

- **Authentication and Authorization:** Patient registration, login, JWT access and refresh tokens, and role-based access.
- **Department Management:** Create and retrieve hospital departments.
- **Doctor Management:** Doctor profiles, specializations, qualifications, and consultation fees.
- **Schedules and Leaves:** Manage doctor availability, working hours, breaks, and leave schedules.
- **Appointment Management:** Book, view, reschedule, cancel, and check in for appointments.
- **Consultation Management:** Manage consultation details and patient history.
- **Queue Management:** WebSocket-based live queue updates.
- **Notifications:** Background email tasks for supported appointment events when SMTP is configured.
- **Scheduled Jobs:** Appointment reminders, no-show checks, and follow-up tasks using APScheduler.
- **File Management:** Upload and authorized download of supported consultation files.
- **Reports:** Dashboard, doctor performance, department summary, peak hours, and frequent no-show reports.
- **Appointment Reviews:** Review functionality for completed appointments.
- **Database Migrations:** Version-controlled schema management with Alembic.

## Technology Stack

| Component | Technology |
|---|---|
| Backend framework | FastAPI |
| Programming language | Python |
| Database | MySQL |
| ORM | SQLAlchemy |
| Data validation | Pydantic |
| Authentication | JWT |
| Password hashing | Passlib and bcrypt |
| Database migrations | Alembic |
| Real-time communication | WebSockets |
| Background processing | FastAPI BackgroundTasks |
| Scheduled tasks | APScheduler |
| API documentation | Swagger UI |

## Project Structure

```text
Hospital_Appointment_Booking_System/
├── app/
│   ├── main.py
│   ├── models/
│   ├── schemas/
│   ├── routers/
│   ├── services/
│   └── ...
├── alembic/
│   ├── versions/
│   │   └── 0001_initial_schema.py
│   └── env.py
├── scripts/
├── uploads/
├── screenshots/
├── alembic.ini
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

*The structure above summarizes the main project components. Keep the entries aligned with the actual files and folders in your repository.*

## Prerequisites

- Python 3.9 or later
- MySQL Server
- MySQL Workbench (optional)
- Git
- A virtual environment

## Installation and Setup

### 1. Clone or open the project

Open a terminal in the project directory.

### 2. Create and activate a virtual environment

For Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure the database

Create the database in MySQL:

```sql
CREATE DATABASE hospital_booking
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;
```

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

Update `.env` with your local MySQL connection details and a strong JWT secret. Configure SMTP credentials only if email notifications need to be tested.

**Security:** Do not commit `.env`, passwords, JWT secrets, access tokens, or real patient information to GitHub.

## Database Migration

The project uses Alembic to create and manage database tables.

Apply migrations:

```powershell
alembic upgrade head
```

Verify the current migration:

```powershell
alembic current
```

The initial migration is stored in `alembic/versions/0001_initial_schema.py`.

When models change, create and apply a new migration:

```powershell
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

## Run the Application

Start the development server:

```powershell
uvicorn app.main:app --reload
```

Open the following URLs:

- **Swagger API documentation:** http://127.0.0.1:8000/docs
- **ReDoc documentation:** http://127.0.0.1:8000/redoc
- **Health endpoint:** http://127.0.0.1:8000/health
- **Live queue test page:** http://127.0.0.1:8000/queue-test

## API Modules

| Module | Main functionality |
|---|---|
| Authentication | Registration, login, token refresh, logout, current user |
| Administration | Staff account management |
| Departments | Department management |
| Doctors | Doctor profiles and doctor information |
| Schedules | Doctor schedules, leaves, and available slots |
| Appointments | Booking, listing, cancellation, rescheduling, check-in |
| Consultations | Consultation records and patient history |
| File Management | File uploads and authorized downloads |
| Live Queue | Real-time queue communication over WebSockets |
| Notifications | Personal notification WebSocket |
| Reports | Hospital, doctor, department, and appointment statistics |
| Reviews | Appointment review submission |

For exact request fields, authentication requirements, and response schemas, refer to Swagger UI at `/docs`.

## Authentication and Testing

1. Register a patient using `POST /auth/register`.
2. Log in using `POST /auth/login`.
3. Authorize protected requests using the access token.
4. Create staff accounts and doctor profiles using the appropriate administrative workflow.
5. Configure doctor schedules and verify available appointment slots.
6. Test appointment booking and the supported appointment lifecycle.
7. Test role-based restrictions and validation responses.
8. Test queue events, file operations, reports, and notifications where configured.

Public registration creates a Patient account. Administrative and Doctor operations require the appropriate role and permissions.

Use local test accounts and non-sensitive sample data. Do not publish passwords or tokens in screenshots.

## Live Queue Testing

1. Log in and obtain an access token.
2. Open `/queue-test`.
3. Enter the doctor ID and access token in the test page.
4. Connect the WebSocket.
5. Trigger a supported queue event, such as patient check-in or calling the next patient.
6. Verify that the connected client receives the queue update.

WebSocket testing requires a valid token and the appropriate permissions.

## Email Configuration

For Gmail SMTP, enable two-step verification and create an App Password. Configure the following variables in `.env`:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email@gmail.com
```

Use your own credentials locally. Never include them in the repository.

Email delivery depends on valid SMTP configuration and successful execution of the relevant notification workflow. Confirm actual receipt before reporting an email test as successful.

## Screenshots and Submission Evidence

Store genuine screenshots in the `screenshots/` directory, where applicable:

- Successful authentication response
- Doctor information and schedules
- Successful appointment booking
- Appointment listing or cancellation
- Alembic migration status
- Live queue connection and update
- Actual email notifications, if successfully received

Only include evidence of tests that were actually performed. Hide access tokens, passwords, secret keys, and personal information.

## Security Considerations

- Store credentials and secrets in environment variables.
- Use role-based authorization for protected operations.
- Keep password hashes and authentication tokens out of API responses and screenshots.
- Restrict uploaded file types and sizes.
- Use local test data instead of real patient information.
- Perform authorization, validation, and concurrency testing before production deployment.

## Conclusion

The Hospital Appointment Booking System demonstrates the implementation of a FastAPI backend for hospital appointment workflows, with MySQL persistence, Alembic migrations, authentication, role-based access, and supporting real-time and background-processing features.

