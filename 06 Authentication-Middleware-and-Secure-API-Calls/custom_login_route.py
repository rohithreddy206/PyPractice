from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import os

router = APIRouter()
templates = Jinja2Templates(directory="templates")

SECURITY_TOKEN = os.getenv("SECURITY_TOKEN")

@router.get("/login", response_class=HTMLResponse)
async def show_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/custom-login")
async def custom_login(request: Request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")
    # Replace with real authentication
    if username == "admin" and password == "admin":
        return JSONResponse({"token": SECURITY_TOKEN})
    return JSONResponse({"error": "Invalid credentials"}, status_code=401)
