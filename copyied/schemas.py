from pydantic import BaseModel, EmailStr, constr
from typing import Optional, List

class StudentCreate(BaseModel):
    first_name: constr(min_length=2, max_length=50)
    last_name: constr(min_length=2, max_length=50)
    phone: constr(pattern=r'^[5-9][0-9]{9}$')
    birthdate: str  # or use date if you want automatic parsing
    email: EmailStr

class StudentUpdate(BaseModel):
    first_name: constr(min_length=2, max_length=50)
    last_name: constr(min_length=2, max_length=50)
    phone: constr(pattern=r'^[5-9][0-9]{9}$')
    birthdate: str
    email: EmailStr

class StudentResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    phone: str
    birthdate: str
    email: EmailStr

    class Config:
        orm_mode = True

class SubjectOut(BaseModel):
    id: int
    name: str

class StudentWithSubjects(StudentResponse):
    enrolled_subjects: List[SubjectOut]
    available_subjects: List[SubjectOut]
    profile_image_guid: Optional[str] = None

class SubjectIds(BaseModel):
    subject_ids: List[int]

class PaginatedStudents(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    items: List[StudentResponse]
