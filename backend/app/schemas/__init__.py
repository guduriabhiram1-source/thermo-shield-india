"""Pydantic request / response schemas (input validation)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from ..ml.features import CLASSES


# --- auth ---------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=256)
    confirm_password: str = Field(min_length=10, max_length=256)
    full_name: str = Field(default="", max_length=128)
    organisation: str = Field(default="", max_length=128)

    @model_validator(mode="after")
    def _match(self):
        if self.password != self.confirm_password:
            raise ValueError("password and confirm_password do not match")
        return self


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=512)


class LogoutRequest(BaseModel):
    refresh_token: str | None = Field(default=None, max_length=512)
    all_devices: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    organisation: str = ""
    is_verified: bool
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None


class UserUpdateRequest(BaseModel):
    role: Literal["ADMIN", "ANALYST", "VIEWER"] | None = None
    is_active: bool | None = None
    full_name: str | None = Field(default=None, max_length=128)
    organisation: str | None = Field(default=None, max_length=128)


class MessageResponse(BaseModel):
    message: str
    detail: str | None = None


# --- events -------------------------------------------------------------------
class AnalyzeEventRequest(BaseModel):
    """Re-run the pipeline for an incident, or analyse a coordinate (no detection is invented)."""
    incident_id: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    timestamp: datetime | None = None
    with_images: bool = False
    with_pdf: bool = False
    live_enrichment: bool = True


class VerifyRequest(BaseModel):
    action: Literal["CONFIRM", "CORRECT", "UNCERTAIN"]
    classification: str | None = None
    probable_cause: str = Field(default="", max_length=128)
    notes: str = Field(default="", max_length=4000)

    @field_validator("classification")
    @classmethod
    def _valid_class(cls, v):
        if v is not None and v not in CLASSES:
            raise ValueError(f"classification must be one of {CLASSES}")
        return v


class IngestRequest(BaseModel):
    mode: Literal["auto", "api", "public", "csv"] = "auto"
    csv_text: str | None = Field(default=None, max_length=50_000_000)
    csv_data_status: Literal["LIVE", "HISTORICAL", "auto"] = "auto"
    sources: str | None = None
    days: int | None = Field(default=None, ge=1, le=10)
    window: Literal["24h", "48h", "7d"] | None = None
    analyse: bool = True


class BackfillRequest(BaseModel):
    start_date: datetime
    end_date: datetime | None = None
    sources: str | None = None


class TrainRequest(BaseModel):
    note: str = Field(default="", max_length=256)
    min_accuracy: float = Field(default=0.7, ge=0.3, le=1.0)
    test_size: float = Field(default=0.25, ge=0.1, le=0.5)


class AlertSettingsUpdate(BaseModel):
    live_alerts_enabled: bool | None = None
    high_enabled: bool | None = None
    critical_enabled: bool | None = None
    recipients: str | None = Field(default=None, max_length=4000)
    cooldown_hours: int | None = Field(default=None, ge=0, le=720)
    min_confidence: float | None = Field(default=None, ge=0, le=1)


class TestAlertRequest(BaseModel):
    recipient: EmailStr


TokenResponse.model_rebuild()
