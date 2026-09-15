import asyncio
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.crawlers.base import ParsedRecruitment, RawPayload
from app.crawlers.registry import create_adapter
from app.db.models import (
    CrawlRun,
    ExamEvent,
    Organization,
    RawDocument,
    RecruitmentBatch,
    Revision,
    SourceRegistry,
)
from app.domain.enums import CrawlStatus, RecruitmentStatus, SourceHealth


STATUS_RANK = {
    RecruitmentStatus.UPCOMING: 0,
    RecruitmentStatus.OPEN: 1,
    RecruitmentStatus.CLOSED: 2,
    RecruitmentStatus.EXAM: 3,
    RecruitmentStatus.INTERVIEW: 4,
    RecruitmentStatus.RESULT: 5,
    RecruitmentStatus.FINISHED: 6,
    RecruitmentStatus.CANCELLED: 7,
}


def _save_raw(settings: Settings, source_key: str, payload: RawPayload) -> tuple[Path, str]:
    digest = hashlib.sha256(payload.body).hexdigest()
    directory = settings.raw_data_path / source_key / str(payload.fetched_at.year)
    directory.mkdir(parents=True, exist_ok=True)
    safe_item_id = re.sub(r"[^A-Za-z0-9._-]", "_", payload.source_item_id)[:120]
    if not safe_item_id:
        safe_item_id = digest[:16]
    target = directory / f"{safe_item_id}-{digest[:12]}.json"
    if not target.exists():
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(payload.body)
        temporary.replace(target)
    return target, digest


def _upsert_recruitment(
    session: Session,
    source: SourceRegistry,
    parsed: ParsedRecruitment,
    raw_document: RawDocument,
    content_hash: str,
) -> tuple[bool, bool]:
    organization = session.scalar(
        select(Organization).where(
            Organization.canonical_name == parsed.organization_name
        )
    )
    if organization is None:
        organization = Organization(
            canonical_name=parsed.organization_name,
            organization_type=parsed.organization_type,
            official_url=(
                str(parsed.organization_official_url)
                if parsed.organization_official_url
                else None
            ),
        )
        session.add(organization)
        session.flush()

    batch = session.scalar(
        select(RecruitmentBatch).where(
            RecruitmentBatch.source_id == source.id,
            RecruitmentBatch.source_batch_id == parsed.source_batch_id,
        )
    )
    now = datetime.now(UTC)
    created = batch is None
    changed = False
    if batch is None:
        batch = RecruitmentBatch(
            source_batch_id=parsed.source_batch_id,
            organization_id=organization.id,
            source_id=source.id,
            title=parsed.title,
            recruitment_type=parsed.recruitment_type,
            audience_type=parsed.audience_type,
            year=parsed.year,
            batch_no=parsed.batch_no,
            publish_at=parsed.publish_at,
            application_start_at=parsed.application_start_at,
            application_end_at=parsed.application_end_at,
            status=parsed.status,
            source_url=str(parsed.source_url),
            first_seen_at=now,
            last_seen_at=now,
            content_hash=content_hash,
        )
        session.add(batch)
        session.flush()
    else:
        batch.last_seen_at = now
        if parsed.publish_at is not None and (
            batch.publish_at is None or parsed.publish_at < batch.publish_at
        ):
            batch.publish_at = parsed.publish_at
            changed = True
        if STATUS_RANK[parsed.status] > STATUS_RANK[batch.status]:
            batch.status = parsed.status
            changed = True
        for field in ("application_start_at", "application_end_at"):
            value = getattr(parsed, field)
            if value is not None and getattr(batch, field) != value:
                setattr(batch, field, value)
                changed = True

    for parsed_event in parsed.events:
        event = session.scalar(
            select(ExamEvent).where(
                ExamEvent.batch_id == batch.id,
                ExamEvent.source_event_id == parsed_event.source_event_id,
            )
        )
        values = {
            "event_type": parsed_event.event_type,
            "title": parsed_event.title,
            "start_at": parsed_event.start_at,
            "end_at": parsed_event.end_at,
            "province_code": parsed_event.province_code,
            "city_code": parsed_event.city_code,
            "source_url": str(parsed_event.source_url),
        }
        if event is None:
            session.add(
                ExamEvent(
                    batch_id=batch.id,
                    source_event_id=parsed_event.source_event_id,
                    **values,
                )
            )
            changed = changed or not created
        else:
            for field, value in values.items():
                if getattr(event, field) != value:
                    setattr(event, field, value)
                    changed = True

    previous = session.scalar(
        select(RawDocument)
        .where(
            RawDocument.source_id == source.id,
            RawDocument.canonical_url == raw_document.canonical_url,
            RawDocument.id != raw_document.id,
        )
        .order_by(RawDocument.fetched_at.desc())
    )
    if previous is not None and previous.content_hash != content_hash:
        revision_no = (
            session.scalar(
                select(func.max(Revision.revision_no)).where(Revision.batch_id == batch.id)
            )
            or 0
        ) + 1
        session.add(
            Revision(
                batch_id=batch.id,
                raw_document_id=raw_document.id,
                revision_no=revision_no,
                content_hash=content_hash,
                changed_fields={"source_url": raw_document.canonical_url},
                detected_at=now,
            )
        )
        changed = True
    return created, changed


