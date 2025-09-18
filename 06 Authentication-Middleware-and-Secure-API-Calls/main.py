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

from database import create_db
from api import students
from middlewares.auth import auth_middleware
from custom_login_route import router as custom_login_router

# Load .env values
load_dotenv()

APP_HEADING = os.getenv("APP_HEADING", "Student Registration System")
LOGGING_ENABLED = os.getenv("LOGGING", "false").lower() == "true"
LOG_FILE = os.getenv("LOG_FILE", "student_actions.log")
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
        return await call_next(request)

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
                return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Forbidden: admin only list"})
        else:
            parts = path.split("/")
            if len(parts) >= 4 and parts[3].isdigit():
                target_id = int(parts[3])
                user_id = request.state.user["id"]
                if role != "admin" and target_id != user_id:
                    return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": "Forbidden: cannot access other student"})
    return await call_next(request)

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

# Mount student APIs
app.include_router(students.router, prefix="/api/students", tags=["students"])
app.include_router(custom_login_router)

# Templates
templates = Jinja2Templates(directory="templates")

@app.post("/api/login")
async def api_login(
    student_id: int = Body(..., embed=True),
    password: str = Body(..., embed=True)
):
    record = get_student_auth(student_id)
    if not record or not verify_password(password, record["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    role = record.get("role") or "student"
    token = create_access_token({"sub": str(record["id"]), "role": role})
    return {"access_token": token, "token_type": "bearer", "role": role, "student_id": record["id"]}

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