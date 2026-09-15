import asyncio
import html
import json
import re
from datetime import UTC, datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from selectolax.parser import HTMLParser

from app.crawlers.base import (
    DiscoveredItem,
    ParsedEvent,
    ParsedRecruitment,
    RawPayload,
)
from app.domain.enums import RecruitmentStatus, RecruitmentType


CHINA_TZ = ZoneInfo("Asia/Shanghai")
CONSTANTS_URL = (
    "http://dl.scs.gov.cn/pp/gkweb/core/web/ui/js/core/core-constant.js"
)
HOME_API_TEMPLATE = "http://dl.scs.gov.cn/api/gkhome/article/{exam_id}"
ARTICLE_API_TEMPLATE = "http://dl.scs.gov.cn/api/article/{article_id}"
DETAIL_PAGE = (
    "http://bm.scs.gov.cn/pp/gkweb/core/web/ui/business/article/articledetail.html"
)
ALLOWED_GROUPS = {"招考公告", "公告公示"}


def _millis_to_datetime(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _plain_text(content: str) -> str:
    tree = HTMLParser(html.unescape(content or ""))
    return re.sub(r"\s+", "", tree.text(separator=" ", strip=True))


def _event_type(title: str) -> str:
    rules = (
        ("拟录用", "PUBLIC_NOTICE"),
        ("公示", "PUBLIC_NOTICE"),
        ("补充录用", "SUPPLEMENT"),
        ("调剂", "ADJUSTMENT"),
        ("准考证", "ADMISSION_TICKET"),
        ("笔试成绩", "WRITTEN_RESULT"),
        ("笔试", "WRITTEN_EXAM"),
        ("面试", "INTERVIEW"),
        ("体检", "MEDICAL"),
        ("报名", "REGISTRATION"),
    )
    return next((value for keyword, value in rules if keyword in title), "ANNOUNCEMENT")


def _status_for_event(event_type: str) -> RecruitmentStatus:
    return {
        "PUBLIC_NOTICE": RecruitmentStatus.RESULT,
        "INTERVIEW": RecruitmentStatus.INTERVIEW,
        "WRITTEN_RESULT": RecruitmentStatus.EXAM,
        "WRITTEN_EXAM": RecruitmentStatus.EXAM,
        "ADMISSION_TICKET": RecruitmentStatus.EXAM,
        "MEDICAL": RecruitmentStatus.RESULT,
    }.get(event_type, RecruitmentStatus.CLOSED)


def _application_window(text: str) -> tuple[datetime | None, datetime | None]:
    match = re.search(
        r"报考者可于(?P<year>\d{4})年(?P<sm>\d{1,2})月(?P<sd>\d{1,2})日"
        r"(?P<sh>\d{1,2}):(?P<smin>\d{2})至"
        r"(?:(?P<eyear>\d{4})年)?(?P<em>\d{1,2})月(?P<ed>\d{1,2})日"
        r"(?P<eh>\d{1,2}):(?P<emin>\d{2})",
        text,
    )
    if not match:
        return None, None
    values = {key: int(value) if value else None for key, value in match.groupdict().items()}
    end_year = values["eyear"] or values["year"]
    start = datetime(
        values["year"], values["sm"], values["sd"], values["sh"], values["smin"], tzinfo=CHINA_TZ
    )
    end = datetime(
        end_year, values["em"], values["ed"], values["eh"], values["emin"], tzinfo=CHINA_TZ
    )
    return start, end


def _written_exam_start(text: str) -> datetime | None:
    match = re.search(
        r"公共科目笔试时间为[：:]?(?P<year>\d{4})年(?P<month>\d{1,2})月"
        r"(?P<day>\d{1,2})日(?:上午|下午)?(?P<hour>\d{1,2}):(?P<minute>\d{2})",
        text,
    )
    if not match:
        return None
    values = {key: int(value) for key, value in match.groupdict().items()}
    return datetime(**values, tzinfo=CHINA_TZ)


class NationalCivilServiceAdapter:
    key = "national_civil_service"
    parser_version = "national-exam-json-v1"

    def __init__(self, client: httpx.AsyncClient):
        self.client = client
        self.exam_id: str | None = None
        self.exam_year: int | None = None

    async def _get(self, url: str) -> httpx.Response:
        retry_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await self.client.get(url)
                if response.status_code not in retry_statuses:
                    response.raise_for_status()
                    return response
                last_error = httpx.HTTPStatusError(
                    f"可重试的上游状态码: {response.status_code}",
                    request=response.request,
                    response=response,
                )
            except httpx.TransportError as exc:
                last_error = exc
            if attempt < 2:
                await asyncio.sleep((2, 5)[attempt])
        assert last_error is not None
        raise last_error

    async def _load_exam_metadata(self) -> None:
        response = await self._get(CONSTANTS_URL)
        exam_id = re.search(r'neu\.hb01Id=.*?:"([a-f0-9]+)"', response.text)
        year = re.search(r'neu\.aae001="(\d{4})"', response.text)
        if not exam_id or not year:
            raise ValueError("国家公务员专题常量结构发生变化")
        self.exam_id = exam_id.group(1)
        self.exam_year = int(year.group(1))

    async def discover(self, cursor: str | None = None) -> list[DiscoveredItem]:
        await self._load_exam_metadata()
        response = await self._get(HOME_API_TEMPLATE.format(exam_id=self.exam_id))
        payload = response.json()
        items: dict[str, DiscoveredItem] = {}
        cursor_value = int(cursor) if cursor else None
        for group in payload.get("articleGroupList", []):
            if group.get("title") not in ALLOWED_GROUPS:
                continue
            for article in group.get("articleList", []):
                published_millis = article.get("pstrtime")
                if cursor_value is not None and published_millis <= cursor_value:
                    continue
                article_id = article["id"]
                params = urlencode(
                    {
                        "ArticleId": article_id,
                        "id": article.get("parentColumnId") or "",
                        "eid": article.get("cmsArticleColumnId") or "",
                    }
                )
                items[article_id] = DiscoveredItem(
                    source_item_id=article_id,
                    url=f"{DETAIL_PAGE}?{params}",
                    title_hint=article.get("articleTitle"),
                    published_at_hint=_millis_to_datetime(published_millis),
                    cursor=str(published_millis) if published_millis else None,
                )
        def priority(item: DiscoveredItem) -> tuple[int, float]:
            title = item.title_hint or ""
            is_primary = bool(
                re.search(r"\d{4}年度考试录用公务员公告$", title)
                and "补充" not in title
            )
            published = item.published_at_hint or datetime.min.replace(tzinfo=UTC)
            return (0 if is_primary else 1, -float(published.toordinal()))

        return sorted(items.values(), key=priority)

    async def fetch(self, item: DiscoveredItem) -> RawPayload:
        response = await self._get(
            ARTICLE_API_TEMPLATE.format(article_id=item.source_item_id)
        )
        return RawPayload(
            source_item_id=item.source_item_id,
            source_url=item.url,
            canonical_url=item.url,
            fetched_at=datetime.now(UTC),
            http_status=response.status_code,
            content_type=response.headers.get("content-type"),
            body=response.content,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )

    async def parse(self, payload: RawPayload) -> ParsedRecruitment:
        data = json.loads(payload.body)
        article = data["article"]
        title = article["articleTitle"].strip()
        published_at = _millis_to_datetime(article.get("ctime"))
        year_match = re.search(r"(20\d{2})年度", title)
        year = int(year_match.group(1)) if year_match else self.exam_year
        if year is None:
            raise ValueError("无法确定国考年度")
        text = _plain_text(article.get("content") or "")
        application_start, application_end = _application_window(text)
        event_type = _event_type(title)
        events = [
            ParsedEvent(
                source_event_id=payload.source_item_id,
                event_type=event_type,
                title=title,
                start_at=published_at,
                source_url=payload.source_url,
            )
        ]
        if application_start and application_end:
            events.append(
                ParsedEvent(
                    source_event_id=f"{payload.source_item_id}:application",
                    event_type="APPLICATION_WINDOW",
                    title=f"{year}年度国考报名",
                    start_at=application_start,
                    end_at=application_end,
                    source_url=payload.source_url,
                )
            )
        written_exam = _written_exam_start(text)
        if written_exam:
            events.append(
                ParsedEvent(
                    source_event_id=f"{payload.source_item_id}:written-exam",
                    event_type="WRITTEN_EXAM",
                    title=f"{year}年度国考公共科目笔试",
                    start_at=written_exam,
                    source_url=payload.source_url,
                )
            )
        status = _status_for_event(event_type)
        if application_end and datetime.now(CHINA_TZ) <= application_end:
            status = RecruitmentStatus.OPEN
        return ParsedRecruitment(
            source_item_id=payload.source_item_id,
            source_batch_id=f"national-civil-service-{year}",
            title=f"中央机关及其直属机构{year}年度考试录用公务员",
            organization_name="国家公务员局",
            organization_type="GOVERNMENT",
            organization_official_url="http://www.scs.gov.cn/",
            recruitment_type=RecruitmentType.CIVIL_SERVICE_NATIONAL,
            audience_type="PUBLIC",
            year=year,
            publish_at=published_at,
            application_start_at=application_start,
            application_end_at=application_end,
            status=status,
            source_url=f"http://bm.scs.gov.cn/kl{year}",
            events=events,
        )
