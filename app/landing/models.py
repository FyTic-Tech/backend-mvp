import re
from typing import Optional
from pydantic import BaseModel, field_validator

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class WaitlistEntryCreate(BaseModel):
    name: str = ""
    email: str = ""
    role: str = ""
    area: str = ""
    problematic: str = ""
    tools: str = ""
    process: str = ""
    ai_question: str = ""
    user_id: Optional[str] = None
    referred_by: Optional[str] = None  # handled in users table, not stored in waitlist

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return str(v).strip() if v else ""

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        if not v:
            return ""
        v = str(v).strip().lower()
        if v and not _EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v


class ContactCreate(BaseModel):
    name: str
    firm: str
    email: str
    message: str

    @field_validator("name", "firm", "message", mode="before")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return str(v).strip()

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        v = str(v).strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v


class WaitlistStatusResponse(BaseModel):
    active: bool
    count: int = 0


class ClientsResponse(BaseModel):
    visible: bool
    clients: list[str]


class OkResponse(BaseModel):
    ok: bool


class WaitlistPostResponse(BaseModel):
    ok: bool
    id: str


class InvestorCreate(BaseModel):
    name: str
    email: str

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = str(v).strip()
        if not v:
            raise ValueError("name is required")
        return v

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        v = str(v).strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v


class CheckEmailRequest(BaseModel):
    email: str


class RefCodeRequest(BaseModel):
    user_id: str


class LinkSurveyRequest(BaseModel):
    user_id: str
    email: str
    referred_by: Optional[str] = None


class BindUserRequest(BaseModel):
    anonymous_id: str
    new_user_id: str


class LinkGoogleRequest(BaseModel):
    waitlist_id: str
    user_id: str
    email: str
    referred_by: Optional[str] = None


class WaitlistEntryUpdate(BaseModel):
    role: Optional[str] = None
    area: Optional[str] = None
    problematic: Optional[str] = None
    tools: Optional[str] = None
    process: Optional[str] = None
    ai_question: Optional[str] = None
    fytic_question: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    user_id: Optional[str] = None

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = str(v).strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("invalid email format")
        return v
