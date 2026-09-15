from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import (
    LocationPrecision,
    LocationType,
    RecruitmentStatus,
    RecruitmentType,
    SourceHealth,
)


class DivisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    level: str
    parent_id: int | None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    raw_text: str
    province_code: str | None
    city_code: str | None
    location_type: LocationType
    precision: LocationPrecision
    confidence: float


class PositionOut(BaseModel):
    id: int
    title: str
    position_code: str | None
    department: str | None
    headcount: int | None
    education: str | None
    majors_raw: str | None
    organization_name: str
    batch_title: str
    recruitment_type: RecruitmentType
    status: RecruitmentStatus
    application_end_at: datetime | None
    source_url: str
    locations: list[LocationOut]


class PositionPage(BaseModel):
    items: list[PositionOut]
    total: int
    page: int
    page_size: int


class SourceCoverageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    category: str
    authority_level: str
    province_code: str | None
    city_code: str | None
    enabled: bool
    last_success_at: datetime | None
    health_status: SourceHealth

