from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ActivityPayload(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    description: str | None = ""
    fiscal_year: int = Field(default_factory=lambda: datetime.now().year, ge=2024, le=2100)
    budget_ceiling: float = Field(gt=0)
    default_province: str | None = Field(default="DKI JAKARTA", max_length=120)
    origin_city: str | None = Field(default="JAKARTA", max_length=120)


class SubComponentPayload(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    notes: str | None = ""


class FormSelectionPayload(BaseModel):
    form_code: str = Field(min_length=2, max_length=80)
    attributes: dict[str, Any] = Field(default_factory=dict)


class AccountSelectionTogglePayload(BaseModel):
    is_selected: bool


class ManualAccountPayload(BaseModel):
    account_code: str = Field(min_length=6, max_length=10)
    recommendation_reason: str | None = "Akun ditambahkan manual oleh pengguna."


class BudgetLinePayload(BaseModel):
    item_name: str = Field(min_length=2, max_length=200)
    specification: str | None = ""
    volume: float = Field(default=0, ge=0)
    unit: str = Field(default="Paket", min_length=1, max_length=50)
    unit_price: float = Field(default=0, ge=0)


class BudgetLineUpdatePayload(BaseModel):
    item_name: str | None = Field(default=None, min_length=2, max_length=200)
    specification: str | None = None
    volume: float | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    unit_price: float | None = Field(default=None, ge=0)

