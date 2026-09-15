from app.domain.enums import LocationPrecision
from app.importers.national_exam_positions import parse_location


def test_parse_province_city_county_location() -> None:
    location = parse_location("山东省济南市历下区")
    assert location.province_name == "山东省"
    assert location.province_code == "370000"
    assert location.city_name == "济南市"
    assert location.precision == LocationPrecision.COUNTY


def test_parse_municipality_location() -> None:
    location = parse_location("北京市西城区")
    assert location.province_name == "北京市"
    assert location.city_name == "北京市"
    assert location.precision == LocationPrecision.COUNTY


def test_parse_nationwide_location() -> None:
    location = parse_location("全国")
    assert location.province_name is None
    assert location.precision == LocationPrecision.NATIONWIDE


def test_parse_direct_administered_county_location() -> None:
    location = parse_location("海南省陵水黎族自治县")
    assert location.province_name == "海南省"
    assert location.city_name == "陵水黎族自治县"
    assert location.precision == LocationPrecision.COUNTY
