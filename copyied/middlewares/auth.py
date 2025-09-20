from fastapi import Request, HTTPException
from starlette.responses import JSONResponse
import os
from dotenv import load_dotenv

# Load .env values
load_dotenv()

# Get token from environment
SECURITY_TOKEN = os.getenv("SECURITY_TOKEN")

async def auth_middleware(request: Request, call_next):
    # Allow unauthenticated access to login and static/template routes
    if request.url.path in ["/login", "/custom-login", "/"] or request.url.path.startswith("/static"):
        response = await call_next(request)
        return response

    # Check for Authorization header
    auth_header = request.headers.get("Authorization")
    # log token for debugging
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            {"error": "Missing or invalid Authorization header"},
            status_code=401
        )
    
    token = auth_header[7:]
    # Replace with your token check logic
    from os import getenv
    if token != getenv("SECURITY_TOKEN"):
        return JSONResponse(
            {"error": "Invalid or expired token"},
            status_code=401
        )
    
    # Token is valid, proceed with the request
    response = await call_next(request)
    return response