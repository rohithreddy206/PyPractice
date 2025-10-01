import logging
import sqlite3
import uuid, os  # NEW
from fastapi import APIRouter, HTTPException, Query, UploadFile, File  # NEW
from starlette.requests import Request
from database import get_db_connection
from schemas import StudentCreate, StudentUpdate, StudentWithSubjects, SubjectOut, SubjectIds, PaginatedStudents

try:
    import pandas as pd
except ImportError:
    pd = None

router = APIRouter()

PROFILE_IMAGE_DIR = "profile_images"  # NEW
os.makedirs(PROFILE_IMAGE_DIR, exist_ok=True)  # NEW

# NEW: pandas helper for student + subjects
def _pd_fetch_student_and_subjects(student_id: int):
    if not pd:
        return None
    conn = get_db_connection()
    try:
        df_student = pd.read_sql_query(
            "SELECT id, first_name, last_name, number AS phone, birthdate, email, profile_image_guid FROM students WHERE id=?",
            conn, params=[student_id]
        )
        if df_student.empty:
            return "NOT_FOUND"
        df_enrolled = pd.read_sql_query(
            """
            SELECT s.id, s.name
            FROM tblStudentSubject ss
            JOIN tblSubject s ON s.id = ss.subject_id
            WHERE ss.student_id=?
            ORDER BY s.name
            """, conn, params=[student_id]
        )
        df_available = pd.read_sql_query(
            """
            SELECT id, name FROM tblSubject
            WHERE id NOT IN (
                SELECT subject_id FROM tblStudentSubject WHERE student_id=?
            )
            ORDER BY name
            """, conn, params=[student_id]
        )
        student_row = df_student.iloc[0].to_dict()
        enrolled = [SubjectOut(**r) for r in df_enrolled.to_dict(orient="records")]
        available = [SubjectOut(**r) for r in df_available.to_dict(orient="records")]
        return {**student_row, "enrolled_subjects": enrolled, "available_subjects": available}
    finally:
        conn.close()

@router.post("/", response_model=dict)
def add_student(student: StudentCreate):
    logging.info("ADD_STUDENT (slash) attempt phone=%s email=%s", student.phone, student.email)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM students WHERE number=?", (student.phone,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Phone number already exists")
    try:
        cursor.execute("""
            INSERT INTO students (first_name, last_name, number, birthdate, email)
            VALUES (?, ?, ?, ?, ?)
        """, (student.first_name, student.last_name, student.phone, student.birthdate, student.email))
        # created_at filled automatically
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Email already exists")
    finally:
        cursor.close(); conn.close()
    return {"success": True, "message": "Student registered successfully!"}

@router.post("", response_model=dict)
def add_student_noslash(student: StudentCreate):
    logging.info("ADD_STUDENT (no-slash) direct hit")
    return add_student(student)

@router.get("/", response_model=PaginatedStudents)
def get_students(
    q: str | None = Query(None, description="Search by first name, last name or email"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100)
):
    logging.info("LIST_STUDENTS (slash) q=%s page=%s size=%s", q, page, page_size)
    conn = get_db_connection()
    where = ""
    params = []
    if q:
        like = f"%{q.strip()}%"
        where = "WHERE first_name LIKE ? OR last_name LIKE ? OR email LIKE ?"
        params.extend([like, like, like])
    # Use pandas if available
    if pd:
        df = pd.read_sql_query(f"""
            SELECT id, first_name, last_name, number AS phone, birthdate, email
            FROM students {where} ORDER BY id DESC
        """, conn, params=params)
        total = len(df)
        pages = (total + page_size - 1) // page_size if total else 1
        if page > pages and total:
            page = pages
        start = (page - 1) * page_size
        end = start + page_size
        slice_df = df.iloc[start:end]
        items = slice_df.to_dict(orient="records")
        conn.close()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
            "items": items
        }
    # Fallback original path
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) AS c FROM students {where}", params)
    total = cur.fetchone()["c"]
    pages = (total + page_size - 1) // page_size if total else 1
    if page > pages and total != 0:
        page = pages
    offset = (page - 1) * page_size
    cur.execute(
        f"""SELECT id, first_name, last_name, number AS phone, birthdate, email
            FROM students {where}
            ORDER BY id DESC
            LIMIT ? OFFSET ?""",
        (*params, page_size, offset)
    )
    items = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {"total": total, "page": page, "page_size": page_size, "pages": pages, "items": items}