async def run_source(
    session: Session,
    settings: Settings,
    source_key: str,
    *,
    max_items: int = 20,
    dry_run: bool = False,
) -> dict[str, int | str | bool]:
    source = session.scalar(select(SourceRegistry).where(SourceRegistry.key == source_key))
    if source is None:
        raise ValueError(f"来源不存在: {source_key}")
    if not source.enabled:
        raise ValueError(f"来源未启用: {source_key}")

    run = CrawlRun(
        source_id=source.id,
        started_at=datetime.now(UTC),
        status=CrawlStatus.RUNNING,
    )
    if not dry_run:
        session.add(run)
        session.commit()

    fetched = parsed_count = new_count = changed_count = 0
    try:
        limits = httpx.Limits(max_connections=2, max_keepalive_connections=1)
        async with httpx.AsyncClient(
            headers={"User-Agent": settings.crawler_user_agent},
            timeout=httpx.Timeout(30),
            follow_redirects=True,
            limits=limits,
        ) as client:
            adapter = create_adapter(source.adapter_key, client)
            items = (await adapter.discover())[:max_items]
            min_interval = float(source.crawl_policy.get("min_interval_seconds", 0))
            for index, item in enumerate(items):
                payload = await adapter.fetch(item)
                fetched += 1
                if len(payload.body) > settings.max_raw_document_bytes:
                    raise ValueError(
                        f"原始响应超过限制: {len(payload.body)} bytes > "
                        f"{settings.max_raw_document_bytes} bytes"
                    )
                parsed = await adapter.parse(payload)
                parsed_count += 1
                if dry_run:
                    if index < len(items) - 1 and min_interval > 0:
                        await asyncio.sleep(min_interval)
                    continue
                path, digest = _save_raw(settings, source.key, payload)
                existing_raw = session.scalar(
                    select(RawDocument).where(
                        RawDocument.source_id == source.id,
                        RawDocument.canonical_url == str(payload.canonical_url),
                        RawDocument.content_hash == digest,
                    )
                )
                if existing_raw is not None:
                    if index < len(items) - 1 and min_interval > 0:
                        await asyncio.sleep(min_interval)
                    continue
                raw = RawDocument(
                    source_id=source.id,
                    source_url=str(payload.source_url),
                    canonical_url=str(payload.canonical_url),
                    fetched_at=payload.fetched_at,
                    http_status=payload.http_status,
                    content_type=payload.content_type,
                    content_hash=digest,
                    storage_path=str(path.relative_to(settings.raw_data_path.parent)),
                    parser_version=getattr(adapter, "parser_version", None),
                    parse_status="PARSED",
                )
                session.add(raw)
                session.flush()
                created, changed = _upsert_recruitment(
                    session, source, parsed, raw, digest
                )
                new_count += int(created)
                changed_count += int(changed)
                session.commit()
                if index < len(items) - 1 and min_interval > 0:
                    await asyncio.sleep(min_interval)
        if not dry_run:
            run.status = CrawlStatus.SUCCEEDED
            run.finished_at = datetime.now(UTC)
            run.fetched_count = fetched
            run.parsed_count = parsed_count
            run.new_count = new_count
            run.changed_count = changed_count
            source.last_success_at = run.finished_at
            source.health_status = SourceHealth.HEALTHY
            session.commit()
        return {
            "source": source_key,
            "dry_run": dry_run,
            "fetched": fetched,
            "parsed": parsed_count,
            "new": new_count,
            "changed": changed_count,
        }
    except Exception as exc:
        if not dry_run:
            session.rollback()
            persisted_run = session.get(CrawlRun, run.id)
            persisted_source = session.get(SourceRegistry, source.id)
            if persisted_run:
                persisted_run.status = CrawlStatus.FAILED
                persisted_run.finished_at = datetime.now(UTC)
                persisted_run.error_type = type(exc).__name__
                persisted_run.error_message = str(exc)[:2000]
            if persisted_source:
                persisted_source.health_status = SourceHealth.DEGRADED
            session.commit()
        raise
