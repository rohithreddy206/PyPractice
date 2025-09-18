from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import os
from dotenv import load_dotenv

load_dotenv()
router = APIRouter()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
SECURITY_TOKEN = os.getenv("SECURITY_TOKEN", "mytoken")

@router.post("/custom-login")
async def custom_login(request: Request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return JSONResponse(content={"detail": "Username and password required"}, status_code=400)
    if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
        return JSONResponse(content={"detail": "Invalid credentials"}, status_code=401)
    return JSONResponse(content={"token": SECURITY_TOKEN, "username": username}, status_code=200)
