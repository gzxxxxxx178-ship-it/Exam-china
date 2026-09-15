from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import xlrd
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.db.models import (
    AdministrativeDivision,
    Position,
    PositionLocation,
    RawDocument,
    RecruitmentBatch,
    SourceRegistry,
)
from app.domain.enums import LocationPrecision, LocationType


SOURCE_KEY = "national_civil_service"
DEFAULT_BATCH_ID = "national-civil-service-2026"
PARSER_VERSION = "national-exam-xls-v1"

REQUIRED_COLUMNS = {
    "部门代码",
    "部门名称",
    "用人司局",
    "招考职位",
    "职位代码",
    "招考人数",
    "专业",
    "学历",
    "工作地点",
}

PROVINCE_CODES = {
    "北京市": "110000",
    "天津市": "120000",
    "河北省": "130000",
    "山西省": "140000",
    "内蒙古自治区": "150000",
    "辽宁省": "210000",
    "吉林省": "220000",
    "黑龙江省": "230000",
    "上海市": "310000",
    "江苏省": "320000",
    "浙江省": "330000",
    "安徽省": "340000",
    "福建省": "350000",
    "江西省": "360000",
    "山东省": "370000",
    "河南省": "410000",
    "湖北省": "420000",
    "湖南省": "430000",
    "广东省": "440000",
    "广西壮族自治区": "450000",
    "海南省": "460000",
    "重庆市": "500000",
    "四川省": "510000",
    "贵州省": "520000",
    "云南省": "530000",
    "西藏自治区": "540000",
    "陕西省": "610000",
    "甘肃省": "620000",
    "青海省": "630000",
    "宁夏回族自治区": "640000",
    "新疆维吾尔自治区": "650000",
    "台湾省": "710000",
    "香港特别行政区": "810000",
    "澳门特别行政区": "820000",
}
MUNICIPALITIES = {"北京市", "天津市", "上海市", "重庆市"}
CITY_PATTERN = re.compile(r"^(.+?(?:自治州|地区|盟|市))")
DIRECT_ADMIN_PATTERN = re.compile(r"^(.+?(?:自治县|县|林区|新区|区))")


@dataclass(frozen=True)
class ParsedLocation:
    raw_text: str
    province_name: str | None
    city_name: str | None
    province_code: str | None
    city_code: str | None
    division_id: int | None
    precision: LocationPrecision
    confidence: float


@dataclass(frozen=True)
class ParsedWorkbook:
    rows: list[dict[str, str]]
    sheet_counts: dict[str, int]
    headcount: int


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return re.sub(r"[\u3000\t ]+", " ", str(value)).strip()


def _header_row(sheet: xlrd.sheet.Sheet) -> tuple[int, list[str]]:
    for row_index in range(min(sheet.nrows, 20)):
        values = [_text(sheet.cell_value(row_index, col)) for col in range(sheet.ncols)]
        if REQUIRED_COLUMNS.issubset(values):
            return row_index, values
    raise ValueError(f"工作表“{sheet.name}”未找到完整表头")


def parse_workbook(path: Path) -> ParsedWorkbook:
    workbook = xlrd.open_workbook(str(path), on_demand=True)
    rows: list[dict[str, str]] = []
    sheet_counts: dict[str, int] = {}
    total_headcount = 0
    seen_keys: set[str] = set()
    for sheet in workbook.sheets():
        header_index, headers = _header_row(sheet)
        count = 0
        for row_index in range(header_index + 1, sheet.nrows):
            row = {
                header: _text(sheet.cell_value(row_index, col_index))
                for col_index, header in enumerate(headers)
                if header
            }
            if not row.get("职位代码"):
                continue
            source_id = f"{row['部门代码']}:{row['职位代码']}"
            if source_id in seen_keys:
                raise ValueError(f"来源唯一键重复: {source_id}")
            seen_keys.add(source_id)
            try:
                headcount = int(float(row["招考人数"]))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{sheet.name} 第 {row_index + 1} 行招考人数无效: {row['招考人数']}"
                ) from exc
            if headcount < 1:
                raise ValueError(f"{sheet.name} 第 {row_index + 1} 行招考人数小于 1")
            row["_source_position_id"] = source_id
            row["_sheet_name"] = sheet.name
            row["_headcount"] = str(headcount)
            rows.append(row)
            count += 1
            total_headcount += headcount
        sheet_counts[sheet.name] = count
    workbook.release_resources()
    return ParsedWorkbook(rows=rows, sheet_counts=sheet_counts, headcount=total_headcount)


