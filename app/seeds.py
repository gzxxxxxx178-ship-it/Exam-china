import csv
from datetime import date
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AdministrativeDivision, SourceRegistry
from app.domain.enums import SourceHealth


def load_divisions(session: Session, path: Path) -> int:
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    by_code: dict[str, AdministrativeDivision] = {}
    created = 0
    for row in sorted(rows, key=lambda item: int(item["level_order"])):
        existing = session.scalar(
            select(AdministrativeDivision).where(
                AdministrativeDivision.code == row["code"],
                AdministrativeDivision.valid_from == date.fromisoformat(row["valid_from"]),
            )
        )
        if existing:
            by_code[row["code"]] = existing
            continue
        parent = by_code.get(row["parent_code"])
        division = AdministrativeDivision(
            code=row["code"],
            name=row["name"],
            level=row["level"],
            parent=parent,
            valid_from=date.fromisoformat(row["valid_from"]),
            aliases=[alias for alias in row["aliases"].split("|") if alias],
        )
        session.add(division)
        session.flush()
        by_code[row["code"]] = division
        created += 1
    return created


def load_sources(session: Session, path: Path) -> int:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    created = 0
    for item in payload.get("sources", []):
        source_item = dict(item)
        seed_health_status = source_item.pop("seed_health_status", None)
        seed_health = SourceHealth(seed_health_status) if seed_health_status else None
        existing = session.scalar(
            select(SourceRegistry).where(SourceRegistry.key == source_item["key"])
        )
        if existing:
            for field in (
                "name",
                "category",
                "base_url",
                "authority_level",
                "province_code",
                "city_code",
                "adapter_key",
                "crawl_policy",
                "interval_minutes",
                "enabled",
            ):
                setattr(existing, field, source_item[field])
            if seed_health == SourceHealth.PAUSED:
                existing.health_status = SourceHealth.PAUSED
            continue
        session.add(
            SourceRegistry(
                **source_item,
                health_status=seed_health or SourceHealth.UNKNOWN,
            )
        )
        created += 1
    return created