@router.get("", response_model=PaginatedStudents)
def get_students_noslash(
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100)
):
    return get_students(q=q, page=page, page_size=page_size)

@router.put("/{student_id}", response_model=dict)
def update_student(student_id: int, student: StudentUpdate, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Admin can edit any student, student only their own
    if user["role"] != "admin" and user["id"] != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM students WHERE number=? AND id!=?", (student.phone, student_id))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Phone number already exists")
    try:
        cursor.execute("""
            UPDATE students
            SET first_name=?, last_name=?, number=?, birthdate=?, email=?
            WHERE id=?
        """, (student.first_name, student.last_name, student.phone, student.birthdate, student.email, student_id))
        conn.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Student not found")
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already exists")
    finally:
        cursor.close(); conn.close()
    return {"success": True, "message": "Student updated successfully!"}

@router.delete("/{student_id}", response_model=dict)
def delete_student(student_id: int, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Admin can delete any student, student only their own
    if user["role"] != "admin" and user["id"] != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE id=?", (student_id,))
    conn.commit()
    deleted = cursor.rowcount
    cursor.close(); conn.close()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Student not found")
    return {"success": True, "message": "Student deleted"}

@router.get("/{student_id}", response_model=StudentWithSubjects)
def get_student_with_subjects(student_id: int, request: Request):
    logging.info("GET_STUDENT id=%s", student_id)
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Admin can access any student, student only their own
    if user["role"] != "admin" and user["id"] != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # NEW: try pandas path
    pd_result = _pd_fetch_student_and_subjects(student_id)
    if pd_result == "NOT_FOUND":
        raise HTTPException(status_code=404, detail="Student not found")
    if pd_result:
        return pd_result  # already shaped

    # ...existing code (fallback original SQL)...
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, first_name, last_name, number AS phone, birthdate, email, profile_image_guid FROM students WHERE id=?", (student_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")
    cur.execute("""
        SELECT s.id, s.name
        FROM tblSubject s
        JOIN tblStudentSubject ss ON ss.subject_id = s.id
        WHERE ss.student_id=?
        ORDER BY s.name
    """, (student_id,))
    enrolled = [SubjectOut(**dict(r)) for r in cur.fetchall()]
    cur.execute("""
        SELECT id, name FROM tblSubject
        WHERE id NOT IN (SELECT subject_id FROM tblStudentSubject WHERE student_id=?)
        ORDER BY name
    """, (student_id,))
    available = [SubjectOut(**dict(r)) for r in cur.fetchall()]
    cur.close(); conn.close()
    return {**dict(row), "enrolled_subjects": enrolled, "available_subjects": available}

@router.post("/{student_id}/profile-image", response_model=dict)  # NEW
def upload_profile_image(student_id: int, request: Request, file: UploadFile = File(...)):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Admin can upload image for any student, student only their own
    if user["role"] != "admin" and user["id"] != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    # basic content-type check
    if file.content_type not in ("image/png", "image/jpeg", "image/jpg", "image/webp"):
        raise HTTPException(status_code=400, detail="Unsupported image type")
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        # derive from content-type if extension missing
        ext = ".jpg" if "jpeg" in file.content_type else ".png"
    guid = uuid.uuid4().hex
    fname = f"{guid}{ext}"
    path = os.path.join(PROFILE_IMAGE_DIR, fname)
    with open(path, "wb") as out:
        out.write(file.file.read())
    # persist guid (not filename per requirement)
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("UPDATE students SET profile_image_guid=? WHERE id=?", (guid, student_id))
    if cur.rowcount == 0:
        conn.rollback(); cur.close(); conn.close()
        try: os.remove(path)
        except: pass
        raise HTTPException(status_code=404, detail="Student not found")
    conn.commit(); cur.close(); conn.close()
    return {"success": True, "profile_image_guid": guid, "url": f"/api/profile-image/{guid}"}

