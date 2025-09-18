from pydantic import BaseModel, EmailStr, constr
from datetime import date 
from typing import Annotated, List

class StudentBase(BaseModel):
    first_name: Annotated[str, constr(min_length=2, max_length=50, pattern=r"^[A-Za-z\s-]+$")]
    last_name: Annotated[str, constr(min_length=2, max_length=50, pattern=r"^[A-Za-z\s-]+$")]
    phone: Annotated[str, constr(pattern=r"^[5-9]\d{9}$")]
    birthdate: date
    email: EmailStr

class StudentCreate(StudentBase):
    pass

class StudentUpdate(StudentBase):
    pass

class StudentOut(StudentBase):
    id: int

class SubjectOut(BaseModel):
    id: int
    name: str

class StudentWithSubjects(StudentOut):
    enrolled_subjects: List[SubjectOut]
    available_subjects: List[SubjectOut]

class SubjectIds(BaseModel):
    subject_ids: List[int]
