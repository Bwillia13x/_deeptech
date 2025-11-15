"""Simple Hacker News client for Phase Five source expansion."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Sequence

import httpx

from .config import Settings
from .logger import get_logger

log = get_logger(__name__)

DEFAULT_HN_URL = "https://hacker-news.firebaseio.com/v0"


class HackerNewsClient:
    """Client for the Hacker News Firebase API."""

    def __init__(self, base_url: str = DEFAULT_HN_URL, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def __aenter__(self) -> "HackerNewsClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._client.aclose()

    async def _get_json(self, path: str) -> Dict[str, Any] | None:
        url = f"{self.base_url}/{path}"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            log.error("Hacker News request failed (%s): %s", path, exc)
            return None

    async def fetch_story_ids(self, list_type: str) -> List[int]:
        payload = await self._get_json(f"{list_type}.json")
        if isinstance(payload, list):
            return [int(item) for item in payload if isinstance(item, int)]
        return []

    async def get_item(self, item_id: int) -> Dict[str, Any] | None:
        return await self._get_json(f"item/{item_id}.json")

    async def fetch_items(
        self,
        ids: Sequence[int],
        allowed_types: Iterable[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        allowed = set(allowed_types)
        items: List[Dict[str, Any]] = []
        for item_id in ids:
            if len(items) >= limit:
                break
            item = await self.get_item(item_id)
            if not item:
                continue
            if item.get("type") not in allowed:
                continue
            items.append(item)
        return items


def _normalize_hn_item(item: Dict[str, Any]) -> Dict[str, Any]:
    timestamp = item.get("time")
    try:
        published_at = datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        published_at = datetime.now(timezone.utc).isoformat()

    text = item.get("text") or ""
    title = item.get("title") or text or f"Hacker News {item.get('id')}"
    url = item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id')}"

    metadata = {
        "score": item.get("score"),
        "descendants": item.get("descendants"),
        "item_type": item.get("type"),
        "by": item.get("by"),
        "parent": item.get("parent"),
        "url": url,
    }

    return {
        "type": item.get("type", "story"),
        "source": "hackernews",
        "source_id": str(item.get("id")),
        "title": title,
        "text": text,
        "url": url,
        "published_at": published_at,
        "metadata": metadata,
        "raw_json": json.dumps(item, default=str, ensure_ascii=False),
    }


async def fetch_hackernews_artifacts(settings: Settings) -> List[Dict[str, Any]]:
    """Fetch Hacker News items based on configured lists."""
    config = settings.app.sources.hacker_news
    if not config.enabled:
        log.debug("Hacker News source disabled")
        return []

    allowed_types: List[str] = list(config.allowed_item_types)
    if config.include_comments and "comment" not in allowed_types:
        allowed_types.append("comment")

    artifacts: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    remaining = max(1, config.max_items)

    async with HackerNewsClient(base_url=config.api_base_url) as client:
        for list_type in config.list_types:
            if remaining <= 0:
                break
            ids = await client.fetch_story_ids(list_type)
            if not ids:
                continue
            fetched = await client.fetch_items(ids, allowed_types, limit=remaining)
            log.info("Hacker News list '%s' returned %d items", list_type, len(fetched))
            for item in fetched:
                item_id = item.get("id")
                if not item_id:
                    continue
                str_id = str(item_id)
                if str_id in seen_ids:
                    continue
                seen_ids.add(str_id)
                artifacts.append(_normalize_hn_item(item))
                remaining -= 1
                if remaining <= 0:
                    break

    log.info("Total Hacker News artifacts collected: %d", len(artifacts))
    return artifacts
