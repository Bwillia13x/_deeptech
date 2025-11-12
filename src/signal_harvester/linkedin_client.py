"""LinkedIn API v2 client for organization and personal posts."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from .config import Settings
from .logger import get_logger

log = get_logger(__name__)


class LinkedInAPIError(Exception):
    """Raised when LinkedIn API returns an error."""
    pass


class LinkedInRateLimitError(LinkedInAPIError):
    """Raised when LinkedIn API rate limit is hit."""
    pass


class LinkedInClient:
    """Client for LinkedIn API v2."""
    
    def __init__(self, access_token: str):
        """
        Initialize LinkedIn API v2 client.
        
        Args:
            access_token: LinkedIn OAuth 2.0 access token
        """
        self.access_token = access_token
        self.base_url = "https://api.linkedin.com/v2"
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=10),
            headers={
                "Authorization": f"Bearer {access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
                "LinkedIn-Version": "202311",  # API version
            }
        )
        
    async def __aenter__(self) -> "LinkedInClient":
        return self
        
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> None:
        await self.http_client.aclose()
    
    async def get_organization_posts(
        self,
        org_id: str,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch posts from a LinkedIn organization page.
        
        Args:
            org_id: LinkedIn organization URN (e.g., "urn:li:organization:123456")
            since: Only fetch posts after this datetime
            limit: Maximum number of posts to fetch
        
        Returns:
            List of organization posts with metadata
        """
        if not org_id.startswith("urn:li:organization:"):
            org_id = f"urn:li:organization:{org_id}"
        
        # Build query parameters
        params = {
            "q": "author",
            "author": org_id,
            "count": min(limit, 100),  # LinkedIn max is 100
            "sortBy": "LAST_MODIFIED",
        }
        
        try:
            url = f"{self.base_url}/ugcPosts"
            response = await self._make_request("GET", url, params=params)
            
            if not response or "elements" not in response:
                log.warning(f"No posts found for organization {org_id}")
                return []
            
            posts = response["elements"]
            
            # Filter by date if specified
            if since:
                posts = [
                    post for post in posts
                    if self._parse_linkedin_timestamp(post.get("created", {}).get("time", 0)) > since
                ]
            
            log.info(f"Fetched {len(posts)} posts from LinkedIn organization {org_id}")
            return posts
            
        except Exception as e:
            log.error(f"Error fetching organization posts for {org_id}: {e}")
            return []
    
    async def get_person_posts(
        self,
        person_id: str,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch posts from a LinkedIn personal profile.
        
        Note: Requires user consent for personal data access.
        
        Args:
            person_id: LinkedIn person URN (e.g., "urn:li:person:abc123")
            since: Only fetch posts after this datetime
            limit: Maximum number of posts to fetch
        
        Returns:
            List of personal posts with metadata
        """
        if not person_id.startswith("urn:li:person:"):
            person_id = f"urn:li:person:{person_id}"
        
        params = {
            "q": "author",
            "author": person_id,
            "count": min(limit, 100),
            "sortBy": "LAST_MODIFIED",
        }
        
        try:
            url = f"{self.base_url}/ugcPosts"
            response = await self._make_request("GET", url, params=params)
            
            if not response or "elements" not in response:
                log.warning(f"No posts found for person {person_id}")
                return []
            
            posts = response["elements"]
            
            # Filter by date if specified
            if since:
                posts = [
                    post for post in posts
                    if self._parse_linkedin_timestamp(post.get("created", {}).get("time", 0)) > since
                ]
            
            log.info(f"Fetched {len(posts)} posts from LinkedIn person {person_id}")
            return []
            
        except Exception as e:
            log.error(f"Error fetching person posts for {person_id}: {e}")
            return []
    
    async def get_organization_info(self, org_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a LinkedIn organization.
        
        Args:
            org_id: LinkedIn organization ID or URN
        
        Returns:
            Organization information dictionary
        """
        if not org_id.startswith("urn:li:organization:"):
            org_id = f"urn:li:organization:{org_id}"
        
        # Extract numeric ID from URN
        numeric_id = org_id.split(":")[-1]
        
        try:
            url = f"{self.base_url}/organizations/{numeric_id}"
            response = await self._make_request("GET", url)
            
            if response:
                log.info(f"Fetched organization info for {org_id}")
                return response
            return None
            
        except Exception as e:
            log.error(f"Error fetching organization info for {org_id}: {e}")
            return None
    
    async def search_organizations(
        self,
        query: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Search for LinkedIn organizations.
        
        Note: Organization search requires partner API access.
        This is a placeholder for future implementation.
        
        Args:
            query: Search query string
            limit: Maximum results to return
        
        Returns:
            List of organization search results
        """
        log.warning(
            "LinkedIn organization search requires partner API access. "
            "Returning empty results."
        )
        return []
    
    async def _make_request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request to LinkedIn API with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL to request
            params: Query parameters
            json_data: JSON body for POST/PUT requests
            max_retries: Maximum number of retry attempts
        
        Returns:
            Response JSON or None on error
        """
        backoff = 1.0
        
        for attempt in range(1, max_retries + 1):
            try:
                if method == "GET":
                    response = await self.http_client.get(url, params=params)
                elif method == "POST":
                    response = await self.http_client.post(url, params=params, json=json_data)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    log.warning(
                        f"LinkedIn API rate limited (429). Attempt {attempt}/{max_retries}."
                    )
                    if attempt < max_retries:
                        retry_after = response.headers.get("Retry-After")
                        sleep_s = (
                            float(retry_after) if retry_after and retry_after.isdigit()
                            else backoff
                        )
                        await asyncio.sleep(sleep_s)
                        backoff *= 2
                        continue
                    raise LinkedInRateLimitError("LinkedIn API rate limit exceeded")
                
                # Handle server errors (5xx)
                if 500 <= response.status_code < 600:
                    log.warning(
                        f"LinkedIn API server error {response.status_code}. "
                        f"Attempt {attempt}/{max_retries}."
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    raise LinkedInAPIError(f"LinkedIn API server error: {response.status_code}")
                
                # Handle client errors (4xx except 429)
                if 400 <= response.status_code < 500:
                    error_data = response.json() if response.text else {}
                    log.error(
                        f"LinkedIn API client error {response.status_code}: {error_data}"
                    )
                    raise LinkedInAPIError(
                        f"LinkedIn API error {response.status_code}: {error_data}"
                    )
                
                response.raise_for_status()
                return response.json() if response.text else {}
                
            except httpx.HTTPError as e:
                log.error(
                    f"LinkedIn API HTTP error (attempt {attempt}/{max_retries}): {e}"
                )
                if attempt < max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise LinkedInAPIError(f"LinkedIn API request failed: {e}")
        
        return None
    
    def _parse_linkedin_timestamp(self, timestamp_ms: int) -> datetime:
        """
        Convert LinkedIn timestamp (milliseconds since epoch) to datetime.
        
        Args:
            timestamp_ms: Timestamp in milliseconds
        
        Returns:
            UTC datetime object
        """
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
    
    def _transform_post(self, post: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform LinkedIn post to our standard artifact format.
        
        Args:
            post: Raw LinkedIn post data
        
        Returns:
            Transformed post in artifact format
        """
        try:
            # Extract post text
            specific_content = post.get("specificContent", {})
            share_content = specific_content.get("com.linkedin.ugc.ShareContent", {})
            share_commentary = share_content.get("shareCommentary", {})
            text = share_commentary.get("text", "")
            
            # Extract author URN
            author_urn = post.get("author", "")
            
            # Extract created time
            created_info = post.get("created", {})
            created_time = created_info.get("time", 0)
            created_dt = self._parse_linkedin_timestamp(created_time)
            
            # Extract engagement metrics
            total_share_stats = post.get("totalShareStatistics", {})
            likes_count = total_share_stats.get("likeCount", 0)
            comments_count = total_share_stats.get("commentCount", 0)
            shares_count = total_share_stats.get("shareCount", 0)
            
            # Calculate engagement score
            engagement_score = likes_count + (comments_count * 3) + (shares_count * 2)
            
            # Extract post ID
            post_id = post.get("id", "")
            
            # Build post URL (may not be directly accessible)
            post_url = f"https://www.linkedin.com/feed/update/{post_id}" if post_id else ""
            
            artifact = {
                "source_id": post_id,
                "title": f"LinkedIn post from {author_urn}",
                "text": text,
                "url": post_url,
                "published_at": created_dt.isoformat(),
                "updated_at": created_dt.isoformat(),
                "metadata": {
                    "author_urn": author_urn,
                    "likes_count": likes_count,
                    "comments_count": comments_count,
                    "shares_count": shares_count,
                    "engagement_score": engagement_score,
                    "visibility": post.get("visibility", {}).get("com.linkedin.ugc.MemberNetworkVisibility", "UNKNOWN"),
                },
                "type": "post",
            }
            
            return artifact
            
        except Exception as e:
            log.error(f"Error transforming LinkedIn post {post.get('id')}: {e}")
            return {}


async def fetch_linkedin_artifacts(settings: Settings) -> List[Dict[str, Any]]:
    """
    Fetch artifacts from LinkedIn organizations and profiles.
    
    Args:
        settings: Application settings with LinkedIn configuration
    
    Returns:
        List of transformed LinkedIn post artifacts
    """
    access_token = settings.app.linkedin_access_token or settings.app.sources.linkedin.access_token
    if not access_token:
        log.warning("LinkedIn access token not configured, skipping LinkedIn fetch")
        return []
    
    async with LinkedInClient(access_token) as client:
        artifacts = []
        
        # Get configured organizations to monitor
        linkedin_config = settings.app.sources.linkedin
        organizations = linkedin_config.organizations
        
        # Calculate time window (last 24 hours)
        fetch_window_hours = getattr(settings.app.fetch, 'window_hours', 24)
        since = datetime.now(timezone.utc) - timedelta(hours=fetch_window_hours)
        
        # Fetch from configured organizations
        if organizations:
            log.info(f"Fetching from {len(organizations)} configured LinkedIn organizations")
            for org_id in organizations:
                try:
                    posts = await client.get_organization_posts(org_id, since=since, limit=50)
                    for post in posts:
                        artifact = client._transform_post(post)
                        if artifact and artifact.get("text"):  # Only include posts with content
                            artifact["source"] = "linkedin"
                            artifact["raw_json"] = json.dumps(post, default=str)
                            artifacts.append(artifact)
                    
                    log.info(f"Fetched {len(posts)} posts from LinkedIn organization {org_id}")
                except Exception as e:
                    log.error(f"Error fetching from LinkedIn organization {org_id}: {e}")
        
        log.info(f"Total LinkedIn artifacts fetched: {len(artifacts)}")
        return artifacts


if __name__ == "__main__":
    # Simple test
    import os
    
    async def test() -> None:
        token = os.getenv("LINKEDIN_ACCESS_TOKEN")
        if not token:
            print("Please set LINKEDIN_ACCESS_TOKEN environment variable")
            return
        
        async with LinkedInClient(token) as client:
            # Test fetching organization info (requires valid org ID)
            org_id = "1337"  # LinkedIn company ID
            print(f"Fetching info for organization {org_id}...")
            info = await client.get_organization_info(org_id)
            if info:
                print(f"Organization: {info.get('localizedName', 'Unknown')}")
            else:
                print("Could not fetch organization info (may require permissions)")
    
    asyncio.run(test())
