import re
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
    fytic_question: str = ""

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
