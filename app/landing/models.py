from pydantic import BaseModel, EmailStr, field_validator


class WaitlistEntryCreate(BaseModel):
    name: str
    email: EmailStr
    role: str = ""
    area: str = ""
    problematic: str = ""
    tools: str = ""
    process: str = ""
    fytic_question: str = ""

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        return str(v).strip()

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return str(v).strip().lower()


class ContactCreate(BaseModel):
    name: str
    firm: str
    email: EmailStr
    message: str

    @field_validator("name", "firm", "message", mode="before")
    @classmethod
    def strip_text(cls, v: str) -> str:
        return str(v).strip()

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return str(v).strip().lower()


class WaitlistStatusResponse(BaseModel):
    active: bool
    count: int = 0


class ClientsResponse(BaseModel):
    visible: bool
    clients: list[str]


class OkResponse(BaseModel):
    ok: bool
