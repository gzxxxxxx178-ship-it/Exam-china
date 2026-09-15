from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pdfplumber
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.db.models import (
    AdministrativeDivision,
    Organization,
    Position,
    PositionLocation,
    RawDocument,
    RecruitmentBatch,
    SourceRegistry,
)
from app.domain.enums import LocationPrecision, LocationType, RecruitmentStatus, RecruitmentType


SOURCE_KEY = "state_grid"
PARSER_VERSION = "state-grid-pdf-v1"
EXPECTED_HEADERS = ["所在地", "单位名称", "招聘专业类别", "学历要求"]
JIANGXI_PROVINCE_CODE = "360000"
JIANGXI_CITY_CODES = {
    "南昌市": "360100",
    "景德镇市": "360200",
    "萍乡市": "360300",
    "九江市": "360400",
    "新余市": "360500",
    "鹰潭市": "360600",
    "赣州市": "360700",
    "吉安市": "360800",
    "宜春市": "360900",
    "抚州市": "361000",
    "上饶市": "361100",
}


@dataclass(frozen=True)
class StateGridPdfRow:
    city_name: str
    employer_name: str
    majors: str
    education: str


@dataclass(frozen=True)
class StateGridPdfDocument:
    title: str
    year: int
    rows: list[StateGridPdfRow]


def _text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_table(table: list[list[str | None]]) -> list[StateGridPdfRow]:
    if not table or [_text(cell) for cell in table[0]] != EXPECTED_HEADERS:
        raise ValueError("PDF 未包含预期的招聘需求表头")
    rows: list[StateGridPdfRow] = []
    current_city: str | None = None
    for row_index, row in enumerate(table[1:], start=2):
        if len(row) != 4:
            raise ValueError(f"PDF 第 {row_index} 行列数异常")
        city, employer, majors, education = (_text(value) for value in row)
        current_city = city or current_city
        if not current_city or not employer or not majors or not education:
            raise ValueError(f"PDF 第 {row_index} 行存在无法识别的必填字段")
        if current_city not in JIANGXI_CITY_CODES:
            raise ValueError(f"PDF 第 {row_index} 行包含未支持的江西地市: {current_city}")
        rows.append(StateGridPdfRow(current_city, employer, majors, education))
    if not rows:
        raise ValueError("PDF 招聘需求表不包含岗位记录")
    return rows


def parse_state_grid_pdf(path: Path) -> StateGridPdfDocument:
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) != 1:
            raise ValueError("当前导入器仅支持单页国家电网招聘需求 PDF")
        page = pdf.pages[0]
        title = _text(page.extract_text() or "").split(" 所在地", maxsplit=1)[0]
        year_match = re.search(r"(20\d{2})年", title)
        if not year_match:
            raise ValueError("PDF 标题未包含招聘年度")
        table = page.extract_table()
    return StateGridPdfDocument(title=title, year=int(year_match.group(1)), rows=parse_table(table or []))


def _division_indexes(session: Session) -> tuple[dict[str, AdministrativeDivision], dict[str, AdministrativeDivision]]:
    divisions = list(
        session.scalars(
            select(AdministrativeDivision).where(AdministrativeDivision.valid_to.is_(None))
        )
    )
    by_code = {item.code: item for item in divisions}
    return ({item.name: item for item in divisions if item.level == "PROVINCE"}, by_code)


def _store_raw_pdf(
    session: Session,
    settings: Settings,
    source: SourceRegistry,
    path: Path,
    digest: str,
) -> RawDocument:
    canonical_url = f"local-import://{SOURCE_KEY}/{path.name}"
    existing = session.scalar(
        select(RawDocument).where(
            RawDocument.source_id == source.id,
            RawDocument.canonical_url == canonical_url,
            RawDocument.content_hash == digest,
        )
    )
    if existing:
        return existing
    target_dir = settings.raw_data_path / SOURCE_KEY / "imports"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{digest[:16]}-{path.name}"
    if not target.exists():
        shutil.copy2(path, target)
    raw = RawDocument(
        source_id=source.id,
        source_url=canonical_url,
        canonical_url=canonical_url,
        fetched_at=datetime.now(UTC),
        http_status=200,
        content_type="application/pdf",
        content_hash=digest,
        storage_path=str(target.relative_to(settings.raw_data_path.parent)),
        parser_version=PARSER_VERSION,
        parse_status="PARSED",
    )
    session.add(raw)
    return raw