@router.get("/{student_id}/subjects", response_model=list[SubjectOut])
def get_student_subjects_only(student_id: int, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Admin can view any student's subjects, student only their own
    if user["role"] != "admin" and user["id"] != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # NEW: pandas shortcut
    if pd:
        conn = get_db_connection()
        try:
            exists = pd.read_sql_query("SELECT id FROM students WHERE id=?", conn, params=[student_id])
            if exists.empty:
                raise HTTPException(status_code=404, detail="Student not found")
            df_sub = pd.read_sql_query(
                """
                SELECT s.id, s.name
                FROM tblSubject s
                JOIN tblStudentSubject ss ON ss.subject_id = s.id
                WHERE ss.student_id=?
                ORDER BY s.name
                """, conn, params=[student_id]
            )
            return [SubjectOut(**r) for r in df_sub.to_dict(orient="records")]
        finally:
            conn.close()

    # ...existing code (fallback)...
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM students WHERE id=?", (student_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")
    cur.execute("""
        SELECT s.id, s.name
        FROM tblSubject s
        JOIN tblStudentSubject ss ON ss.subject_id = s.id
        WHERE ss.student_id=?
        ORDER BY s.name
    """, (student_id,))
    data = [SubjectOut(**dict(r)) for r in cur.fetchall()]
    cur.close(); conn.close()
    return data

@router.post("/{student_id}/subjects", response_model=dict)
def add_subjects_to_student(student_id: int, payload: SubjectIds, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Admin can add subjects for any student, student only their own
    if user["role"] != "admin" and user["id"] != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not payload.subject_ids:
        raise HTTPException(status_code=400, detail="No subject IDs provided")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM students WHERE id=?", (student_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")
    placeholders = ",".join("?" * len(payload.subject_ids))
    cur.execute(f"SELECT id FROM tblSubject WHERE id IN ({placeholders})", tuple(payload.subject_ids))
    valid = {r["id"] for r in cur.fetchall()}
    if set(payload.subject_ids) - valid:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid subject IDs")
    added = 0
    for sid in payload.subject_ids:
        cur.execute("INSERT OR IGNORE INTO tblStudentSubject (student_id, subject_id) VALUES (?,?)", (student_id, sid))
        if cur.rowcount:
            added += 1
    conn.commit()
    cur.close(); conn.close()
    return {"success": True, "added": added}

@router.post("/{student_id}/subjects/remove", response_model=dict)
def remove_subjects_from_student(student_id: int, payload: SubjectIds, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Admin can remove subjects for any student, student only their own
    if user["role"] != "admin" and user["id"] != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not payload.subject_ids:
        raise HTTPException(status_code=400, detail="No subject IDs provided")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM students WHERE id=?", (student_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")
    placeholders = ",".join("?" * len(payload.subject_ids))
    cur.execute(f"DELETE FROM tblStudentSubject WHERE student_id=? AND subject_id IN ({placeholders})",
                (student_id, *payload.subject_ids))
    removed = cur.rowcount
    conn.commit()
    cur.close(); conn.close()
    return {"success": True, "removed": removed}

@router.post("/{student_id}/subjects", response_model=dict)
def add_subjects_to_student(student_id: int, payload: SubjectIds, request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Admin can add subjects for any student, student only their own
    if user["role"] != "admin" and user["id"] != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if not payload.subject_ids:
        raise HTTPException(status_code=400, detail="No subject IDs provided")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM students WHERE id=?", (student_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")
    placeholders = ",".join("?" * len(payload.subject_ids))
    cur.execute(f"SELECT id FROM tblSubject WHERE id IN ({placeholders})", tuple(payload.subject_ids))
    valid = {r["id"] for r in cur.fetchall()}
    missing = set(payload.subject_ids) - valid
    if missing:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Invalid subject IDs: {sorted(missing)}")
    added = 0
    for sid in payload.subject_ids:
        cur.execute("INSERT OR IGNORE INTO tblStudentSubject (student_id, subject_id) VALUES (?,?)", (student_id, sid))
        if cur.rowcount:
            added += 1
    conn.commit()
    cur.close(); conn.close()
    return {"success": True, "added": added}

@router.post("/{student_id}/subjects/remove", response_model=dict)
def remove_subjects_from_student(student_id: int, payload: SubjectIds, request: Request):  # modified
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user["role"] != "admin" and user["id"] != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if not payload.subject_ids:
        raise HTTPException(status_code=400, detail="No subject IDs provided")
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM students WHERE id=?", (student_id,))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Student not found")
    placeholders = ",".join("?" * len(payload.subject_ids))
    cur.execute(f"DELETE FROM tblStudentSubject WHERE student_id=? AND subject_id IN ({placeholders})",
                (student_id, *payload.subject_ids))
    removed = cur.rowcount
    conn.commit()
    cur.close(); conn.close()
    return {"success": True, "removed": removed}
