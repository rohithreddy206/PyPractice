import logging
import os
import fastapi
from fastapi import HTTPException, status, Depends, Request  # FIX: add Request to import
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from database import create_db, get_db_connection
from api import students
from middlewares.auth import selective_auth_middleware  # CHANGED: use refactored middleware
from middlewares.rate_limit import rate_limit_middleware  # NEW: import rate limiter
from custom_login_route import router as custom_login_router
from fastapi.templating import Jinja2Templates  # ADD THIS
from fastapi.responses import HTMLResponse, JSONResponse      # ADD THIS if not already present
from jose import jwt
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict
from time import time

load_dotenv()
APP_HEADING = os.getenv("APP_HEADING", "Student Registration System")
LOGGING_ENABLED = os.getenv("LOGGING", "false").lower() == "true"
LOG_FILE = os.getenv("LOG_FILE", "student_actions.log")
SECURITY_TOKEN = os.getenv("SECURITY_TOKEN")

ALGORITHM = "HS256"
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
LOGIN_MAX_ATTEMPTS = 3
_login_failures_admin = defaultdict(list)
_login_failures_student = defaultdict(list)

if LOGGING_ENABLED:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")]
    )
else:
    logging.disable(logging.CRITICAL)

app = FastAPI(title="Student Registration API")

# Register middlewares
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(selective_auth_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

create_db()

# Register routers
app.include_router(students.router, prefix="/api/students", tags=["students"])
app.include_router(custom_login_router)

# Templates
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Optional: expose role if authenticated
    user_role = getattr(getattr(request, "state", None), "user", {}).get("role") if hasattr(request, "state") else None
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "heading": APP_HEADING,
            "security_token": SECURITY_TOKEN,
            "role": user_role
        }
    )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/student-login", response_class=HTMLResponse)
async def student_login_page(request: Request):
    return templates.TemplateResponse("student_login.html", {"request": request, "heading": APP_HEADING})

@app.get("/students/{student_id}", response_class=HTMLResponse)
async def student_detail_page(student_id: int, request: Request):
    return templates.TemplateResponse(
        "student_detail.html",
        {"request": request, "student_id": student_id, "heading": APP_HEADING}
    )

@app.get("/student/{student_id}/subjects", response_class=HTMLResponse)
async def student_subjects_page(student_id: int, request: Request):
    return templates.TemplateResponse(
        "student_subjects.html",
        {"request": request, "student_id": student_id, "heading": APP_HEADING}
    )

@app.get("/students/{student_id}/subjects", response_class=HTMLResponse)
async def student_subjects_page_plural(student_id: int, request: Request):
    return templates.TemplateResponse(
        "student_subjects.html",
        {"request": request, "student_id": student_id, "heading": APP_HEADING}
    )

@app.get("/api/profile-image/{guid}")  # NEW
def get_profile_image(guid: str):
    # Find any file starting with guid.*
    pattern = os.path.join(PROFILE_IMAGE_DIR, f"{guid}.*")
    matches = glob.glob(pattern)
    if not matches:
        raise HTTPException(status_code=404, detail="Image not found")
    # choose first (only expected)
    fpath = matches[0]
    # simple content-type inference
    ext = os.path.splitext(fpath)[1].lower()
    ctype = "image/png"
    if ext in (".jpg", ".jpeg"): ctype = "image/jpeg"
    elif ext == ".webp": ctype = "image/webp"
    return FileResponse(fpath, media_type=ctype)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def _status_admin(username: str):
    key = str(username).strip().lower()
    used = len(_login_failures_admin[key])
    remaining = max(0, LOGIN_MAX_ATTEMPTS - used)
    locked = used >= LOGIN_MAX_ATTEMPTS
    return used, remaining, locked, 0

def _record_failure_admin(username: str):
    key = str(username).strip().lower()
    _login_failures_admin[key].append(time())
    return _status_admin(username)

def _clear_failures_admin(username: str):
    key = str(username).strip().lower()
    _login_failures_admin.pop(key, None)

def _status_student(student_id):
    key = str(student_id)
    used = len(_login_failures_student[key])
    remaining = max(0, LOGIN_MAX_ATTEMPTS - used)
    locked = used >= LOGIN_MAX_ATTEMPTS
    return used, remaining, locked, 0

