import logging
import os
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi import Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from dotenv import load_dotenv
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Optional
import io, csv
from fastapi.responses import StreamingResponse
from time import time  # NEW
from collections import defaultdict  # NEW
# NEW: pandas import (with graceful fallback)
try:
    import pandas as pd
except ImportError:
    pd = None

from database import create_db
# ADD: import get_db_connection for student existence check
from database import get_db_connection
from api import students
from middlewares.auth import auth_middleware
from custom_login_route import router as custom_login_router  # reverted import

# Load .env values
load_dotenv()

APP_HEADING = os.getenv("APP_HEADING", "Student Registration System")
LOGGING_ENABLED = os.getenv("LOGGING", "false").lower() == "true"
LOG_FILE = os.getenv("LOG_FILE", "student_actions.log")  # FIX: restore assignment (was just 'LOG_FILE')
SECURITY_TOKEN = os.getenv("SECURITY_TOKEN")
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET")

# Configure logging
if LOGGING_ENABLED:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")]
    )
else:
    logging.disable(logging.CRITICAL)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Utility: create JWT
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Placeholder: fetch auth record (replace with real DB query)
def get_student_auth(student_id: int):
    # TODO: Replace with actual DB lookup. For example:
    # row = db.execute("SELECT id, password_hash, role FROM students WHERE id=?", (student_id,)).fetchone()
    # return {"id": row.id, "password_hash": row.password_hash, "role": row.role}
    demo_admin_id = 1
    if student_id == demo_admin_id:
        return {"id": 1, "password_hash": "adminpass", "role": "admin"}
    # Every other id accepted with password "studentpass"
    return {"id": student_id, "password_hash": "studentpass", "role": "student"}

# Very naive password check (replace with proper hashing e.g. passlib)
def verify_password(plain: str, stored: str) -> bool:
    return plain == stored

# FastAPI instance
app = FastAPI(title="Student Registration API")

# Replace previous blanket middleware with selective one
@app.middleware("http")
async def selective_auth(request, call_next):
    path = request.url.path
    # Allow non-API and login endpoint
    if not path.startswith("/api/") or path == "/api/login":
        return await call_next(request)

    # NEW: Allow open registration (self-register) for creating a student
    if request.method == "POST" and path.rstrip("/") == "/api/students":
        return await call_next(request)  # removed debug log

    auth_header = request.headers.get("Authorization")

    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = int(payload.get("sub"))
            role = payload.get("role", "student")
            if user_id is None:
                raise JWTError("Missing sub")
            request.state.user = {"id": user_id, "role": role, "legacy": False}
        except JWTError:
            # NEW: attempt legacy fallback instead of immediate 401
            legacy_token = request.headers.get("X-SECURITY-TOKEN") or request.query_params.get("token")
            if legacy_token and SECURITY_TOKEN and legacy_token == SECURITY_TOKEN:
                request.state.user = {"id": 0, "role": "admin", "legacy": True}
            else:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid token. Obtain a new token via POST /api/login"}
                )
    else:
        # Legacy fallback: SECURITY_TOKEN support (treat as admin)
        legacy_token = request.headers.get("X-SECURITY-TOKEN") or request.query_params.get("token")
        if legacy_token and SECURITY_TOKEN and legacy_token == SECURITY_TOKEN:
            # Assign pseudo admin user (id 0 indicates legacy)
            request.state.user = {"id": 0, "role": "admin", "legacy": True}
        else:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "detail": "Invalid or missing token. Use Authorization: Bearer <JWT> from /api/login "
                              "or provide X-SECURITY-TOKEN header (legacy)."
                }
            )

    # Resource-level enforcement for /api/students
    if path.startswith("/api/students"):
        role = request.state.user["role"]
        if path.rstrip("/") == "/api/students":
            if role != "admin":
                return JSONResponse(status_code=status.HTTP_403_FORBIDDEN,
                                    content={"detail": "Forbidden: admin only list. (Login as admin first)"})
        # NEW: admin-only bulk export
        elif path.startswith("/api/students/export-all"):  # CHANGED from /export
            if role != "admin":
                return JSONResponse(status_code=403, content={"detail": "Forbidden: admin only export"})
        else:
            parts = path.split("/")
            if len(parts) >= 4 and parts[3].isdigit():
                target_id = int(parts[3])
                user_id = request.state.user["id"]
                if role != "admin" and target_id != user_id:
                    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Forbidden: cannot access other student"})
    return await call_next(request)  # removed trailing debug log

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize DB
create_db()

