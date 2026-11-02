from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


# ---------- Auth ----------
class UserCreate(BaseModel):
    # Plain str + light validation avoids the extra email-validator dependency.
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower()


class UserLogin(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str


# ---------- Links ----------
class LinkCreate(BaseModel):
    url: HttpUrl
    custom_alias: Optional[str] = Field(default=None, min_length=3, max_length=32)
    expires_at: Optional[datetime] = None


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    short_url: str
    target_url: str
    created_at: datetime
    expires_at: Optional[datetime]
    is_active: bool


# ---------- Analytics ----------
class CountItem(BaseModel):
    label: str
    count: int


class DayCount(BaseModel):
    date: str
    count: int


class AnalyticsOut(BaseModel):
    code: str
    total_clicks: int
    clicks_by_day: List[DayCount]
    top_referrers: List[CountItem]
    browsers: List[CountItem]
    devices: List[CountItem]
    countries: List[CountItem]
