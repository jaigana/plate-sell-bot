from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PlateInput(BaseModel):
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    plate_number: str = Field(min_length=1, max_length=30)

    @field_validator("country_code")
    @classmethod
    def uppercase_country(cls, value: str) -> str:
        return value.upper()


class SaleCreateRequest(BaseModel):
    plate_id: int = Field(gt=0)
    price: int = Field(ge=1, le=99_999)


class AuctionCreateRequest(BaseModel):
    plate_id: int = Field(gt=0)
    starting_price: int = Field(ge=1, le=99_999)
    duration_minutes: int = Field(ge=1, le=1_440)


class BalanceAdjustment(BaseModel):
    user_id: int = Field(gt=0)
    amount: int = Field(ge=-99_999, le=99_999)
    reason: str = Field(min_length=1, max_length=240)
