"""Facebook Graph API client for public pages and groups."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

import httpx

from .config import Settings
from .logger import get_logger

log = get_logger(__name__)


def _truncate_facebook_title(message: str | None) -> str:
    if not message:
        return ""
    return f"{message[:100]}..." if len(message) > 100 else message


class FacebookAPIError(Exception):
    """Raised when Facebook API returns an error."""
    pass


class FacebookRateLimitError(FacebookAPIError):
    """Raised when Facebook API rate limit is hit."""
    pass


class FacebookClient:
    """Client for Facebook Graph API."""
    
    def __init__(self, access_token: str, version: str = "v18.0"):
        self.access_token = access_token
        self.version = version
        self.base_url = f"https://graph.facebook.com/{version}"
        self.http_client = httpx.AsyncClient(timeout=30.0, limits=httpx.Limits(max_connections=10))
        
    async def __aenter__(self) -> "FacebookClient":
        return self
        
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> None:
        await self.http_client.aclose()
    
    async def _make_request(self, endpoint: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Make a request to Facebook Graph API."""
        if params is None:
            params = {}
        
        params["access_token"] = self.access_token
        
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = await self.http_client.get(url, params=params)
            response.raise_for_status()
            return cast(Dict[str, Any], response.json())
            
        except httpx.HTTPStatusError as e:
            error_data = cast(Dict[str, Any], e.response.json())
            error_code = error_data.get("error", {}).get("code", 0)
            error_message = error_data.get("error", {}).get("message", "Unknown error")
            
            if error_code == 4 or error_code == 80003:  # Rate limit errors
                raise FacebookRateLimitError(f"Rate limit hit: {error_message}")
            elif error_code == 190:  # Invalid access token
                raise FacebookAPIError(f"Invalid access token: {error_message}")
            else:
                raise FacebookAPIError(f"Facebook API error {error_code}: {error_message}")
                
        except Exception as e:
            raise FacebookAPIError(f"Request failed: {str(e)}")
    
    async def get_page_posts(
        self,
        page_id: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get posts from a Facebook page."""
        page_fields = (
            "id,message,created_time,updated_time,permalink_url,"
            "likes.summary(true),comments.summary(true),shares,type"
        )
        params = {
            "fields": page_fields,
            "limit": limit,
        }
        
        if since:
            params["since"] = int(since.timestamp())
        if until:
            params["until"] = int(until.timestamp())
        
        try:
            data = await self._make_request(f"{page_id}/posts", params)
            posts = data.get("data", [])
            
            # Transform posts to our format
            transformed_posts = []
            for post in posts:
                try:
                    # Check if post should be included
                    if not self._should_include_post(post):
                        continue
                    
                    created_time = datetime.fromisoformat(post["created_time"])
                    
                    transformed_posts.append({
                        "id": post["id"],
                        "message": post.get("message", ""),
                        "created_time": created_time,
                        "permalink_url": post.get("permalink_url", ""),
                        "likes": post.get("likes", {}).get("summary", {}).get("total_count", 0),
                        "comments": post.get("comments", {}).get("summary", {}).get("total_count", 0),
                        "shares": post.get("shares", {}).get("count", 0),
                        "type": post.get("type", "status"),
                    })
                except Exception as e:
                    log.warning(f"Error transforming post {post.get('id', 'unknown')}: {e}")
                    continue
            
            return transformed_posts
            
        except Exception as e:
            log.error(f"Error fetching page posts for {page_id}: {e}")
            return []
    
    async def get_group_posts(
        self,
        group_id: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get posts from a Facebook group."""
        group_fields = (
            "id,message,created_time,updated_time,permalink_url,"
            "likes.summary(true),comments.summary(true),from"
        )
        params = {
            "fields": group_fields,
            "limit": limit,
        }
        
        if since:
            params["since"] = int(since.timestamp())
        if until:
            params["until"] = int(until.timestamp())
        
        try:
            data = await self._make_request(f"{group_id}/feed", params)
            posts = data.get("data", [])
            
            # Transform posts to our format
            transformed_posts = []
            for post in posts:
                try:
                    # Check if post should be included
                    if not self._should_include_post(post):
                        continue
                    
                    created_time = datetime.fromisoformat(post["created_time"])
                    
                    transformed_posts.append({
                        "id": post["id"],
                        "message": post.get("message", ""),
                        "created_time": created_time,
                        "permalink_url": post.get("permalink_url", ""),
                        "likes": post.get("likes", {}).get("summary", {}).get("total_count", 0),
                        "comments": post.get("comments", {}).get("summary", {}).get("total_count", 0),
                        "author": post.get("from", {}).get("name", "Unknown"),
                    })
                except Exception as e:
                    log.warning(f"Error transforming group post {post.get('id', 'unknown')}: {e}")
                    continue
            
            return transformed_posts
            
        except Exception as e:
            log.error(f"Error fetching group posts for {group_id}: {e}")
            return []
    
    async def search_pages(
        self,
        query: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search for Facebook pages."""
        params = {
            "q": query,
            "type": "page",
            "fields": "id,name,about,link,likes,talking_about_count,category",
            "limit": limit,
        }
        
        try:
            data = await self._make_request("search", params)
            pages = data.get("data", [])
            
            # Filter for relevant pages (tech, research, AI, etc.)
            relevant_pages = []
            tech_keywords = [
                "tech", "technology", "research", "science", "ai", "artificial intelligence",
                "quantum", "computer", "computing", "software", "engineering", "lab",
                "laboratory", "university", "institute", "innovation", "startup"
            ]
            
            for page in pages:
                category = page.get("category", "").lower()
                about = page.get("about", "").lower()
                name = page.get("name", "").lower()
                
                # Check if page is tech/research related
                is_relevant = any(
                    keyword in category or keyword in about or keyword in name
                    for keyword in tech_keywords
                )
                
                if is_relevant:
                    relevant_pages.append({
                        "id": page["id"],
                        "name": page["name"],
                        "about": page.get("about", ""),
                        "link": page.get("link", ""),
                        "likes": page.get("likes", 0),
                        "category": page.get("category", ""),
                        "talking_about_count": page.get("talking_about_count", 0),
                    })
            
            return relevant_pages
            
        except Exception as e:
            log.error(f"Error searching pages for query '{query}': {e}")
            return []
    
    async def search_groups(
        self,
        query: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search for Facebook groups."""
        params = {
            "q": query,
            "type": "group",
            "fields": "id,name,description,link,member_count,privacy",
            "limit": limit,
        }
        
        try:
            data = await self._make_request("search", params)
            groups = data.get("data", [])
            
            # Filter for relevant groups
            relevant_groups = []
            tech_keywords = [
                "tech", "technology", "research", "science", "ai", "artificial intelligence",
                "quantum", "computer", "computing", "software", "engineering", "lab",
                "laboratory", "university", "innovation", "startup", "developer"
            ]
            
            for group in groups:
                # Skip private groups to respect privacy
                if group.get("privacy") != "OPEN":
                    continue
                
                description = group.get("description", "").lower()
                name = group.get("name", "").lower()
                
                # Check if group is tech/research related
                is_relevant = any(
                    keyword in description or keyword in name
                    for keyword in tech_keywords
                )
                
                if is_relevant:
                    relevant_groups.append({
                        "id": group["id"],
                        "name": group["name"],
                        "description": group.get("description", ""),
                        "link": group.get("link", ""),
                        "member_count": group.get("member_count", 0),
                        "privacy": group.get("privacy", ""),
                    })
            
            return relevant_groups
            
        except Exception as e:
            log.error(f"Error searching groups for query '{query}': {e}")
            return []
    
    def _should_include_post(self, post: Dict[str, Any]) -> bool:
        """Check if a post should be included based on content quality filters."""
        message = post.get("message", "")
        
        # Skip posts with no message or too short
        if not message or len(message.strip()) < 50:
            return False
        
        # Skip posts that are just links
        if re.match(r'^https?://', message.strip()):
            return False
        
        return True


async def fetch_facebook_artifacts(settings: Settings) -> List[Dict[str, Any]]:
    """Fetch artifacts from Facebook pages and groups."""
    
    access_token = settings.app.facebook_access_token or settings.app.sources.facebook.access_token
    if not access_token:
        log.warning("Facebook access token not configured, skipping Facebook fetch")
        return []
    
    async with FacebookClient(access_token) as client:
        artifacts = []
        
        # Get configured pages and groups to monitor
        facebook_config = settings.app.sources.facebook
        pages_to_monitor = facebook_config.pages
        groups_to_monitor = facebook_config.groups
        search_queries = facebook_config.search_queries
        
        # Calculate time window (last 24 hours)
        from datetime import timedelta
        fetch_window_hours = getattr(settings.app.fetch, 'window_hours', 24)
        since = datetime.now(timezone.utc) - timedelta(hours=fetch_window_hours)
        
        # Fetch from configured pages
        if pages_to_monitor:
            log.info(f"Fetching from {len(pages_to_monitor)} configured pages")
            for page_id in pages_to_monitor:
                try:
                    posts = await client.get_page_posts(page_id, since=since)
                    for post in posts:
                        artifacts.append({
                            "type": "post",
                            "source": "facebook",
                            "source_id": post["id"],
                            "title": _truncate_facebook_title(post.get("message")),
                            "text": post["message"],
                            "url": post["permalink_url"],
                            "published_at": post["created_time"].isoformat(),
                            "metadata": {
                                "likes": post["likes"],
                                "comments": post["comments"],
                                "shares": post["shares"],
                                "post_type": post["type"],
                            },
                            "raw_json": json.dumps(post, default=str),
                        })
                    log.info(f"Fetched {len(posts)} posts from page {page_id}")
                except Exception as e:
                    log.error(f"Error fetching from page {page_id}: {e}")
        
        # Fetch from configured groups
        if groups_to_monitor:
            log.info(f"Fetching from {len(groups_to_monitor)} configured groups")
            for group_id in groups_to_monitor:
                try:
                    posts = await client.get_group_posts(group_id, since=since)
                    for post in posts:
                        artifacts.append({
                            "type": "post",
                            "source": "facebook",
                            "source_id": post["id"],
                            "title": _truncate_facebook_title(post.get("message")),
                            "text": post["message"],
                            "url": post["permalink_url"],
                            "published_at": post["created_time"].isoformat(),
                            "metadata": {
                                "likes": post["likes"],
                                "comments": post["comments"],
                                "author": post["author"],
                            },
                            "raw_json": json.dumps(post, default=str),
                        })
                    log.info(f"Fetched {len(posts)} posts from group {group_id}")
                except Exception as e:
                    log.error(f"Error fetching from group {group_id}: {e}")
        
        # Search for new pages/groups if configured
        if search_queries:
            log.info(f"Searching for pages/groups with queries: {search_queries}")
            for query in search_queries:
                try:
                    # Search pages
                    pages = await client.search_pages(query, limit=10)
                    for page in pages:
                        # Fetch recent posts from discovered pages
                        posts = await client.get_page_posts(page["id"], since=since, limit=20)
                        for post in posts:
                            artifacts.append({
                                "type": "post",
                                "source": "facebook",
                                "source_id": post["id"],
                                "title": _truncate_facebook_title(post.get("message")),
                                "text": post["message"],
                                "url": post["permalink_url"],
                                "published_at": post["created_time"].isoformat(),
                                "metadata": {
                                    "likes": post["likes"],
                                    "comments": post["comments"],
                                    "shares": post["shares"],
                                    "page_name": page["name"],
                                    "page_category": page["category"],
                                },
                                "raw_json": json.dumps(post, default=str),
                            })
                    
                    # Search groups
                    groups = await client.search_groups(query, limit=10)
                    for group in groups:
                        # Fetch recent posts from discovered groups
                        posts = await client.get_group_posts(group["id"], since=since, limit=20)
                        for post in posts:
                            artifacts.append({
                                "type": "post",
                                "source": "facebook",
                                "source_id": post["id"],
                                "title": _truncate_facebook_title(post.get("message")),
                                "text": post["message"],
                                "url": post["permalink_url"],
                                "published_at": post["created_time"].isoformat(),
                                "metadata": {
                                    "likes": post["likes"],
                                    "comments": post["comments"],
                                    "author": post["author"],
                                    "group_name": group["name"],
                                    "group_members": group["member_count"],
                                },
                                "raw_json": json.dumps(post, default=str),
                            })
                except Exception as e:
                    log.error(f"Error searching with query '{query}': {e}")
        
        log.info(f"Total Facebook artifacts fetched: {len(artifacts)}")
        return artifacts


if __name__ == "__main__":
    # Simple test
    import os
    
    async def test() -> None:
        token = os.getenv("FACEBOOK_ACCESS_TOKEN")
        if not token:
            print("Please set FACEBOOK_ACCESS_TOKEN environment variable")
            return
        
        async with FacebookClient(token) as client:
            # Test searching for tech pages
            print("Searching for tech pages...")
            pages = await client.search_pages("artificial intelligence research", limit=5)
            for page in pages:
                print(f"- {page['name']} ({page['category']}) - {page['likes']} likes")
            
            print(f"\nFound {len(pages)} relevant pages")
    
    asyncio.run(test())
