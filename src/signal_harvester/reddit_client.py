"""Reddit client for Phase Five community source expansion."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from .config import Settings
from .logger import get_logger

log = get_logger(__name__)

DEFAULT_REDDIT_URL = "https://www.reddit.com"
MAX_REDDIT_LIMIT = 100


class RedditClient:
    """Simple Reddit client that uses the public listing endpoints."""

    def __init__(self, user_agent: str, base_url: str = DEFAULT_REDDIT_URL, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        headers = {"User-Agent": user_agent}
        self._client = httpx.AsyncClient(base_url=self.base_url, headers=headers, timeout=timeout)

    async def __aenter__(self) -> "RedditClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self._client.aclose()

    async def _fetch_listing(self, path: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        try:
            response = await self._client.get(path, params=params)
            if response.status_code == 429:
                log.warning("Reddit rate limited when calling %s", path)
                return []
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            log.error("Reddit HTTP error (%s): %s", path, exc)
            return []
        except Exception as exc:
            log.error("Reddit fetch error (%s): %s", path, exc)
            return []

        if not isinstance(payload, dict):
            return []

        children = payload.get("data", {}).get("children", [])
        results: List[Dict[str, Any]] = []
        for child in children:
            data = child.get("data") if isinstance(child, dict) else None
            if isinstance(data, dict):
                results.append(data)
        return results

    async def fetch_subreddit_new(self, subreddit: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Fetch new posts from a subreddit."""
        sanitized = subreddit.strip().lstrip("/")
        if not sanitized:
            return []
        params = {"limit": min(limit, MAX_REDDIT_LIMIT)}
        path = f"/r/{sanitized}/new.json"
        return await self._fetch_listing(path, params)

    async def search_posts(self, query: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Search for posts matching the query."""
        if not query:
            return []
        params = {
            "q": query,
            "sort": "new",
            "limit": min(limit, MAX_REDDIT_LIMIT),
            "include_over_18": "1",
        }
        return await self._fetch_listing("/search.json", params)


def _normalize_post(post: Dict[str, Any], method: str, context: str | None = None) -> Dict[str, Any]:
    created_ts = post.get("created_utc") or 0
    try:
        published_at = datetime.fromtimestamp(float(created_ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        published_at = datetime.now(timezone.utc).isoformat()

    title = post.get("title") or ""
    selftext = post.get("selftext") or ""
    text = selftext or title
    url = post.get("url")
    permalink = post.get("permalink")
    if not url and permalink:
        url = f"{DEFAULT_REDDIT_URL.rstrip('/')}{permalink}"

    metadata = {
        "score": post.get("score"),
        "num_comments": post.get("num_comments"),
        "subreddit": post.get("subreddit"),
        "author": post.get("author"),
        "method": method,
        "context": context,
        "over_18": post.get("over_18"),
        "awards": [award.get("name") for award in post.get("all_awardings", []) if isinstance(award, dict)],
        "permalink": permalink,
    }

    return {
        "type": "reddit_post",
        "source": "reddit",
        "source_id": post.get("id", ""),
        "title": title,
        "text": text,
        "url": url,
        "published_at": published_at,
        "metadata": metadata,
        "raw_json": json.dumps(post, default=str, ensure_ascii=False),
    }


async def fetch_reddit_artifacts(settings: Settings) -> List[Dict[str, Any]]:
    """Collect Reddit posts based on configured subreddits/search terms."""
    config = settings.app.sources.reddit
    if not config.enabled:
        log.debug("Reddit source disabled")
        return []

    subreddits = [s for s in config.subreddits if s]
    search_terms = [term for term in config.search_terms if term]
    if not subreddits and not search_terms:
        log.debug("Reddit has no subreddits or search terms configured")
        return []

    artifacts: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    async with RedditClient(user_agent=config.user_agent) as client:
        for subreddit in subreddits:
            posts = await client.fetch_subreddit_new(subreddit, limit=config.max_results)
            log.info("Reddit subreddit '%s' returned %d posts", subreddit, len(posts))
            for post in posts:
                source_id = post.get("id")
                if not source_id or source_id in seen_ids:
                    continue
                seen_ids.add(source_id)
                artifacts.append(_normalize_post(post, method="subreddit", context=subreddit))

        for term in search_terms:
            posts = await client.search_posts(term, limit=config.max_results)
            log.info("Reddit search '%s' returned %d posts", term, len(posts))
            for post in posts:
                source_id = post.get("id")
                if not source_id or source_id in seen_ids:
                    continue
                seen_ids.add(source_id)
                artifacts.append(_normalize_post(post, method="search", context=term))

    log.info("Total Reddit artifacts collected: %d", len(artifacts))
    return artifacts