def _division_indexes(
    session: Session,
) -> tuple[dict[str, AdministrativeDivision], dict[tuple[str, str], AdministrativeDivision]]:
    divisions = list(
        session.scalars(
            select(AdministrativeDivision).where(AdministrativeDivision.valid_to.is_(None))
        )
    )
    provinces: dict[str, AdministrativeDivision] = {}
    cities: dict[tuple[str, str], AdministrativeDivision] = {}
    by_id = {item.id: item for item in divisions}
    for item in divisions:
        names = [item.name, *item.aliases]
        if item.level == "PROVINCE":
            for name in names:
                provinces[name] = item
        elif item.level == "CITY" and item.parent_id in by_id:
            province = by_id[item.parent_id]
            for name in names:
                cities[(province.name, name)] = item
    return provinces, cities


def parse_location(
    raw_text: str,
    provinces: dict[str, AdministrativeDivision] | None = None,
    cities: dict[tuple[str, str], AdministrativeDivision] | None = None,
) -> ParsedLocation:
    provinces = provinces or {}
    cities = cities or {}
    raw = _text(raw_text)
    if raw in {"全国", "全国范围", "全国各地"}:
        return ParsedLocation(
            raw, None, None, None, None, None, LocationPrecision.NATIONWIDE, 1.0
        )

    province_name = next((name for name in PROVINCE_CODES if raw.startswith(name)), None)
    is_xpcc = raw.startswith("新疆生产建设兵团")
    if province_name is None and is_xpcc:
        province_name = "新疆维吾尔自治区"
    if province_name is None:
        return ParsedLocation(raw, None, None, None, None, None, LocationPrecision.UNKNOWN, 0.0)

    province = provinces.get(province_name)
    province_code = province.code if province else PROVINCE_CODES[province_name]
    remainder = raw[len("新疆生产建设兵团") :] if is_xpcc else raw[len(province_name) :]
    city_name: str | None = None
    precision = LocationPrecision.PROVINCE
    if province_name in MUNICIPALITIES and remainder:
        city_name = province_name
        precision = LocationPrecision.COUNTY
    elif remainder:
        match = CITY_PATTERN.match(remainder)
        if match:
            city_name = match.group(1)
            precision = (
                LocationPrecision.COUNTY
                if len(remainder) > len(city_name)
                else LocationPrecision.CITY
            )
        else:
            direct_admin = DIRECT_ADMIN_PATTERN.match(remainder)
            if direct_admin:
                city_name = direct_admin.group(1)
                precision = LocationPrecision.COUNTY

    city = cities.get((province_name, city_name)) if city_name else None
    division = city or province
    confidence = 1.0 if division or province_code else 0.8
    return ParsedLocation(
        raw,
        province_name,
        city_name,
        province_code,
        city.code if city else None,
        division.id if division else None,
        precision,
        confidence,
    )


def _position_values(row: dict[str, str]) -> dict[str, object]:
    phones = " / ".join(
        value for key in ("咨询电话1", "咨询电话2", "咨询电话3") if (value := row.get(key))
    )
    return {
        "source_position_id": row["_source_position_id"],
        "position_code": row["职位代码"],
        "employer_name": row["部门名称"],
        "title": row["招考职位"],
        "department": row["用人司局"],
        "institution_nature": row.get("机构性质") or None,
        "position_attribute": row.get("职位属性") or None,
        "position_distribution": row.get("职位分布") or None,
        "description": row.get("职位简介") or None,
        "institution_level": row.get("机构层级") or None,
        "exam_category": row.get("考试类别") or None,
        "headcount": int(row["_headcount"]),
        "education": row.get("学历") or None,
        "degree": row.get("学位") or None,
        "majors_raw": row.get("专业") or None,
        "political_status": row.get("政治面貌") or None,
        "work_experience": row.get("基层工作最低年限") or None,
        "service_project_experience": row.get("服务基层项目工作经历") or None,
        "professional_test_required": row.get("是否在面试阶段组织专业能力测试") or None,
        "interview_ratio": row.get("面试人员比例") or None,
        "settlement_location": row.get("落户地点") or None,
        "department_website": row.get("部门网站") or None,
        "contact_phone": phones or None,
        "other_requirements": row.get("备注") or None,
    }


