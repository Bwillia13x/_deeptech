"""Simplified tests for Phase 2.5 Facebook integration."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from signal_harvester.config import AppConfig, FacebookConfig, FetchConfig, Settings, SourcesConfig
from signal_harvester.facebook_client import (
    FacebookClient,
    fetch_facebook_artifacts,
)


class TestFacebookClientBasic:
    """Basic tests for FacebookClient."""
    
    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test FacebookClient initialization."""
        client = FacebookClient(access_token="test_token", version="v18.0")
        assert client.access_token == "test_token"
        assert client.version == "v18.0"
        assert client.base_url == "https://graph.facebook.com/v18.0"
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_get_page_posts_success(self):
        """Test successful page posts fetching."""
        client = FacebookClient(access_token="test_token")
        
        # Mock the HTTP request
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {
                    "id": "page_123_456",
                    "message": (
                        "Exciting breakthrough in quantum computing research! "
                        "Our team has developed a novel approach to quantum "
                        "error correction using surface codes."
                    ),
                    "created_time": "2025-11-08T10:00:00+00:00",
                    "permalink_url": "https://facebook.com/123/posts/456",
                    "likes": {"summary": {"total_count": 150}},
                    "comments": {"summary": {"total_count": 25}},
                    "shares": {"count": 10},
                    "type": "status",
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        
        with patch.object(client.http_client, "get", return_value=mock_response):
            posts = await client.get_page_posts("testpage")
        
        assert len(posts) == 1
        assert posts[0]["id"] == "page_123_456"
        assert "quantum computing" in posts[0]["message"].lower()
        assert posts[0]["likes"] == 150
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self):
        """Test rate limit error handling."""
        client = FacebookClient(access_token="test_token")
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "error": {
                "code": 4,
                "message": "Application request limit reached"
            }
        }
        
        mock_http_error = httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=MagicMock(),
            response=mock_response
        )
        mock_response.raise_for_status = MagicMock(side_effect=mock_http_error)
        
        with patch.object(client.http_client, "get", return_value=mock_response):
            posts = await client.get_page_posts("testpage")
            # Should return empty list on error, not raise exception
            assert posts == []
        
        await client.__aexit__(None, None, None)


class TestFacebookIntegration:
    """Integration tests for Facebook functionality."""
    
    def test_configuration_loading(self):
        """Test that Facebook configuration is properly loaded."""
        facebook_config = FacebookConfig(
            access_token="test_token",
            pages=["page1", "page2"],
            search_queries=["AI", "quantum"]
        )
        
        sources_config = SourcesConfig(facebook=facebook_config)
        app_config = AppConfig(
            facebook_access_token="test_token",
            sources=sources_config
        )
        
        settings = Settings(app=app_config, queries=[])
        
        assert settings.app.facebook_access_token == "test_token"
        assert "page1" in settings.app.sources.facebook.pages
        assert len(settings.app.sources.facebook.search_queries) == 2
    
    @pytest.mark.asyncio
    async def test_fetch_facebook_artifacts_no_token(self):
        """Test fetch_facebook_artifacts with no token configured."""
        facebook_config = FacebookConfig(access_token=None)
        sources_config = SourcesConfig(facebook=facebook_config)
        app_config = AppConfig(sources=sources_config)
        settings = Settings(app=app_config, queries=[])
        
        artifacts = await fetch_facebook_artifacts(settings)
        
        assert artifacts == []
    
    @pytest.mark.asyncio
    async def test_fetch_facebook_artifacts_with_mock(self):
        """Test fetch_facebook_artifacts with mocked client."""
        facebook_config = FacebookConfig(
            access_token="test_token",
            pages=["testpage"],
            groups=[],
            search_queries=[]
        )
        sources_config = SourcesConfig(facebook=facebook_config)
        app_config = AppConfig(
            sources=sources_config,
            fetch=FetchConfig()
        )
        settings = Settings(app=app_config, queries=[])
        
        # Mock the FacebookClient
        mock_client = AsyncMock()
        mock_client.get_page_posts = AsyncMock(return_value=[{
            "id": "page_123_456",
            "message": "Quantum computing breakthrough research",
            "created_time": datetime.now(timezone.utc),
            "permalink_url": "https://facebook.com/123/posts/456",
            "likes": 150,
            "comments": 25,
            "shares": 10,
            "type": "status"
        }])
        mock_client.get_group_posts = AsyncMock(return_value=[])
        mock_client.search_pages = AsyncMock(return_value=[])
        mock_client.search_groups = AsyncMock(return_value=[])
        
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        with patch("signal_harvester.facebook_client.FacebookClient", return_value=mock_client):
            artifacts = await fetch_facebook_artifacts(settings)
        
        assert len(artifacts) == 1
        assert artifacts[0]["source"] == "facebook"
        assert artifacts[0]["type"] == "post"
        assert "quantum computing" in artifacts[0]["text"].lower()
