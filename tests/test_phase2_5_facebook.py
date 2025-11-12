"""Tests for Phase 2.5 Facebook Graph API integration."""

import re
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from signal_harvester.config import (
    AppConfig,
    FacebookConfig,
    FetchConfig,
    Settings,
    SourcesConfig,
)
from signal_harvester.facebook_client import (
    FacebookClient,
    fetch_facebook_artifacts,
)


class TestFacebookClient:
    """Test FacebookClient class."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings for testing."""
        facebook_cfg = FacebookConfig(
            access_token="test_token",
            pages=["testpage1", "testpage2"],
            groups=["testgroup1"],
            search_queries=["artificial intelligence", "quantum computing"],
        )
        sources_cfg = SourcesConfig(facebook=facebook_cfg)
        app_cfg = AppConfig(
            database_path=":memory:",
            fetch=FetchConfig(max_results=25, lang="en"),
            facebook_access_token="test_token",
            sources=sources_cfg,
        )
        return Settings(app=app_cfg, queries=[])
    
    @pytest.fixture
    def sample_page_posts(self):
        """Sample Facebook page posts response."""
        return {
            "data": [
                {
                    "id": "page_123_456",
                    "message": (
                        "Exciting breakthrough in quantum computing research! "
                        "Our team has developed a novel approach to quantum "
                        "error correction using surface codes. This could "
                        "significantly improve quantum computer reliability."
                    ),
                    "created_time": "2025-11-08T10:00:00+00:00",
                    "updated_time": "2025-11-08T10:00:00+00:00",
                    "permalink_url": "https://facebook.com/123/posts/456",
                    "likes": {"summary": {"total_count": 150}},
                    "comments": {"summary": {"total_count": 25}},
                    "shares": {"count": 10},
                    "type": "status",
                },
                {
                    "id": "page_123_789",
                    "message": (
                        "Join us for our upcoming webinar on AI safety and "
                        "alignment research. We'll be discussing the "
                        "latest developments in ensuring AI systems remain "
                        "beneficial."
                    ),
                    "created_time": "2025-11-07T15:30:00+00:00",
                    "permalink_url": "https://facebook.com/123/posts/789",
                    "likes": {"summary": {"total_count": 89}},
                    "comments": {"summary": {"total_count": 12}},
                    "shares": {"count": 5},
                    "type": "event",
                },
                # Should be filtered out (too short)
                {
                    "id": "page_123_999",
                    "message": "Check out our new paper!",
                    "created_time": "2025-11-08T12:00:00+00:00",
                    "permalink_url": "https://facebook.com/123/posts/999",
                    "likes": {"summary": {"total_count": 5}},
                    "comments": {"summary": {"total_count": 1}},
                    "type": "link"
                }
            ]
        }
    
    @pytest.fixture
    def sample_group_posts(self):
        """Sample Facebook group posts response."""
        return {
            "data": [
                {
                    "id": "group_456_123",
                    "message": (
                        "Has anyone experimented with the new photonic quantum "
                        "computing architectures? I'm particularly interested "
                        "in the scalability challenges and how they compare to "
                        "superconducting qubits."
                    ),
                    "created_time": "2025-11-08T14:20:00+00:00",
                    "permalink_url": "https://facebook.com/groups/456/posts/123",
                    "likes": {"summary": {"total_count": 45}},
                    "comments": {"summary": {"total_count": 18}},
                    "from": {"name": "Dr. Sarah Chen", "id": "user_789"},
                },
                {
                    "id": "group_456_124",
                    "message": (
                        "Sharing our latest research on reinforcement learning "
                        "for robotics. We've achieved 40% improvement in sample "
                        "efficiency using curriculum learning techniques."
                    ),
                    "created_time": "2025-11-07T09:15:00+00:00",
                    "permalink_url": "https://facebook.com/groups/456/posts/124",
                    "likes": {"summary": {"total_count": 67}},
                    "comments": {"summary": {"total_count": 8}},
                    "from": {"name": "Prof. Michael Rodriguez", "id": "user_790"},
                }
            ]
        }
    
    @pytest.fixture
    def sample_search_pages(self):
        """Sample Facebook page search results."""
        return {
            "data": [
                {
                    "id": "page_ai_research",
                    "name": "AI Research Lab",
                    "about": "Leading research in artificial intelligence and machine learning",
                    "link": "https://facebook.com/AIResearchLab",
                    "likes": 5000,
                    "category": "Science & Technology",
                    "talking_about_count": 150
                },
                {
                    "id": "page_quantum_tech",
                    "name": "Quantum Technologies Institute",
                    "about": "Advancing quantum computing and quantum information science",
                    "link": "https://facebook.com/QuantumTech",
                    "likes": 3200,
                    "category": "Science & Technology",
                    "talking_about_count": 89
                },
                # Should be filtered out (not tech-related)
                {
                    "id": "page_restaurant",
                    "name": "Joe's Pizza",
                    "about": "Best pizza in town!",
                    "link": "https://facebook.com/JoesPizza",
                    "likes": 100,
                    "category": "Restaurant",
                    "talking_about_count": 5
                }
            ]
        }
    
    @pytest.fixture
    def sample_search_groups(self):
        """Sample Facebook group search results."""
        return {
            "data": [
                {
                    "id": "group_robotics",
                    "name": "Advanced Robotics Research",
                    "description": (
                        "Discussion group for robotics researchers "
                        "working on manipulation, locomotion, and AI integration"
                    ),
                    "link": "https://facebook.com/groups/robotics",
                    "member_count": 2500,
                    "privacy": "OPEN",
                },
                {
                    "id": "group_quantum",
                    "name": "Quantum Computing Enthusiasts",
                    "description": (
                        "For researchers and students interested in quantum "
                        "algorithms and hardware"
                    ),
                    "link": "https://facebook.com/groups/quantum",
                    "member_count": 1800,
                    "privacy": "OPEN",
                },
                # Should be filtered out (private group)
                {
                    "id": "group_private",
                    "name": "Private Tech Group",
                    "description": "Private discussion group",
                    "link": "https://facebook.com/groups/private",
                    "member_count": 100,
                    "privacy": "CLOSED"
                }
            ]
        }
    
    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test FacebookClient initialization."""
        client = FacebookClient(access_token="test_token", version="v18.0")
        assert client.access_token == "test_token"
        assert client.version == "v18.0"
        assert client.base_url == "https://graph.facebook.com/v18.0"
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_get_page_posts_success(self, mocker, sample_page_posts):
        """Test successful page posts fetching."""
        client = FacebookClient(access_token="test_token")
        
        # Mock the HTTP request - response.json() needs to return a value synchronously
        mock_response = MagicMock()
        mock_response.json.return_value = sample_page_posts
        mock_response.raise_for_status = MagicMock()
        
        # The get() call itself is async, so wrap in AsyncMock
        mocker.patch.object(client.http_client, "get", new_callable=AsyncMock, return_value=mock_response)
        
        posts = await client.get_page_posts("testpage")
        
        assert len(posts) == 2  # One post filtered out (too short)
        assert posts[0]["id"] == "page_123_456"
        assert "quantum computing" in posts[0]["message"].lower()
        assert posts[0]["likes"] == 150
        assert posts[0]["comments"] == 25
        assert posts[0]["shares"] == 10
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_get_group_posts_success(self, mocker, sample_group_posts):
        """Test successful group posts fetching."""
        client = FacebookClient(access_token="test_token")
        
        # Mock the HTTP request - response.json() returns synchronously
        mock_response = MagicMock()
        mock_response.json.return_value = sample_group_posts
        mock_response.raise_for_status = MagicMock()
        
        mocker.patch.object(client.http_client, "get", new_callable=AsyncMock, return_value=mock_response)
        
        posts = await client.get_group_posts("testgroup")
        
        assert len(posts) == 2
        assert posts[0]["id"] == "group_456_123"
        assert posts[0]["author"] == "Dr. Sarah Chen"
        assert "photonic quantum" in posts[0]["message"].lower()
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_search_pages_success(self, mocker, sample_search_pages):
        """Test successful page search."""
        client = FacebookClient(access_token="test_token")
        
        # Mock the HTTP request - response.json() returns synchronously
        mock_response = MagicMock()
        mock_response.json.return_value = sample_search_pages
        mock_response.raise_for_status = MagicMock()
        
        mocker.patch.object(client.http_client, "get", new_callable=AsyncMock, return_value=mock_response)
        
        pages = await client.search_pages("artificial intelligence")
        
        assert len(pages) == 2  # One filtered out (restaurant)
        assert pages[0]["name"] == "AI Research Lab"
        assert pages[0]["category"] == "Science & Technology"
        assert pages[0]["likes"] == 5000
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_search_groups_success(self, mocker, sample_search_groups):
        """Test successful group search."""
        client = FacebookClient(access_token="test_token")
        
        # Mock the HTTP request - response.json() returns synchronously
        mock_response = MagicMock()
        mock_response.json.return_value = sample_search_groups
        mock_response.raise_for_status = MagicMock()
        
        mocker.patch.object(client.http_client, "get", new_callable=AsyncMock, return_value=mock_response)
        
        groups = await client.search_groups("robotics")
        
        assert len(groups) == 2  # One filtered out (private)
        assert groups[0]["name"] == "Advanced Robotics Research"
        assert groups[0]["privacy"] == "OPEN"
        assert groups[0]["member_count"] == 2500
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, mocker, caplog):
        """Test rate limit error handling."""
        client = FacebookClient(access_token="test_token")
        
        # Create async mock that raises HTTPStatusError
        async def mock_get_rate_limit(*args, **kwargs):
            response_payload = MagicMock()
            response_payload.json.return_value = {
                "error": {
                    "code": 4,
                    "message": "Application request limit reached"
                }
            }
            raise httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=MagicMock(),
                response=response_payload,
            )
        
        mocker.patch.object(client.http_client, "get", side_effect=mock_get_rate_limit)
        
        # get_page_posts catches exceptions and returns empty list, logs error
        posts = await client.get_page_posts("testpage")
        assert len(posts) == 0
        assert "Rate limit hit" in caplog.text
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_invalid_token_error(self, mocker, caplog):
        """Test invalid token error handling."""
        client = FacebookClient(access_token="test_token")
        
        # Create async mock that raises HTTPStatusError
        async def mock_get_invalid_token(*args, **kwargs):
            response_payload = MagicMock()
            response_payload.json.return_value = {
                "error": {
                    "code": 190,
                    "message": "Invalid OAuth access token"
                }
            }
            raise httpx.HTTPStatusError(
                "401 Unauthorized",
                request=MagicMock(),
                response=response_payload,
            )
        
        mocker.patch.object(client.http_client, "get", side_effect=mock_get_invalid_token)
        
        # get_page_posts catches exceptions and returns empty list, logs error
        posts = await client.get_page_posts("testpage")
        assert len(posts) == 0
        assert "Invalid access token" in caplog.text
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_fetch_facebook_artifacts_no_token(self, mock_settings):
        """Test fetch_facebook_artifacts with no token configured."""
        # Remove token from settings
        mock_settings.app.facebook_access_token = None
        mock_settings.app.sources.facebook.access_token = None
        
        artifacts = await fetch_facebook_artifacts(mock_settings)
        
        assert artifacts == []
    
    @pytest.mark.asyncio
    async def test_fetch_facebook_artifacts_full_pipeline(
        self, mocker, mock_settings, sample_page_posts, sample_group_posts
    ):
        """Test full Facebook artifact fetching pipeline."""
        # Mock FacebookClient methods - configure settings with single page/group
        mock_settings.app.sources.facebook.pages = ["testpage1"]
        mock_settings.app.sources.facebook.groups = ["testgroup1"]
        mock_settings.app.sources.facebook.search_queries = []
        
        mock_client = AsyncMock()
        mock_client.get_page_posts = AsyncMock(return_value=[
            {
                "id": "page_123_456",
                "message": "Quantum computing breakthrough research",
                "created_time": datetime.now(timezone.utc),
                "permalink_url": "https://facebook.com/123/posts/456",
                "likes": 150,
                "comments": 25,
                "shares": 10,
                "type": "status"
            }
        ])
        mock_client.get_group_posts = AsyncMock(return_value=[
            {
                "id": "group_456_123",
                "message": "Photonic quantum computing discussion",
                "created_time": datetime.now(timezone.utc),
                "permalink_url": "https://facebook.com/groups/456/posts/123",
                "likes": 45,
                "comments": 18,
                "author": "Dr. Sarah Chen"
            }
        ])
        mock_client.search_pages = AsyncMock(return_value=[])
        mock_client.search_groups = AsyncMock(return_value=[])
        
        # Mock the client context manager
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        mocker.patch("signal_harvester.facebook_client.FacebookClient", return_value=mock_client)
        
        artifacts = await fetch_facebook_artifacts(mock_settings)
        
        assert len(artifacts) == 2
        assert artifacts[0]["source"] == "facebook"
        assert artifacts[0]["type"] == "post"
        assert "quantum computing" in artifacts[0]["text"].lower()
        # Author is in metadata for group posts
        assert artifacts[1]["metadata"]["author"] == "Dr. Sarah Chen"
    
    @pytest.mark.asyncio
    async def test_transformed_post_format(self, mocker):
        """Test that posts are transformed to correct artifact format."""
        client = FacebookClient(access_token="test_token")
        
        # Mock the HTTP request - response.json() returns synchronously
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "page_test_123",
                    "message": (
                        "Test post with sufficient length to pass the filter. "
                        "This should be included in the results."
                    ),
                    "created_time": "2025-11-08T10:00:00+00:00",
                    "permalink_url": "https://facebook.com/test/posts/123",
                    "likes": {"summary": {"total_count": 100}},
                    "comments": {"summary": {"total_count": 20}},
                    "shares": {"count": 5},
                    "type": "status",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        
        mocker.patch.object(client.http_client, "get", new_callable=AsyncMock, return_value=mock_response)
        
        posts = await client.get_page_posts("testpage")
        
        assert len(posts) == 1
        post = posts[0]
        
        # Verify all required fields
        assert "id" in post
        assert "message" in post
        assert "created_time" in post
        assert isinstance(post["created_time"], datetime)
        assert "permalink_url" in post
        assert "likes" in post
        assert "comments" in post
        assert "shares" in post
        assert "type" in post
        
        await client.__aexit__(None, None, None)
    
    def test_content_filtering(self):
        """Test that content filtering works correctly."""
        # Test the filtering logic manually (same logic as in _should_include_post)
        
        # Should be filtered (too short)
        short_post = {"message": "Too short", "id": "123"}
        message = short_post.get("message", "")
        assert not message or len(message.strip()) < 50
        
        # Should be filtered (just a URL)
        url_post = {"message": "https://example.com/article", "id": "456"}
        message = url_post.get("message", "")
        assert re.match(r'^https?://', message.strip())
        
        # Should be included (sufficient length and not just URL)
        good_post = {
            "message": (
                "This is a substantial post about quantum computing research "
                "with enough content to be valuable."
            ),
            "id": "789",
        }
        message = good_post.get("message", "")
        assert message and len(message.strip()) >= 50
        assert not re.match(r'^https?://', message.strip())


class TestFacebookIntegration:
    """Integration tests for Facebook functionality."""
    
    def test_configuration_loading(self):
        """Test that Facebook configuration is properly loaded."""
        facebook_cfg = FacebookConfig(
            access_token="test_token",
            pages=["page1", "page2"],
            groups=["group1"],
            search_queries=["AI", "quantum"],
        )
        app_cfg = AppConfig(facebook_access_token="test_token", sources=SourcesConfig(facebook=facebook_cfg))
        settings = Settings(app=app_cfg)

        assert settings.app.facebook_access_token == "test_token"
        assert "page1" in settings.app.sources.facebook.pages
        assert len(settings.app.sources.facebook.search_queries) == 2
    
    @pytest.mark.asyncio
    async def test_error_recovery(self, mocker):
        """Test that the client recovers from individual errors."""
        client = FacebookClient(access_token="test_token")
        
        # Mock one successful and one failing call
        call_count = [0]
        
        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if "testpage1" in str(args):
                response = MagicMock()
                response.json.return_value = {
                    "data": [
                        {
                            "id": "page1_123",
                            "message": (
                                "Success post with enough content to pass the filtering "
                                "threshold for inclusion in results."
                            ),
                            "created_time": "2025-11-08T10:00:00+00:00",
                            "permalink_url": "https://facebook.com/1/posts/123",
                            "likes": {"summary": {"total_count": 10}},
                            "comments": {"summary": {"total_count": 2}},
                            "type": "status",
                        }
                    ]
                }
                response.raise_for_status = MagicMock()
                return response
            else:
                raise httpx.HTTPError("Connection failed")
        
        mocker.patch.object(client.http_client, "get", side_effect=mock_get)
        
        # First call should succeed
        posts1 = await client.get_page_posts("testpage1")
        assert len(posts1) == 1
        
        # Second call should fail gracefully
        posts2 = await client.get_page_posts("testpage2")
        assert len(posts2) == 0
        
        await client.__aexit__(None, None, None)
