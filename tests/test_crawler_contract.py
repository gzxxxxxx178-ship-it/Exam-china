from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.crawlers.base import ParsedLocation, ParsedPosition, ParsedRecruitment
from app.domain.enums import (
    LocationPrecision,
    RecruitmentStatus,
    RecruitmentType,
)


def test_parsed_recruitment_contract_accepts_valid_position() -> None:
    parsed = ParsedRecruitment(
        source_item_id="notice-1",
        title="2027 年公开招聘",
        organization_name="某事业单位",
        organization_type="PUBLIC_INSTITUTION",
        recruitment_type=RecruitmentType.PUBLIC_INSTITUTION,
        publish_at=datetime.now(UTC),
        status=RecruitmentStatus.OPEN,
        source_url="https://example.gov.cn/notices/1",
        positions=[
            ParsedPosition(
                title="专业技术岗位",
                headcount=1,
                work_locations=[
                    ParsedLocation(
                        raw_text="山东省泰安市",
                        province_code="370000",
                        city_code="370900",
                        division_code="370900",
                        precision=LocationPrecision.CITY,
                        confidence=1.0,
                    )
                ],
            )
        ],
    )
    assert parsed.positions[0].work_locations[0].city_code == "370900"


def test_parsed_location_rejects_nonstandard_division_code() -> None:
    with pytest.raises(ValidationError):
        ParsedLocation(
            raw_text="泰安",
            city_code="3709",
            precision=LocationPrecision.CITY,
            confidence=0.8,
        )

