from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    AdministrativeDivision,
    CrawlRun,
    ExamEvent,
    RecruitmentBatch,
    SourceRegistry,
)
from app.db.session import get_db
from app.domain.enums import RecruitmentStatus, RecruitmentType
from app.schemas import (
    BatchDetailOut,
    BatchSummaryOut,
    CrawlRunOut,
    DivisionOut,
    LocationOut,
    PositionOut,
    PositionPage,
    SourceCoverageOut,
)
from app.services.positions import list_positions


router = APIRouter()


@router.get("/health")
def health(session: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


@router.get("/api/divisions", response_model=list[DivisionOut])
def divisions(
    session: Annotated[Session, Depends(get_db)],
    parent_code: str | None = None,
    level: str | None = None,
) -> list[AdministrativeDivision]:
    query = select(AdministrativeDivision).where(AdministrativeDivision.valid_to.is_(None))
    if parent_code:
        parent_id = select(AdministrativeDivision.id).where(
            AdministrativeDivision.code == parent_code,
            AdministrativeDivision.valid_to.is_(None),
        )
        query = query.where(AdministrativeDivision.parent_id == parent_id.scalar_subquery())
    if level:
        query = query.where(AdministrativeDivision.level == level.upper())
    return list(session.scalars(query.order_by(AdministrativeDivision.code)))


@router.get("/api/positions", response_model=PositionPage)
def positions(
    session: Annotated[Session, Depends(get_db)],
    province_code: str | None = None,
    city_code: str | None = None,
    categories: Annotated[list[RecruitmentType] | None, Query()] = None,
    statuses: Annotated[list[RecruitmentStatus] | None, Query()] = None,
    keyword: str | None = None,
    include_broader_scope: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PositionPage:
    items, total = list_positions(
        session,
        province_code=province_code,
        city_code=city_code,
        categories=categories,
        statuses=statuses,
        keyword=keyword,
        include_broader_scope=include_broader_scope,
        page=page,
        page_size=page_size,
    )
    return PositionPage(
        items=[
            PositionOut(
                id=item.id,
                title=item.title,
                position_code=item.position_code,
                department=item.department,
                headcount=item.headcount,
                education=item.education,
                majors_raw=item.majors_raw,
                organization_name=item.batch.organization.canonical_name,
                batch_title=item.batch.title,
                recruitment_type=item.batch.recruitment_type,
                status=item.batch.status,
                application_end_at=item.batch.application_end_at,
                source_url=item.batch.source_url,
                locations=[LocationOut.model_validate(location) for location in item.locations],
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/api/batches", response_model=list[BatchSummaryOut])
def batches(
    session: Annotated[Session, Depends(get_db)],
    category: RecruitmentType | None = None,
    year: int | None = None,
) -> list[BatchSummaryOut]:
    event_count = (
        select(func.count(ExamEvent.id))
        .where(ExamEvent.batch_id == RecruitmentBatch.id)
        .correlate(RecruitmentBatch)
        .scalar_subquery()
    )
    query = select(RecruitmentBatch, event_count).options(
        selectinload(RecruitmentBatch.organization)
    )
    if category:
        query = query.where(RecruitmentBatch.recruitment_type == category)
    if year:
        query = query.where(RecruitmentBatch.year == year)
    rows = session.execute(
        query.order_by(RecruitmentBatch.publish_at.desc().nullslast())
    ).all()
    return [
        BatchSummaryOut(
            id=batch.id,
            title=batch.title,
            year=batch.year,
            recruitment_type=batch.recruitment_type,
            status=batch.status,
            organization_name=batch.organization.canonical_name,
            publish_at=batch.publish_at,
            application_start_at=batch.application_start_at,
            application_end_at=batch.application_end_at,
            source_url=batch.source_url,
            event_count=count,
        )
        for batch, count in rows
    ]


@router.get("/api/batches/{batch_id}", response_model=BatchDetailOut)
def batch_detail(
    batch_id: int, session: Annotated[Session, Depends(get_db)]
) -> BatchDetailOut:
    batch = session.scalar(
        select(RecruitmentBatch)
        .where(RecruitmentBatch.id == batch_id)
        .options(
            selectinload(RecruitmentBatch.organization),
            selectinload(RecruitmentBatch.positions),
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="招聘批次不存在")
    events = list(
        session.scalars(
            select(ExamEvent)
            .where(ExamEvent.batch_id == batch_id)
            .order_by(ExamEvent.start_at.asc().nullslast(), ExamEvent.id)
        )
    )
    return BatchDetailOut(
        id=batch.id,
        title=batch.title,
        year=batch.year,
        recruitment_type=batch.recruitment_type,
        status=batch.status,
        organization_name=batch.organization.canonical_name,
        publish_at=batch.publish_at,
        application_start_at=batch.application_start_at,
        application_end_at=batch.application_end_at,
        source_url=batch.source_url,
        event_count=len(events),
        events=events,
        position_count=len(batch.positions),
    )


@router.get("/api/sources/coverage", response_model=list[SourceCoverageOut])
def source_coverage(
    session: Annotated[Session, Depends(get_db)],
) -> list[SourceRegistry]:
    return list(session.scalars(select(SourceRegistry).order_by(SourceRegistry.key)))


@router.get("/api/crawl-runs", response_model=list[CrawlRunOut])
def crawl_runs(
    session: Annotated[Session, Depends(get_db)],
    source_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[CrawlRun]:
    query = select(CrawlRun)
    if source_id is not None:
        query = query.where(CrawlRun.source_id == source_id)
    return list(session.scalars(query.order_by(CrawlRun.started_at.desc()).limit(limit)))
