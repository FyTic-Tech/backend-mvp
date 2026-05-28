from pydantic import BaseModel, EmailStr, field_validator


class WaitlistEntryCreate(BaseModel):
    name: str
    email: EmailStr
    role: str = ""
    position: str = ""
    caseload: str = ""

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return str(v).strip()

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return str(v).strip().lower()


class WaitlistStatusResponse(BaseModel):
    active: bool


class ClientsResponse(BaseModel):
    visible: bool
    clients: list[str]


class OkResponse(BaseModel):
    ok: bool
