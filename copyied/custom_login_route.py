from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from jose import jwt
from datetime import datetime, timedelta
from typing import Optional
import os

router = APIRouter()
templates = Jinja2Templates(directory="templates")

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Utility: create JWT
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Placeholder: fetch auth record (replace with real DB query)
def get_student_auth(username: str):
    # For demo purposes, we'll accept specific credentials
    # In real implementation, query database for user by username
    if username == "admin":
        return {"id": 1, "username": "admin", "password_hash": "admin", "role": "admin", "first_name": "Admin", "last_name": "User", "email": "admin@example.com"}
    elif username.startswith("student"):
        student_id = int(username.replace("student", "") or "2")
        return {"id": student_id, "username": username, "password_hash": "student", "role": "student", "first_name": f"Student{student_id}", "last_name": "User", "email": f"student{student_id}@example.com"}
    return None

# Very naive password check (replace with proper hashing e.g. passlib)
def verify_password(plain: str, stored: str) -> bool:
    return plain == stored

@router.get("/login", response_class=HTMLResponse)
async def show_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/custom-login")
async def custom_login(request: Request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")
    
    # Get user record
    record = get_student_auth(username)
    if not record or not verify_password(password, record["password_hash"]):
        return JSONResponse({"error": "Invalid credentials"}, status_code=401)
    
    # Create JWT token
    role = record.get("role", "student")
    token = create_access_token({"sub": str(record["id"]), "username": username, "role": role})
    
    # Return token and student details
    return JSONResponse({
        "access_token": token,
        "token_type": "bearer",
        "role": role,
        "student": {
            "id": record["id"],
            "username": record["username"],
            "first_name": record["first_name"],
            "last_name": record["last_name"],
            "email": record["email"],
            "role": role
        }
    })
