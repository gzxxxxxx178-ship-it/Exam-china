from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field, HttpUrl

from app.domain.enums import (
    LocationPrecision,
    RecruitmentStatus,
    RecruitmentType,
)


class SourceAccessBlockedError(RuntimeError):
    """官方站点明确拒绝自动访问时抛出，调用方必须暂停而非绕过。"""


class DiscoveredItem(BaseModel):
    source_item_id: str
    url: HttpUrl
    title_hint: str | None = None
    published_at_hint: datetime | None = None
    cursor: str | None = None


class RawPayload(BaseModel):
    source_item_id: str
    source_url: HttpUrl
    canonical_url: HttpUrl
    fetched_at: datetime
    http_status: int = Field(ge=100, le=599)
    content_type: str | None = None
    body: bytes
    etag: str | None = None
    last_modified: str | None = None


class ParsedLocation(BaseModel):
    raw_text: str
    province_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    city_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    division_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    precision: LocationPrecision
    confidence: float = Field(ge=0, le=1)


class ParsedPosition(BaseModel):
    source_position_id: str | None = None
    position_code: str | None = None
    title: str = Field(min_length=1)
    department: str | None = None
    headcount: int | None = Field(default=None, ge=0)
    education: str | None = None
    degree: str | None = None
    majors_raw: str | None = None
    political_status: str | None = None
    work_experience: str | None = None
    graduate_year: str | None = None
    age_requirement: str | None = None
    household_requirement: str | None = None
    other_requirements: str | None = None
    work_locations: list[ParsedLocation] = Field(default_factory=list)


class ParsedEvent(BaseModel):
    source_event_id: str
    event_type: str
    title: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    source_url: HttpUrl
    province_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    city_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class ParsedRecruitment(BaseModel):
    source_item_id: str
    source_batch_id: str
    title: str = Field(min_length=1)
    organization_name: str = Field(min_length=1)
    organization_type: str
    organization_official_url: HttpUrl | None = None
    recruitment_type: RecruitmentType
    audience_type: str | None = None
    year: int | None = Field(default=None, ge=2000, le=2200)
    batch_no: str | None = None
    publish_at: datetime | None = None
    application_start_at: datetime | None = None
    application_end_at: datetime | None = None
    status: RecruitmentStatus
    source_url: HttpUrl
    positions: list[ParsedPosition] = Field(default_factory=list)
    events: list[ParsedEvent] = Field(default_factory=list)


class SourceAdapter(Protocol):
    key: str

    async def discover(self, cursor: str | None) -> list[DiscoveredItem]: ...

    async def fetch(self, item: DiscoveredItem) -> RawPayload: ...

    async def parse(self, payload: RawPayload) -> ParsedRecruitment: ...