def import_state_grid_pdf(
    session: Session,
    settings: Settings,
    path: Path,
    *,
    dry_run: bool = False,
) -> dict[str, object]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    document = parse_state_grid_pdf(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    source = session.scalar(select(SourceRegistry).where(SourceRegistry.key == SOURCE_KEY))
    if source is None:
        raise ValueError("请先运行 init-db，来源 state_grid 尚未初始化")
    organization = session.scalar(
        select(Organization).where(Organization.canonical_name == "江西科晨技术有限公司")
    )
    if organization is None:
        organization = Organization(
            canonical_name="江西科晨技术有限公司",
            organization_type=RecruitmentType.SOE_STATE_GRID,
            province_code=JIANGXI_PROVINCE_CODE,
        )
        if not dry_run:
            session.add(organization)
            session.flush()

    batch_source_id = f"state-grid-jiangxi-kechen-{document.year}-graduate"
    batch = session.scalar(
        select(RecruitmentBatch)
        .where(
            RecruitmentBatch.source_id == source.id,
            RecruitmentBatch.source_batch_id == batch_source_id,
        )
        .options(selectinload(RecruitmentBatch.positions).selectinload(Position.locations))
    )
    now = datetime.now(UTC)
    created_batch = batch is None
    if batch is None and not dry_run:
        batch = RecruitmentBatch(
            source_batch_id=batch_source_id,
            organization_id=organization.id,
            source_id=source.id,
            title=document.title,
            recruitment_type=RecruitmentType.SOE_STATE_GRID,
            audience_type="GRADUATE",
            year=document.year,
            status=RecruitmentStatus.UNKNOWN,
            source_url=f"local-import://{SOURCE_KEY}/{path.name}",
            first_seen_at=now,
            last_seen_at=now,
            content_hash=digest,
        )
        session.add(batch)
        session.flush()

    divisions_by_name, divisions_by_code = _division_indexes(session)
    province = divisions_by_name.get("江西省")
    existing = {position.source_position_id: position for position in batch.positions} if batch else {}
    inserted = updated = unchanged = 0
    notice = "源 PDF 未提供具体岗位名称、招聘人数、报名时间或截止时间；最终招聘数量以核定结果为准。"
    for row in document.rows:
        source_id = hashlib.sha256(row.employer_name.encode("utf-8")).hexdigest()[:16]
        source_position_id = f"kechen-{document.year}-{source_id}"
        values = {
            "source_position_id": source_position_id,
            "employer_name": row.employer_name,
            "title": f"{document.year}年毕业生招聘（{row.majors}）",
            "education": row.education,
            "majors_raw": row.majors,
            "other_requirements": notice,
        }
        city_code = JIANGXI_CITY_CODES[row.city_name]
        division = divisions_by_code.get(city_code) or province
        location_values = {
            "division_id": division.id if division else None,
            "province_code": JIANGXI_PROVINCE_CODE,
            "city_code": city_code,
            "province_name": "江西省",
            "city_name": row.city_name,
            "location_type": LocationType.WORK_LOCATION,
            "precision": LocationPrecision.CITY,
            "raw_text": f"江西省{row.city_name}",
            "confidence": 1.0,
        }
        position = existing.get(source_position_id)
        if position is None:
            inserted += 1
            if not dry_run:
                position = Position(batch_id=batch.id, **values)
                position.locations.append(PositionLocation(**location_values))
                session.add(position)
            continue
        work_location = next(
            (item for item in position.locations if item.location_type == LocationType.WORK_LOCATION),
            None,
        )
        values_changed = any(getattr(position, key) != value for key, value in values.items())
        location_changed = work_location is None or any(
            getattr(work_location, key) != value for key, value in location_values.items()
        )
        if values_changed or location_changed:
            updated += 1
            if not dry_run:
                for key, value in values.items():
                    setattr(position, key, value)
                if work_location is None:
                    position.locations.append(PositionLocation(**location_values))
                else:
                    for key, value in location_values.items():
                        setattr(work_location, key, value)
        else:
            unchanged += 1

    if not dry_run:
        _store_raw_pdf(session, settings, source, path, digest)
        batch.last_seen_at = now
        batch.content_hash = digest
        session.commit()
    return {
        "source": SOURCE_KEY,
        "dry_run": dry_run,
        "title": document.title,
        "year": document.year,
        "positions": len(document.rows),
        "headcount": None,
        "created_batch": created_batch,
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "sha256": digest,
    }
