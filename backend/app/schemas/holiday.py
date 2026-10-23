from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class HolidayCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    holiday_date: date
    description: str | None = Field(default=None, max_length=500)
    is_optional: bool = False


class HolidayUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    holiday_date: date | None = None
    description: str | None = Field(default=None, max_length=500)
    is_optional: bool | None = None


class HolidayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    holiday_date: date
    description: str | None
    is_optional: bool
