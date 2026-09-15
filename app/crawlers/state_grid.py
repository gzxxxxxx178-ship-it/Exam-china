from __future__ import annotations

from datetime import UTC, datetime

import httpx

from app.crawlers.base import (
    DiscoveredItem,
    ParsedRecruitment,
    RawPayload,
    SourceAccessBlockedError,
)


STATE_GRID_HOME = "https://zhaopin.sgcc.com.cn/"


class StateGridAdapter:
    """国家电网招聘平台的合规访问探针。

    仅验证公开入口是否允许低频 HTTP 访问。平台返回访问校验页时，
    明确暂停来源，绝不尝试规避校验、登录或验证码。
    """

    key = "state_grid"
    parser_version = "state-grid-access-probe-v1"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def discover(self, cursor: str | None = None) -> list[DiscoveredItem]:
        response = await self.client.get(STATE_GRID_HOME)
        if response.status_code in {403, 412, 429}:
            raise SourceAccessBlockedError(
                "国家电网招聘平台返回访问校验页，已暂停自动采集；"
                "系统不会绕过登录、验证码或反自动化措施。"
            )
        response.raise_for_status()
        raise SourceAccessBlockedError(
            "国家电网招聘平台公开页面未提供已核验的稳定公告接口，"
            "已暂停自动采集，等待人工授权的公开数据入口。"
        )

    async def fetch(self, item: DiscoveredItem) -> RawPayload:
        raise RuntimeError("国家电网来源尚未通过公开访问验证，不能抓取详情")

    async def parse(self, payload: RawPayload) -> ParsedRecruitment:
        raise RuntimeError("国家电网来源尚未通过公开访问验证，不能解析招聘数据")
