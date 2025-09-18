import sqlite3

DB_FILE = "students.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def create_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students(
            id INTEGER PRIMARY KEY,
            first_name VARCHAR(50),
            last_name VARCHAR(50),
            number VARCHAR(15),
            birthdate DATE,
            email TEXT UNIQUE NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tblSubject(
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tblStudentSubject(
            student_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            PRIMARY KEY (student_id, subject_id),
            FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY(subject_id) REFERENCES tblSubject(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("SELECT COUNT(1) c FROM tblSubject")
    if cursor.fetchone()["c"] == 0:
        cursor.executemany("INSERT INTO tblSubject (name) VALUES (?)",
                           [("Mathematics",), ("Physics",), ("Chemistry",), ("Biology",), ("History",)])
    conn.commit()
    cursor.close()
    conn.close()
