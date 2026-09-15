from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import (
    CrawlStatus,
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
    province_name: str | None
    city_name: str | None
    location_type: LocationType
    precision: LocationPrecision
    confidence: float


class PositionOut(BaseModel):
    id: int
    title: str
    position_code: str | None
    employer_name: str | None
    department: str | None
    headcount: int | None
    education: str | None
    degree: str | None
    majors_raw: str | None
    political_status: str | None
    work_experience: str | None
    other_requirements: str | None
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


class CityOptionOut(BaseModel):
    name: str
    code: str | None
    position_count: int


class ProvinceOptionOut(BaseModel):
    name: str
    code: str | None
    position_count: int
    cities: list[CityOptionOut]


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_event_id: str
    event_type: str
    title: str
    start_at: datetime | None
    end_at: datetime | None
    source_url: str
    status: str


class BatchSummaryOut(BaseModel):
    id: int
    title: str
    year: int | None
    recruitment_type: RecruitmentType
    status: RecruitmentStatus
    organization_name: str
    publish_at: datetime | None
    application_start_at: datetime | None
    application_end_at: datetime | None
    source_url: str
    event_count: int


class BatchDetailOut(BatchSummaryOut):
    events: list[EventOut]
    position_count: int


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


class CrawlRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    started_at: datetime
    finished_at: datetime | None
    status: CrawlStatus
    fetched_count: int
    parsed_count: int
    new_count: int
    changed_count: int
    error_type: str | None
    error_message: str | None
