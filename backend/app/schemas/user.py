from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: str
    phone_number: str | None = None
    zip_code: str | None = None
    council_district: str | None = None


class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone_number: str | None = None
    zip_code: str | None = None
    council_district: str | None = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    is_verified: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime | None = None
    last_login: datetime | None = None

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class TokenData(BaseModel):
    email: str | None = None


class UserInterestCreate(BaseModel):
    category: str
    keywords: list[str] = []
    priority: int = 1

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        if v < 1 or v > 5:
            raise ValueError("Priority must be between 1 and 5")
        return v


class UserInterestResponse(BaseModel):
    id: int
    user_id: int
    category: str
    keywords: list[str]
    priority: int
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class UserInterestUpdate(BaseModel):
    keywords: list[str] | None = None
    priority: int | None = None

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v):
        if v is not None and (v < 1 or v > 5):
            raise ValueError("Priority must be between 1 and 5")
        return v
