import uuid
from typing import Optional
from pydantic import BaseModel


class ClientOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    color: Optional[str] = None
    areas: list[str] = []

    model_config = {"from_attributes": True}
