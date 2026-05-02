from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


class CollectionCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    housing_block: str = Field(alias="housingBlock", min_length=1, max_length=32)
    room_number: str = Field(alias="roomNumber", min_length=1, max_length=32)
    collection_date: date = Field(alias="collectionDate")


class CollectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: str
    housing_block: str
    room_number: str
    collection_date: date
    status: str
    processed_at: datetime | None = None
    created_at: datetime


class PaginatedCollections(BaseModel):
    items: list[CollectionRead]
    total: int
    page: int
    page_size: int


class WasteProcessCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    collection_id: int | None = Field(default=None, alias="collectionId")
    source_location: str | None = Field(default=None, alias="sourceLocation", max_length=120)
    waste_category: Literal["Dry Waste", "Wet Waste"] = Field(alias="wasteCategory")
    waste_subtype: str = Field(alias="wasteSubtype", min_length=1, max_length=120)
    quantity: float = Field(gt=0)


class WasteEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: str
    waste_category: str
    waste_subtype: str
    housing_block: str
    room_number: str
    quantity: float
    collection_id: int | None
    created_at: datetime


class WetProcessingCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    compost_quantity: float = Field(default=0, alias="compostQuantity", ge=0)
    biogas_quantity: float = Field(default=0, alias="biogasQuantity", ge=0)
    notes: str | None = None


class ProcessingTotals(BaseModel):
    entries_count: int
    total_weight: float
    dry_weight: float
    wet_weight: float


class WetProcessingRecord(BaseModel):
    employee_id: str
    compost_quantity: float
    biogas_quantity: float
    total_wet_reference: float
    created_at: str
    notes: str | None = None


class WetProcessingStatus(BaseModel):
    total_wet_processed: float
    latest_update: WetProcessingRecord | None


class PaginatedWasteEntries(BaseModel):
    items: list[WasteEntryRead]
    total: int
    page: int
    page_size: int


class SummaryMetric(BaseModel):
    label: str
    value: float | int | str


class DashboardSummary(BaseModel):
    metrics: list[SummaryMetric]


class TrendPoint(BaseModel):
    date: str
    total_weight: float


class CategoryBreakdownPoint(BaseModel):
    label: str
    dry_weight: float
    wet_weight: float


class BlockStat(BaseModel):
    housing_block: str
    collections_count: int
    processed_weight: float


class OperatorStat(BaseModel):
    employee_id: str
    entries_count: int
    total_weight: float
