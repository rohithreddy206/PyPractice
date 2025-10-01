from fastapi import Request
from fastapi.responses import JSONResponse
from collections import defaultdict
from threading import Lock
from time import time

RATE_LIMIT_GLOBAL = 10  # requests per minute
RATE_LIMIT_STUDENT = 3  # requests per minute

_global_requests = []
_student_requests = defaultdict(list)
_rate_lock = Lock()

def _rate_limit_global():
    now = time()
    with _rate_lock:
        _global_requests[:] = [t for t in _global_requests if now - t < 60]
        if len(_global_requests) >= RATE_LIMIT_GLOBAL:
            return False
        _global_requests.append(now)
        return True

def _rate_limit_student(student_id):
    now = time()
    with _rate_lock:
        reqs = _student_requests[student_id]
        reqs[:] = [t for t in reqs if now - t < 60]
        if len(reqs) >= RATE_LIMIT_STUDENT:
            return False
        reqs.append(now)
        return True

async def rate_limit_middleware(request: Request, call_next):
    user = getattr(request.state, "user", None)
    # Only apply rate limits for student users
    if user and user.get("role") == "student":
        if request.url.path.startswith("/api/"):
            if not _rate_limit_global():
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Global rate limit exceeded ({RATE_LIMIT_GLOBAL}/min). Try again later."}
                )
            # Try to extract student_id from path or query or JWT
            path_parts = request.url.path.split("/")
            student_id = None
            if len(path_parts) >= 4 and path_parts[2] == "students" and path_parts[3].isdigit():
                student_id = int(path_parts[3])
            if not student_id and "student_id" in request.query_params:
                sid = request.query_params.get("student_id")
                if sid and sid.isdigit():
                    student_id = int(sid)
            if not student_id:
                student_id = user.get("id")
            if student_id is not None:
                if not _rate_limit_student(student_id):
                    return JSONResponse(
                        status_code=429,
                        content={"detail": f"Rate limit exceeded for student {student_id} ({RATE_LIMIT_STUDENT}/min). Try again later."}
                    )
    # Admins have unlimited access
    return await call_next(request)
