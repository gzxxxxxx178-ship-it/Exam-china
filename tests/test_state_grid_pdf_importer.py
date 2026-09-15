import pytest

from app.importers.state_grid_pdf import parse_table


def test_parse_table_inherits_merged_city_cells() -> None:
    rows = parse_table(
        [
            ["所在地", "单位名称", "招聘专业类别", "学历要求"],
            ["南昌市", "南昌南供电力设计院有限公司", "电工类", "硕士研究生及以上"],
            [None, "南昌通源实业有限公司", "财务会计类", "硕士研究生及以上"],
        ]
    )
    assert [row.city_name for row in rows] == ["南昌市", "南昌市"]
    assert rows[1].employer_name == "南昌通源实业有限公司"


def test_parse_table_rejects_unknown_headers() -> None:
    with pytest.raises(ValueError, match="预期的招聘需求表头"):
        parse_table([["城市", "单位", "专业", "学历"]])