def _record_failure_student(student_id):
    key = str(student_id)
    _login_failures_student[key].append(time())
    return _status_student(student_id)

def _clear_failures_student(student_id):
    key = str(student_id)
    _login_failures_student.pop(key, None)

@app.post("/api/login")
async def api_login(payload: dict, request: Request):
    username = payload.get("username")
    password = payload.get("password")
    student_id = payload.get("student_id")

    # Normalize student_id if passed as string
    if isinstance(student_id, str) and student_id.strip().isdigit():
        student_id = int(student_id.strip())

    # Allow numeric username as student_id fallback
    if student_id is None and username and isinstance(username, str) and username.isdigit():
        student_id = int(username)
        username = None

    # Admin branch
    if username:
        ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
        ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
        used, remaining, locked, _ = _status_admin(username)
        if locked:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many failed admin login attempts. Please wait.",
                    "locked": True,
                    "retry_after_seconds": 0,
                    "lock_expires_at": None,
                    "attempts_used": used,
                    "attempts_remaining": 0,
                    "limit": LOGIN_MAX_ATTEMPTS,
                    "window_seconds": 0,
                    "user_key": f"admin:{username}"
                }
            )
        def fail_admin(detail: str):
            u, r, l, _ = _record_failure_admin(username)
            return JSONResponse(
                status_code=429 if l else 401,
                content={
                    "detail": detail,
                    "locked": l,
                    "retry_after_seconds": 0,
                    "lock_expires_at": None,
                    "attempts_used": u,
                    "attempts_remaining": r,
                    "limit": LOGIN_MAX_ATTEMPTS,
                    "window_seconds": 0,
                    "message": f"{u}/{LOGIN_MAX_ATTEMPTS} attempts used ({r} left)",
                    "user_key": f"admin:{username}"
                }
            )
        if not password:
            return fail_admin("Password required")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            _clear_failures_admin(username)
            token = create_access_token({"sub": "0", "role": "admin", "username": username})
            return {
                "access_token": token,
                "token_type": "bearer",
                "role": "admin",
                "student_id": 0,
                "attempts_used": 0,
                "attempts_remaining": LOGIN_MAX_ATTEMPTS,
                "user_key": f"admin:{username}"
            }
        return fail_admin("Invalid admin credentials")

    # Student branch
    if student_id is not None:
        used, remaining, locked, _ = _status_student(student_id)
        if locked:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many failed student login attempts. Please wait.",
                    "locked": True,
                    "retry_after_seconds": 0,
                    "lock_expires_at": None,
                    "attempts_used": used,
                    "attempts_remaining": 0,
                    "limit": LOGIN_MAX_ATTEMPTS,
                    "window_seconds": 0,
                    "user_key": f"student:{student_id}"
                }
            )
        def fail_student(detail: str):
            u, r, l, _ = _record_failure_student(student_id)
            return JSONResponse(
                status_code=429 if l else 401,
                content={
                    "detail": detail,
                    "locked": l,
                    "retry_after_seconds": 0,
                    "lock_expires_at": None,
                    "attempts_used": u,
                    "attempts_remaining": r,
                    "limit": LOGIN_MAX_ATTEMPTS,
                    "window_seconds": 0,
                    "message": f"{u}/{LOGIN_MAX_ATTEMPTS} attempts used ({r} left)",
                    "user_key": f"student:{student_id}"
                }
            )
        if not password:
            return fail_student("Password required")
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT first_name FROM students WHERE id=?", (student_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return fail_student("Student not found")
        expected = row["first_name"] + "123"
        if password != expected:
            return fail_student("Invalid credentials")
        _clear_failures_student(student_id)
        token = create_access_token({"sub": str(student_id), "role": "student"})
        return {
            "access_token": token,
            "token_type": "bearer",
            "role": "student",
            "student_id": student_id,
            "attempts_used": 0,
            "attempts_remaining": LOGIN_MAX_ATTEMPTS,
            "user_key": f"student:{student_id}"
        }

    # If neither admin nor student branch matched
    return JSONResponse(status_code=400, content={"detail": "username (admin) or student_id required"})