# ============ EXPORT HELPERS ============  (NEW)
def _fetch_students_with_subjects(student_ids: list[int] | None = None):
    # MODIFIED: also fetch created_at
    conn = get_db_connection()
    cur = conn.cursor()
    where = ""
    params = []
    if student_ids:
        placeholders = ",".join("?" for _ in student_ids)
        where = f"WHERE id IN ({placeholders})"
        params = student_ids
    cur.execute(f"""
        SELECT id, first_name, last_name, number AS phone, birthdate, email, created_at
        FROM students {where}
        ORDER BY id
    """, params)
    rows = [dict(r) for r in cur.fetchall()]

    subj_map = {}
    if rows:
        ids_place = ",".join("?" for _ in rows)
        cur.execute(f"""
            SELECT ss.student_id, s.name
            FROM tblStudentSubject ss
            JOIN tblSubject s ON s.id = ss.subject_id
            WHERE ss.student_id IN ({ids_place})
            ORDER BY s.name
        """, [r["id"] for r in rows])
        for r in cur.fetchall():
            subj_map.setdefault(r["student_id"], []).append(r["name"])

    cur.close(); conn.close()

    enriched = []
    for r in rows:
        subs = subj_map.get(r["id"], [])
        enriched.append({
            "id": r["id"],
            "name": f"{r['first_name']} {r['last_name']}".strip(),
            "date_joined": (r.get("created_at") or "").split(" ")[0],
            "subjects": subs
        })
    return enriched  # each item: {id,name,date_joined,subjects:list}

def _build_export_dataframe(student_ids: list[int] | None = None):
    """
    Returns a pandas DataFrame (if pandas installed) or list[dict] fallback with:
      SlNo, Name, DateJoined, Subject 1..3
    """
    data = _fetch_students_with_subjects(student_ids)  # list[{id,name,date_joined,subjects:[]}]

    # Flatten
    flat = []
    for idx, r in enumerate(data, start=1):
        subs = r["subjects"][:3] + [""] * (3 - len(r["subjects"]))
        flat.append({
            "SlNo": idx,
            "Name": r["name"],
            "DateJoined": r["date_joined"],
            "Subject 1": subs[0],
            "Subject 2": subs[1],
            "Subject 3": subs[2],
        })
    if pd:
        return pd.DataFrame(flat, columns=["SlNo","Name","DateJoined","Subject 1","Subject 2","Subject 3"])
    return flat  # fallback list

# REPLACED _to_csv to delegate to DataFrame
def _to_csv(rows: list[dict]) -> str:
    if pd:
        df = _build_export_dataframe([r["id"] for r in rows] if rows else None) if isinstance(rows, list) and rows and "id" in rows[0] and "subjects" in rows[0] else None
    # rows passed are already enriched; reuse flattened logic directly
    if pd:
        # When rows already enriched create DataFrame directly
        flat_df = _build_export_dataframe([r["id"] for r in rows]) if rows else pd.DataFrame(columns=["SlNo","Name","DateJoined","Subject 1","Subject 2","Subject 3"])
        return flat_df.to_csv(index=False)
    # Fallback without pandas
    header = ["SlNo","Name","DateJoined","Subject 1","Subject 2","Subject 3"]
    if not rows:
        return ",".join(header) + "\n"
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    for idx, r in enumerate(rows, start=1):
        subs = r["subjects"][:3] + [""] * (3 - len(r["subjects"]))
        w.writerow([idx, r["name"], r["date_joined"], *subs])
    return out.getvalue()

# NEW: Excel exporter (XLSX) using pandas
def _to_excel_bytes(student_ids: list[int] | None = None) -> bytes:
    if not pd:
        raise HTTPException(status_code=500, detail="pandas not installed for Excel export")
    df = _build_export_dataframe(student_ids)
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Students")
    bio.seek(0)
    return bio.read()

# ============ BULK EXPORT ENDPOINTS ============ (NEW)

