import logging
import sqlite3
from fastapi import APIRouter, HTTPException
from typing import List

from database import get_db_connection
from models import StudentCreate, StudentUpdate, StudentOut, StudentWithSubjects, SubjectOut, SubjectIds

router = APIRouter()

# --- Create student ---
@router.post("/", response_model=dict)
def add_student(student: StudentCreate):
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
        conn.commit()
        logging.info(f"Student added: {student.dict()}")
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Email already exists")
    finally:
        cursor.close()
        conn.close()

    return {"success": True, "message": "Student registered successfully!"}

# --- Read students ---
@router.get("/", response_model=List[StudentOut])
def get_students():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, first_name, last_name, number AS phone, birthdate, email FROM students")
    rows = cursor.fetchall()
    students = [dict(row) for row in rows]
    cursor.close()
    conn.close()
    return students

# --- Update student ---
@router.put("/{student_id}", response_model=dict)
def update_student(student_id: int, student: StudentUpdate):
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
        logging.info(f"Student updated: {student.dict()}")
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already exists")
    finally:
        cursor.close()
        conn.close()

    return {"success": True, "message": "Student updated successfully!"}

# --- Delete student ---
@router.delete("/{student_id}", response_model=dict)
def delete_student(student_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students WHERE id=?", (student_id,))
    conn.commit()
    deleted = cursor.rowcount
    cursor.close()
    conn.close()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Student not found")

    return {"success": True, "message": "Student deleted"}

# --- Read student with subjects ---
@router.get("/{student_id}", response_model=StudentWithSubjects)
def get_student_with_subjects(student_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, first_name, last_name, number AS phone, birthdate, email FROM students WHERE id=?", (student_id,))
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

@router.get("/{student_id}/subjects", response_model=list[SubjectOut])
def get_student_subjects_only(student_id: int):
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
def add_subjects_to_student(student_id: int, payload: SubjectIds):
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
def remove_subjects_from_student(student_id: int, payload: SubjectIds):
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
