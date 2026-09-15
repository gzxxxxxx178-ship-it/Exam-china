from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    AdministrativeDivision,
    Organization,
    Position,
    PositionLocation,
    RecruitmentBatch,
    SourceRegistry,
)
from app.domain.enums import (
    LocationPrecision,
    LocationType,
    RecruitmentStatus,
    RecruitmentType,
    SourceHealth,
)


def seed_positions(session: Session) -> None:
    source = SourceRegistry(
        key="test",
        name="测试官方来源",
        category="PUBLIC_INSTITUTION",
        base_url="https://example.gov.cn",
        authority_level="CITY",
        adapter_key="test",
        enabled=True,
        health_status=SourceHealth.HEALTHY,
    )
    organization = Organization(
        canonical_name="测试事业单位", organization_type="PUBLIC_INSTITUTION"
    )
    now = datetime.now(UTC)
    batch = RecruitmentBatch(
        source_batch_id="test-2027",
        organization=organization,
        source_id=1,
        title="2027 年公开招聘",
        recruitment_type=RecruitmentType.PUBLIC_INSTITUTION,
        year=2027,
        status=RecruitmentStatus.OPEN,
        source_url="https://example.gov.cn/job/1",
        first_seen_at=now,
        last_seen_at=now,
        content_hash="a" * 64,
    )
    taian = Position(title="信息化岗位", majors_raw="计算机科学与技术")
    taian.locations.append(
        PositionLocation(
            province_code="370000",
            city_code="370900",
            province_name="山东省",
            city_name="泰安市",
            location_type=LocationType.WORK_LOCATION,
            precision=LocationPrecision.CITY,
            raw_text="山东省泰安市",
            confidence=1.0,
        )
    )
    province = Position(title="全省统筹岗位", majors_raw="软件工程")
    province.locations.append(
        PositionLocation(
            province_code="370000",
            province_name="山东省",
            location_type=LocationType.WORK_LOCATION,
            precision=LocationPrecision.PROVINCE,
            raw_text="山东省内",
            confidence=0.9,
        )
    )
    nationwide = Position(title="全国待分配岗位", majors_raw="不限")
    nationwide.locations.append(
        PositionLocation(
            location_type=LocationType.WORK_LOCATION,
            precision=LocationPrecision.NATIONWIDE,
            raw_text="全国",
            confidence=1.0,
        )
    )
    batch.positions.extend([taian, province, nationwide])
    session.add_all([source, batch])
    session.commit()


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_home_page(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "岗位雷达" in response.text


def test_city_filter_is_strict_by_default(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        seed_positions(session)
    response = client.get(
        "/api/positions", params={"province_code": "370000", "city_code": "370900"}
    )
    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == ["信息化岗位"]


def test_city_filter_can_include_broader_scope(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        seed_positions(session)
    response = client.get(
        "/api/positions",
        params={
            "province_code": "370000",
            "city_code": "370900",
            "include_broader_scope": "true",
        },
    )
    assert response.status_code == 200
    assert {item["title"] for item in response.json()["items"]} == {
        "信息化岗位",
        "全省统筹岗位",
        "全国待分配岗位",
    }


def test_keyword_filter_searches_major(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        seed_positions(session)
    response = client.get("/api/positions", params={"keyword": "计算机"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == "信息化岗位"


def test_division_children(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        province = AdministrativeDivision(
            code="370000", name="山东省", level="PROVINCE", valid_from=date(2026, 9, 15)
        )
        province.children.append(
            AdministrativeDivision(
                code="370900", name="泰安市", level="CITY", valid_from=date(2026, 9, 15)
            )
        )
        session.add(province)
        session.commit()
    response = client.get("/api/divisions", params={"parent_code": "370000"})
    assert response.status_code == 200
    assert response.json()[0]["code"] == "370900"


def test_location_options_come_from_imported_positions(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        seed_positions(session)
    response = client.get("/api/location-options")
    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "山东省",
            "code": "370000",
            "position_count": 2,
            "cities": [
                {"name": "泰安市", "code": "370900", "position_count": 1}
            ],
        }
    ]


def test_location_options_merge_same_named_city_with_different_codes(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        seed_positions(session)
        batch = session.query(RecruitmentBatch).one()
        duplicate_city = Position(title="同名地市岗位")
        duplicate_city.locations.append(
            PositionLocation(
                province_code="370000",
                city_code="370999",
                province_name="山东省",
                city_name="泰安市",
                location_type=LocationType.WORK_LOCATION,
                precision=LocationPrecision.CITY,
                raw_text="山东省泰安市",
                confidence=0.9,
            )
        )
        batch.positions.append(duplicate_city)
        session.commit()

    response = client.get("/api/location-options")
    assert response.status_code == 200
    assert response.json()[0]["cities"] == [
        {"name": "泰安市", "code": "370900", "position_count": 2}
    ]


def test_location_options_can_filter_by_recruitment_category(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    with session_factory() as session:
        seed_positions(session)
        original_batch = session.query(RecruitmentBatch).one()
        grid_batch = RecruitmentBatch(
            source_batch_id="state-grid-2027",
            organization=original_batch.organization,
            source_id=original_batch.source_id,
            title="国家电网招聘",
            recruitment_type=RecruitmentType.SOE_STATE_GRID,
            year=2027,
            status=RecruitmentStatus.OPEN,
            source_url="https://example.gov.cn/grid/1",
            first_seen_at=original_batch.first_seen_at,
            last_seen_at=original_batch.last_seen_at,
            content_hash="b" * 64,
        )
        position = Position(title="电网岗位")
        position.locations.append(
            PositionLocation(
                province_code="370000",
                city_code="371600",
                province_name="山东省",
                city_name="滨州市",
                location_type=LocationType.WORK_LOCATION,
                precision=LocationPrecision.CITY,
                raw_text="山东省滨州市",
                confidence=1.0,
            )
        )
        grid_batch.positions.append(position)
        session.add(grid_batch)
        session.commit()

    response = client.get(
        "/api/location-options", params={"categories": "SOE_STATE_GRID"}
    )
    assert response.status_code == 200
    assert response.json()[0]["cities"] == [
        {"name": "滨州市", "code": "371600", "position_count": 1}
    ]
