from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Organization, Position, PositionLocation, RecruitmentBatch
from app.domain.enums import (
    LocationPrecision,
    LocationType,
    RecruitmentStatus,
    RecruitmentType,
)


def _area_predicate(
    province_code: str | None,
    city_code: str | None,
    include_broader_scope: bool,
):
    location_match = PositionLocation.location_type == LocationType.WORK_LOCATION
    if city_code:
        exact = PositionLocation.city_code == city_code
        conditions = [exact]
        if include_broader_scope:
            conditions.extend(
                [
                    (PositionLocation.province_code == province_code)
                    & (PositionLocation.precision == LocationPrecision.PROVINCE),
                    PositionLocation.precision.in_(
                        [LocationPrecision.NATIONWIDE, LocationPrecision.UNKNOWN]
                    ),
                ]
            )
        location_match &= or_(*conditions)
    elif province_code:
        conditions = [PositionLocation.province_code == province_code]
        if include_broader_scope:
            conditions.append(
                PositionLocation.precision.in_(
                    [LocationPrecision.NATIONWIDE, LocationPrecision.UNKNOWN]
                )
            )
        location_match &= or_(*conditions)
    else:
        return None
    return exists(
        select(PositionLocation.id).where(
            PositionLocation.position_id == Position.id, location_match
        )
    )


def build_position_query(
    *,
    province_code: str | None = None,
    city_code: str | None = None,
    categories: list[RecruitmentType] | None = None,
    statuses: list[RecruitmentStatus] | None = None,
    keyword: str | None = None,
    include_broader_scope: bool = False,
) -> Select:
    query = (
        select(Position)
        .join(Position.batch)
        .join(RecruitmentBatch.organization)
        .options(
            selectinload(Position.locations),
            selectinload(Position.batch).selectinload(RecruitmentBatch.organization),
        )
    )
    area = _area_predicate(province_code, city_code, include_broader_scope)
    if area is not None:
        query = query.where(area)
    if categories:
        query = query.where(RecruitmentBatch.recruitment_type.in_(categories))
    if statuses:
        query = query.where(RecruitmentBatch.status.in_(statuses))
    if keyword:
        pattern = f"%{keyword.strip()}%"
        query = query.where(
            or_(
                Position.title.ilike(pattern),
                Position.department.ilike(pattern),
                Position.majors_raw.ilike(pattern),
                Organization.canonical_name.ilike(pattern),
            )
        )
    return query.order_by(
        RecruitmentBatch.publish_at.desc().nullslast(), Position.id.desc()
    )


def list_positions(
    session: Session,
    *,
    page: int,
    page_size: int,
    **filters,
) -> tuple[list[Position], int]:
    query = build_position_query(**filters)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = list(
        session.scalars(query.offset((page - 1) * page_size).limit(page_size)).unique()
    )
    return items, total