def _different(position: Position, values: dict[str, object]) -> bool:
    return any(getattr(position, key) != value for key, value in values.items())


def _store_source_file(
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
        content_type="application/vnd.ms-excel",
        content_hash=digest,
        storage_path=str(target.relative_to(settings.raw_data_path.parent)),
        parser_version=PARSER_VERSION,
        parse_status="PARSED",
    )
    session.add(raw)
    return raw


def import_national_exam_positions(
    session: Session,
    settings: Settings,
    path: Path,
    *,
    batch_source_id: str = DEFAULT_BATCH_ID,
    dry_run: bool = False,
) -> dict[str, object]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    parsed = parse_workbook(path)
    source = session.scalar(select(SourceRegistry).where(SourceRegistry.key == SOURCE_KEY))
    if source is None:
        raise ValueError("请先运行 init-db，来源 national_civil_service 尚未初始化")
    batch = session.scalar(
        select(RecruitmentBatch)
        .where(
            RecruitmentBatch.source_id == source.id,
            RecruitmentBatch.source_batch_id == batch_source_id,
        )
        .options(selectinload(RecruitmentBatch.positions).selectinload(Position.locations))
    )
    if batch is None:
        raise ValueError(f"招聘批次不存在: {batch_source_id}，请先采集国家公务员局公告")

    provinces, cities = _division_indexes(session)
    existing = {item.source_position_id: item for item in batch.positions}
    inserted = updated = unchanged = 0
    unmatched_locations: set[str] = set()
    if not dry_run:
        _store_source_file(session, settings, source, path, digest)

    for row in parsed.rows:
        source_position_id = row["_source_position_id"]
        values = _position_values(row)
        location = parse_location(row["工作地点"], provinces, cities)
        if location.precision == LocationPrecision.UNKNOWN:
            unmatched_locations.add(location.raw_text)
        position = existing.get(source_position_id)
        if position is None:
            inserted += 1
            if dry_run:
                continue
            position = Position(batch_id=batch.id, **values)
            position.locations.append(
                PositionLocation(
                    division_id=location.division_id,
                    province_code=location.province_code,
                    city_code=location.city_code,
                    province_name=location.province_name,
                    city_name=location.city_name,
                    location_type=LocationType.WORK_LOCATION,
                    precision=location.precision,
                    raw_text=location.raw_text,
                    confidence=location.confidence,
                )
            )
            session.add(position)
            continue

        location_values = {
            "division_id": location.division_id,
            "province_code": location.province_code,
            "city_code": location.city_code,
            "province_name": location.province_name,
            "city_name": location.city_name,
            "precision": location.precision,
            "raw_text": location.raw_text,
            "confidence": location.confidence,
        }
        work_location = next(
            (item for item in position.locations if item.location_type == LocationType.WORK_LOCATION),
            None,
        )
        location_changed = work_location is None or any(
            getattr(work_location, key) != value for key, value in location_values.items()
        )
        if _different(position, values) or location_changed:
            updated += 1
            if not dry_run:
                for key, value in values.items():
                    setattr(position, key, value)
                if work_location is None:
                    work_location = PositionLocation(
                        position=position, location_type=LocationType.WORK_LOCATION, **location_values
                    )
                    session.add(work_location)
                else:
                    for key, value in location_values.items():
                        setattr(work_location, key, value)
        else:
            unchanged += 1

    result = {
        "source": SOURCE_KEY,
        "batch_source_id": batch_source_id,
        "dry_run": dry_run,
        "sha256": digest,
        "sheets": parsed.sheet_counts,
        "positions": len(parsed.rows),
        "headcount": parsed.headcount,
        "inserted": inserted,
        "updated": updated,
        "unchanged": unchanged,
        "unmatched_location_count": len(unmatched_locations),
        "unmatched_location_samples": sorted(unmatched_locations)[:20],
    }
    if not dry_run:
        session.commit()
    return result
