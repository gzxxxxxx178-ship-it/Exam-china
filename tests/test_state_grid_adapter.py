import asyncio

import httpx
import pytest

from app.crawlers.base import SourceAccessBlockedError
from app.crawlers.registry import create_adapter
from app.crawlers.state_grid import StateGridAdapter


def test_state_grid_pauses_when_platform_returns_access_challenge() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://zhaopin.sgcc.com.cn/")
        return httpx.Response(412, text="access challenge", request=request)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await StateGridAdapter(client).discover()

    with pytest.raises(SourceAccessBlockedError, match="暂停自动采集"):
        asyncio.run(scenario())


def test_registry_creates_state_grid_adapter() -> None:
    async def scenario() -> str:
        async with httpx.AsyncClient() as client:
            return create_adapter("state_grid", client).key

    assert asyncio.run(scenario()) == "state_grid"
