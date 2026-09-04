"""Pydantic request/response schemas — every endpoint validates input."""
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=10, max_length=15)
    email: Optional[str] = Field(default=None, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["applicant", "officer", "admin", "consultant"] = "applicant"
    invite_code: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def phone_digits(cls, v: str) -> str:
        digits = v.replace("-", "").replace(" ", "").replace("+", "")
        if not digits.isdigit():
            raise ValueError("phone must contain only digits")
        return digits


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=200)  # phone or email
    password: str = Field(min_length=1, max_length=128)


class ProfileRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    sector: str = Field(min_length=2, max_length=60)
    district: str = Field(default="", max_length=80)
    industrial_zone: str = Field(default="", max_length=80)
    investment_size: float = Field(default=0, ge=0, le=10_000_000_000)
    employee_count: int = Field(default=0, ge=0, le=1_000_000)
    project_stage: Literal["planning", "under_construction", "operational",
                           "expansion"] = "planning"
    authorized_person: str = Field(default="", max_length=120)
    pan: str = Field(default="", max_length=20)
    gst: str = Field(default="", max_length=20)
    registration_no: str = Field(default="", max_length=40)


class CreateApplicationRequest(BaseModel):
    approval_id: str = Field(min_length=2, max_length=80)


class DecisionRequest(BaseModel):
    action: Literal["verify", "clarify", "approve", "reject"]
    notes: str = Field(default="", max_length=4000)
    clarification_text: str = Field(default="", max_length=4000)


class InspectionRequest(BaseModel):
    type: str = Field(default="routine", max_length=60)
    scheduled_date: str = Field(min_length=8, max_length=10)
    coordinated_with: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("scheduled_date")
    @classmethod
    def date_shape(cls, v: str) -> str:
        from datetime import datetime
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("scheduled_date must be YYYY-MM-DD")
        return v


class RespondClarificationRequest(BaseModel):
    response: str = Field(min_length=2, max_length=4000)


class GrievanceRequest(BaseModel):
    application_id: Optional[str] = None
    reason: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=2000)


class GreenChannelToggleRequest(BaseModel):
    enabled: bool
    approval_id: Optional[str] = None  # reserved for per-type toggles


class SmsDispatchRequest(BaseModel):
    user_id: str = ""
    application_id: str = ""
    message: str = Field(min_length=1, max_length=300)


class DigiLockerConsentRequest(BaseModel):
    aadhaar_number: str = Field(min_length=12, max_length=24)


class DigiLockerVerifyRequest(BaseModel):
    otp: str = Field(min_length=4, max_length=8)


class DigiLockerApplyRequest(BaseModel):
    pan: str = Field(default="", max_length=20)
    gst: str = Field(default="", max_length=20)
    authorized_person: str = Field(default="", max_length=120)
