from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.domain.enums import (
    CrawlStatus,
    LocationPrecision,
    LocationType,
    RecruitmentStatus,
    RecruitmentType,
    SourceHealth,
)


def enum_column(enum_type: type, name: str) -> Enum:
    return Enum(enum_type, name=name, native_enum=False, validate_strings=True)


class AdministrativeDivision(Base):
    __tablename__ = "administrative_division"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(6), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("administrative_division.id"), nullable=True
    )
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    parent: Mapped[AdministrativeDivision | None] = relationship(
        remote_side="AdministrativeDivision.id", back_populates="children"
    )
    children: Mapped[list[AdministrativeDivision]] = relationship(
        back_populates="parent"
    )

    __table_args__ = (
        UniqueConstraint("code", "valid_from", name="uq_division_code_version"),
    )


class SourceRegistry(Base, TimestampMixin):
    __tablename__ = "source_registry"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    authority_level: Mapped[str] = mapped_column(String(30), nullable=False)
    province_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    city_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    adapter_key: Mapped[str] = mapped_column(String(120), nullable=False)
    crawl_policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    interval_minutes: Mapped[int] = mapped_column(Integer, default=240, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    health_status: Mapped[SourceHealth] = mapped_column(
        enum_column(SourceHealth, "source_health"),
        default=SourceHealth.UNKNOWN,
        nullable=False,
    )


class CrawlRun(Base):
    __tablename__ = "crawl_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_registry.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[CrawlStatus] = mapped_column(
        enum_column(CrawlStatus, "crawl_status"), nullable=False
    )
    fetched_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parsed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)


class Organization(Base, TimestampMixin):
    __tablename__ = "organization"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    organization_type: Mapped[str] = mapped_column(String(80), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("organization.id"))
    province_code: Mapped[str | None] = mapped_column(String(6), index=True)
    city_code: Mapped[str | None] = mapped_column(String(6), index=True)
    official_url: Mapped[str | None] = mapped_column(Text)


class RecruitmentBatch(Base, TimestampMixin):
    __tablename__ = "recruitment_batch"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(ForeignKey("organization.id"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_registry.id"), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    recruitment_type: Mapped[RecruitmentType] = mapped_column(
        enum_column(RecruitmentType, "recruitment_type"), index=True, nullable=False
    )
    audience_type: Mapped[str | None] = mapped_column(String(80))
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    batch_no: Mapped[str | None] = mapped_column(String(80))
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    application_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[RecruitmentStatus] = mapped_column(
        enum_column(RecruitmentStatus, "recruitment_status"), index=True, nullable=False
    )
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    organization: Mapped[Organization] = relationship()
    positions: Mapped[list[Position]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


class Position(Base, TimestampMixin):
    __tablename__ = "position"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("recruitment_batch.id"), index=True)
    source_position_id: Mapped[str | None] = mapped_column(String(160))
    position_code: Mapped[str | None] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    department: Mapped[str | None] = mapped_column(String(300))
    headcount: Mapped[int | None] = mapped_column(Integer)
    education: Mapped[str | None] = mapped_column(String(80), index=True)
    degree: Mapped[str | None] = mapped_column(String(80))
    majors_raw: Mapped[str | None] = mapped_column(Text)
    political_status: Mapped[str | None] = mapped_column(String(120))
    work_experience: Mapped[str | None] = mapped_column(String(200))
    graduate_year: Mapped[str | None] = mapped_column(String(80))
    age_requirement: Mapped[str | None] = mapped_column(String(160))
    household_requirement: Mapped[str | None] = mapped_column(String(200))
    other_requirements: Mapped[str | None] = mapped_column(Text)

    batch: Mapped[RecruitmentBatch] = relationship(back_populates="positions")
    locations: Mapped[list[PositionLocation]] = relationship(
        back_populates="position", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "batch_id", "source_position_id", name="uq_position_batch_source_id"
        ),
    )


class PositionLocation(Base):
    __tablename__ = "position_location"

    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("position.id"), index=True)
    division_id: Mapped[int | None] = mapped_column(
        ForeignKey("administrative_division.id"), nullable=True, index=True
    )
    province_code: Mapped[str | None] = mapped_column(String(6), index=True)
    city_code: Mapped[str | None] = mapped_column(String(6), index=True)
    location_type: Mapped[LocationType] = mapped_column(
        enum_column(LocationType, "location_type"), index=True, nullable=False
    )
    precision: Mapped[LocationPrecision] = mapped_column(
        enum_column(LocationPrecision, "location_precision"), index=True, nullable=False
    )
    raw_text: Mapped[str] = mapped_column(String(300), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)

    position: Mapped[Position] = relationship(back_populates="locations")
    division: Mapped[AdministrativeDivision | None] = relationship()

    __table_args__ = (
        Index("ix_position_location_area", "province_code", "city_code", "precision"),
    )


class ExamEvent(Base, TimestampMixin):
    __tablename__ = "exam_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("recruitment_batch.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    province_code: Mapped[str | None] = mapped_column(String(6), index=True)
    city_code: Mapped[str | None] = mapped_column(String(6), index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="SCHEDULED")


class RawDocument(Base):
    __tablename__ = "raw_document"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_registry.id"), index=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(160))
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    parser_version: Mapped[str | None] = mapped_column(String(80))
    parse_status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING")


class Revision(Base):
    __tablename__ = "revision"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("recruitment_batch.id"), index=True)
    raw_document_id: Mapped[int] = mapped_column(ForeignKey("raw_document.id"))
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_fields: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("batch_id", "revision_no", name="uq_revision_batch_number"),
    )