@app.get("/api/students/export-all")
def export_students(ids: str | None = None, request: Request = None):
    user = getattr(request.state, "user", None)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    id_list = None
    if ids:
        try:
            id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()] or None
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ids parameter")
    data = _fetch_students_with_subjects(id_list)
    csv_text = _to_csv(data)
    return StreamingResponse(io.StringIO(csv_text),
                             media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=students_export.csv"})

@app.get("/api/students/export-all.xlsx")
def export_students_excel(ids: str | None = None, request: Request = None):
    user = getattr(request.state, "user", None)
    if not user or user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    if not pd:
        raise HTTPException(status_code=500, detail="pandas not installed")
    id_list = None
    if ids:
        try:
            id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()] or None
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ids parameter")
    content = _to_excel_bytes(id_list)
    return StreamingResponse(io.BytesIO(content),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": "attachment; filename=students_export.xlsx"})

# Include router AFTER static export-all routes so static path wins before /{student_id}
app.include_router(students.router, prefix="/api/students", tags=["students"])
app.include_router(custom_login_router)

# ============ SINGLE STUDENT EXPORT (can remain here) ============
@app.get("/api/students/{student_id}/export")
def export_single_student(student_id: int, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user["role"] != "admin" and user["id"] != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    data = _fetch_students_with_subjects([student_id])
    if not data:
        raise HTTPException(status_code=404, detail="Student not found")
    csv_text = _to_csv(data)
    return StreamingResponse(io.StringIO(csv_text),
                             media_type="text/csv",
                             headers={"Content-Disposition": f"attachment; filename=student_{student_id}.csv"})

@app.get("/api/students/{student_id}/export.xlsx")
def export_single_student_excel(student_id: int, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user["role"] != "admin" and user["id"] != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not pd:
        raise HTTPException(status_code=500, detail="pandas not installed")
    rows = _fetch_students_with_subjects([student_id])
    if not rows:
        raise HTTPException(status_code=404, detail="Student not found")
    content = _to_excel_bytes([student_id])
    return StreamingResponse(io.BytesIO(content),
                             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f"attachment; filename=student_{student_id}.xlsx"})

# Templates
templates = Jinja2Templates(directory="templates")

# ==== FAILED LOGIN ATTEMPT TRACKING (NEW) ====
LOGIN_MAX_ATTEMPTS = 3
LOGIN_WINDOW_SEC = 60
_login_failures = defaultdict(list)  # ip -> [timestamps]

def _purge_old(ip: str):
    now = time()
    bucket = _login_failures[ip]
    while bucket and now - bucket[0] >= LOGIN_WINDOW_SEC:
        bucket.pop(0)

def _status(ip: str):
    _purge_old(ip)
    used = len(_login_failures[ip])
    remaining = max(0, LOGIN_MAX_ATTEMPTS - used)
    locked = used >= LOGIN_MAX_ATTEMPTS
    retry_after = 0
    if locked and _login_failures[ip]:
        retry_after = int(LOGIN_WINDOW_SEC - (time() - _login_failures[ip][0]))
        if retry_after < 0: retry_after = 0
    return used, remaining, locked, retry_after

def _record_failure(ip: str):
    _purge_old(ip)
    _login_failures[ip].append(time())
    return _status(ip)

def _clear_failures(ip: str):
    _login_failures.pop(ip, None)
# ==== END FAILED LOGIN ATTEMPT TRACKING ====

@app.post("/api/login")
async def api_login(payload: dict = Body(...), request: Request = None):  # MODIFIED (added request + logic)
    """
    Mixed login:
      Admin: username == 'admin' and password == 'admin123'
      Student: student_id + password (password = first_name + '123')
    """
    client_ip = request.client.host if request and request.client else "unknown"
    used, remaining, locked, retry = _status(client_ip)
    if locked:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Too many failed login attempts. Please wait.",
                "locked": True,
                "retry_after_seconds": retry,
                "lock_expires_at": int(time()) + retry,
                "attempts_used": used,
                "attempts_remaining": 0,
                "limit": LOGIN_MAX_ATTEMPTS,
                "window_seconds": LOGIN_WINDOW_SEC
            }
        )

    username = payload.get("username")
    password = payload.get("password")

    def fail(detail: str):
        u, r, l, ry = _record_failure(client_ip)
        return JSONResponse(
            status_code=429 if l else 401,
            content={
                "detail": detail,
                "locked": l,
                "retry_after_seconds": ry if l else 0,
                "lock_expires_at": (int(time()) + ry) if l else None,
                "attempts_used": u,
                "attempts_remaining": r,
                "limit": LOGIN_MAX_ATTEMPTS,
                "window_seconds": LOGIN_WINDOW_SEC,
                "message": f"{u}/{LOGIN_MAX_ATTEMPTS} attempts used ({r} left)"
            }
        )

    if username:  # admin branch
        if username == "admin" and password == "admin123":
            _clear_failures(client_ip)
            token = create_access_token({"sub": "0", "role": "admin"})
            return {
                "access_token": token,
                "token_type": "bearer",
                "role": "admin",
                "student_id": 0,
                "attempts_used": 0,
                "attempts_remaining": LOGIN_MAX_ATTEMPTS
            }
        return fail("Invalid admin credentials")

    student_id = payload.get("student_id")
    if student_id is None:
        return fail("student_id or username required")

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT first_name FROM students WHERE id=?", (student_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    if not row:
        return fail("Invalid credentials")
    expected = row["first_name"] + "123"
    if password != expected:
        return fail("Invalid credentials")

    _clear_failures(client_ip)
    token = create_access_token({"sub": str(student_id), "role": "student"})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": "student",
        "student_id": student_id,
        "attempts_used": 0,
        "attempts_remaining": LOGIN_MAX_ATTEMPTS
    }

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