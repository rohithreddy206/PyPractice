from fastapi import Request
from fastapi.responses import JSONResponse
from jose import jwt, JWTError
import os
from dotenv import load_dotenv

# Load .env values
load_dotenv()

# Get token from environment
SECURITY_TOKEN = os.getenv("SECURITY_TOKEN")
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_SECRET")
ALGORITHM = "HS256"

async def selective_auth_middleware(request: Request, call_next):
    path = request.url.path
    # Allow public profile images, non-API, and login endpoint
    if path.startswith("/api/profile-image/") or not path.startswith("/api/") or path == "/api/login":
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
            legacy_token = request.headers.get("X-SECURITY-TOKEN") or request.query_params.get("token")
            if legacy_token and SECURITY_TOKEN and legacy_token == SECURITY_TOKEN:
                request.state.user = {"id": 0, "role": "admin", "legacy": True}
            else:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid token. Obtain a new token via POST /api/login"}
                )
    else:
        legacy_token = request.headers.get("X-SECURITY-TOKEN") or request.query_params.get("token")
        if legacy_token and SECURITY_TOKEN and legacy_token == SECURITY_TOKEN:
            request.state.user = {"id": 0, "role": "admin", "legacy": True}
        else:
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Invalid or missing token. Use Authorization: Bearer <JWT> from /api/login "
                              "or provide X-SECURITY-TOKEN header (legacy)."
                }
            )
    return await call_next(request)