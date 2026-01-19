from typing import Annotated

from annotated_types import Len
from pydantic import BaseModel, EmailStr


class IssueTokenRequestSchema(BaseModel):
    username: str
    password: str


class RefreshTokenRequestSchema(BaseModel):
    refresh_token: str


class TokenResponseSchema(BaseModel):
    access_token: str
    refresh_token: str


class CreateUserRequestSchema(BaseModel):
    email: EmailStr
    username: Annotated[str, Len(max_length=150)]
    first_name: Annotated[str, Len(max_length=150)]
    last_name: Annotated[str, Len(max_length=150)]
    password: Annotated[str, Len(max_length=128)]


class UserSchema(BaseModel):
    id: int
    username: str
    email: str
    first_name: str
    last_name: str
    is_staff: bool
    is_superuser: bool
