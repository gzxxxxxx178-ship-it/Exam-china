import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch

import httpx

from app.crawlers.national_exam import NationalCivilServiceAdapter
from app.domain.enums import RecruitmentStatus


EXAM_ID = "8a81f6d9980207bb0198ab5683670008"
ARTICLE_ID = "article-2026"


def test_national_exam_discovery_and_parsing() -> None:
    constants = (
        'neu.aae001="2026",neu.hb01Id=neu.examSelect?"":'
        f'"{EXAM_ID}"'
    )
    home = {
        "articleGroupList": [
            {
                "title": "招考公告",
                "articleList": [
                    {
                        "id": ARTICLE_ID,
                        "cmsArticleColumnId": "column-1",
                        "parentColumnId": "parent-1",
                        "articleTitle": "中央机关及其直属机构2026年度考试录用公务员公告",
                        "pstrtime": 1760371200000,
                    }
                ],
            },
            {
                "title": "政策法规",
                "articleList": [
                    {
                        "id": "ignored",
                        "articleTitle": "中华人民共和国公务员法",
                        "pstrtime": 1760371200000,
                    }
                ],
            },
        ]
    }
    detail = {
        "article": {
            "articleTitle": "中央机关及其直属机构2026年度考试录用公务员公告",
            "ctime": 1760371200000,
            "content": (
                "<p>报考者可于2025年10月15日8:00至10月24日18:00期间登录专题网站"
                "进行报名。</p><p>公共科目笔试时间为：2025年11月30日上午 9:00—11:00。"
                "</p>"
            ),
        },
        "resourceList": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("core-constant.js"):
            return httpx.Response(200, text=constants)
        if request.url.path == f"/api/gkhome/article/{EXAM_ID}":
            return httpx.Response(200, json=home)
        if request.url.path == f"/api/article/{ARTICLE_ID}":
            return httpx.Response(200, json=detail)
        return httpx.Response(404)

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = NationalCivilServiceAdapter(client)
            items = await adapter.discover()
            assert len(items) == 1
            raw = await adapter.fetch(items[0])
            return await adapter.parse(raw)

    parsed = asyncio.run(scenario())
    assert parsed.source_batch_id == "national-civil-service-2026"
    assert parsed.application_start_at == datetime.fromisoformat(
        "2025-10-15T08:00:00+08:00"
    )
    assert parsed.application_end_at == datetime.fromisoformat(
        "2025-10-24T18:00:00+08:00"
    )
    assert parsed.status == RecruitmentStatus.CLOSED
    assert {event.event_type for event in parsed.events} == {
        "ANNOUNCEMENT",
        "APPLICATION_WINDOW",
        "WRITTEN_EXAM",
    }


def test_adapter_rejects_changed_constant_structure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="unexpected")

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await NationalCivilServiceAdapter(client).discover()

    try:
        asyncio.run(scenario())
    except ValueError as exc:
        assert "结构发生变化" in str(exc)
    else:
        raise AssertionError("站点结构变化时应显式失败")


def test_adapter_retries_transient_upstream_error() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(502, request=request)
        return httpx.Response(200, text="ok", request=request)

    async def scenario() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = NationalCivilServiceAdapter(client)
            with patch(
                "app.crawlers.national_exam.asyncio.sleep", new=AsyncMock()
            ) as sleep:
                response = await adapter._get("http://dl.scs.gov.cn/test")
                sleep.assert_awaited_once_with(2)
                return response

    assert asyncio.run(scenario()).status_code == 200
    assert attempts == 2
