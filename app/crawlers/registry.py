import httpx

from app.crawlers.base import SourceAdapter
from app.crawlers.national_exam import NationalCivilServiceAdapter


def create_adapter(adapter_key: str, client: httpx.AsyncClient) -> SourceAdapter:
    adapters = {
        "national_exam": NationalCivilServiceAdapter,
    }
    try:
        adapter_class = adapters[adapter_key]
    except KeyError as exc:
        raise ValueError(f"尚未实现采集适配器: {adapter_key}") from exc
    return adapter_class(client)
