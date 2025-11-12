"""Comprehensive tests for LinkedIn client integration."""

from datetime import timezone
from unittest.mock import MagicMock, patch

import pytest

from signal_harvester.config import AppConfig, LinkedInConfig, Settings, SourcesConfig
from signal_harvester.linkedin_client import (
    LinkedInClient,
    fetch_linkedin_artifacts,
)


class TestLinkedInClientBasic:
    """Basic tests for LinkedInClient."""
    
    @pytest.mark.asyncio
    async def test_client_initialization(self):
        """Test LinkedInClient initialization."""
        client = LinkedInClient(access_token="test_token")
        assert client.access_token == "test_token"
        assert client.base_url == "https://api.linkedin.com/v2"
        assert "Authorization" in client.http_client.headers
        assert client.http_client.headers["Authorization"] == "Bearer test_token"
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_get_organization_posts_success(self):
        """Test successful organization posts fetching."""
        client = LinkedInClient(access_token="test_token")
        
        # Mock the HTTP request with realistic LinkedIn post structure
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "elements": [
                {
                    "id": "urn:li:ugcPost:123456789",
                    "author": "urn:li:organization:1337",
                    "created": {"time": 1699444800000},  # Nov 8, 2025
                    "specificContent": {
                        "com.linkedin.ugc.ShareContent": {
                            "shareCommentary": {
                                "text": "Excited to announce our latest breakthrough in AI research! "
                                        "Our team has developed a novel transformer architecture that "
                                        "reduces training time by 40% while improving accuracy."
                            }
                        }
                    },
                    "visibility": {
                        "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                    },
                    "totalShareStatistics": {
                        "likeCount": 245,
                        "commentCount": 18,
                        "shareCount": 32
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "mock response"
        
        with patch.object(client.http_client, "get", return_value=mock_response):
            posts = await client.get_organization_posts("urn:li:organization:1337")
        
        assert len(posts) == 1
        assert posts[0]["id"] == "urn:li:ugcPost:123456789"
        assert (
            "transformer architecture"
            in posts[0]["specificContent"]["com.linkedin.ugc.ShareContent"]["shareCommentary"]["text"]
        )
        assert posts[0]["totalShareStatistics"]["likeCount"] == 245
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_get_organization_posts_with_numeric_id(self):
        """Test organization posts with numeric ID conversion."""
        client = LinkedInClient(access_token="test_token")
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"elements": []}
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_response.text = ""
        
        with patch.object(client.http_client, "get", return_value=mock_response) as mock_get:
            await client.get_organization_posts("1337")  # Numeric ID without URN prefix
            
            # Verify the params include the URN format
            call_args = mock_get.call_args
            assert call_args[1]["params"]["author"] == "urn:li:organization:1337"
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self):
        """Test rate limit error handling."""
        client = LinkedInClient(access_token="test_token")
        
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {
            "status": 429,
            "message": "Too many requests"
        }
        mock_response.headers = {"Retry-After": "60"}
        mock_response.text = "mock response"
        
        with patch.object(client.http_client, "get", return_value=mock_response):
            # Should return empty list on rate limit after retries, not raise
            posts = await client.get_organization_posts("urn:li:organization:1337")
            assert posts == []
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_server_error_retry(self):
        """Test server error retry logic."""
        client = LinkedInClient(access_token="test_token")
        
        # Mock 500 error
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "mock response"
        
        with patch.object(client.http_client, "get", return_value=mock_response):
            # Should return empty list after retries, not raise
            posts = await client.get_organization_posts("urn:li:organization:1337")
            assert posts == []
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_client_error_handling(self):
        """Test 4xx client error handling."""
        client = LinkedInClient(access_token="test_token")
        
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {
            "status": 403,
            "message": "Forbidden - insufficient permissions"
        }
        mock_response.text = "mock response"
        
        with patch.object(client.http_client, "get", return_value=mock_response):
            # Should return empty list on client error, not raise
            posts = await client.get_organization_posts("urn:li:organization:1337")
            assert posts == []
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_get_organization_info_success(self):
        """Test getting organization information."""
        client = LinkedInClient(access_token="test_token")
        
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": 1337,
            "localizedName": "AI Research Labs",
            "localizedWebsite": "https://airesearch.example.com",
            "vanityName": "ai-research-labs",
            "logoV2": {
                "original": "https://media.licdn.com/logo.png"
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "mock response"
        
        with patch.object(client.http_client, "get", return_value=mock_response):
            info = await client.get_organization_info("urn:li:organization:1337")
        
        assert info is not None
        assert info["localizedName"] == "AI Research Labs"
        assert info["id"] == 1337
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_transform_post_success(self):
        """Test post transformation to artifact format."""
        client = LinkedInClient(access_token="test_token")
        
        post = {
            "id": "urn:li:ugcPost:987654321",
            "author": "urn:li:organization:5678",
            "created": {"time": 1699444800000},
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": "Check out our new research paper on quantum algorithms!"
                    }
                }
            },
            "totalShareStatistics": {
                "likeCount": 100,
                "commentCount": 20,
                "shareCount": 15
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }
        
        artifact = client._transform_post(post)
        
        assert artifact["source_id"] == "urn:li:ugcPost:987654321"
        assert artifact["text"] == "Check out our new research paper on quantum algorithms!"
        assert artifact["metadata"]["likes_count"] == 100
        assert artifact["metadata"]["comments_count"] == 20
        assert artifact["metadata"]["shares_count"] == 15
        assert artifact["metadata"]["engagement_score"] == 100 + (20 * 3) + (15 * 2)  # 190
        assert artifact["metadata"]["author_urn"] == "urn:li:organization:5678"
        assert artifact["type"] == "post"
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_timestamp_parsing(self):
        """Test LinkedIn timestamp parsing."""
        client = LinkedInClient(access_token="test_token")
        
        # LinkedIn uses milliseconds since epoch
        timestamp_ms = 1699444800000  # Nov 8, 2025, 00:00:00 UTC
        dt = client._parse_linkedin_timestamp(timestamp_ms)
        
        assert dt.year == 2023
        assert dt.month == 11
        assert dt.day == 8
        assert dt.tzinfo == timezone.utc
        
        await client.__aexit__(None, None, None)


class TestLinkedInIntegration:
    """Integration tests for LinkedIn functionality."""
    
    def test_configuration_loading(self):
        """Test that LinkedIn configuration is properly loaded."""
        linkedin_config = LinkedInConfig(
            access_token="test_token",
            organizations=["urn:li:organization:1337", "urn:li:organization:5678"],
            max_results=100
        )
        
        sources_config = SourcesConfig(linkedin=linkedin_config)
        app_config = AppConfig(
            linkedin_access_token="test_token",
            sources=sources_config
        )
        settings = Settings(app=app_config)
        
        assert settings.app.linkedin_access_token == "test_token"
        assert settings.app.sources.linkedin.organizations == [
            "urn:li:organization:1337",
            "urn:li:organization:5678"
        ]
        assert settings.app.sources.linkedin.max_results == 100
    
    @pytest.mark.asyncio
    async def test_fetch_linkedin_artifacts_no_token(self):
        """Test that fetch returns empty list when token is not configured."""
        linkedin_config = LinkedInConfig(access_token=None)
        sources_config = SourcesConfig(linkedin=linkedin_config)
        app_config = AppConfig(sources=sources_config)
        settings = Settings(app=app_config)
        
        artifacts = await fetch_linkedin_artifacts(settings)
        assert artifacts == []
    
    @pytest.mark.asyncio
    async def test_fetch_linkedin_artifacts_success(self):
        """Test successful artifact fetching."""
        linkedin_config = LinkedInConfig(
            access_token="test_token",
            organizations=["urn:li:organization:1337"],
            max_results=50
        )
        sources_config = SourcesConfig(linkedin=linkedin_config)
        app_config = AppConfig(
            linkedin_access_token="test_token",
            sources=sources_config
        )
        settings = Settings(app=app_config)
        
        # Mock the organization posts response
        mock_posts = [
            {
                "id": "urn:li:ugcPost:123",
                "author": "urn:li:organization:1337",
                "created": {"time": 1699444800000},
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {
                            "text": "Our latest AI breakthrough is here! Revolutionary transformer model."
                        }
                    }
                },
                "totalShareStatistics": {
                    "likeCount": 500,
                    "commentCount": 75,
                    "shareCount": 120
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
            }
        ]
        
        with patch("signal_harvester.linkedin_client.LinkedInClient.get_organization_posts", return_value=mock_posts):
            artifacts = await fetch_linkedin_artifacts(settings)
        
        assert len(artifacts) == 1
        assert artifacts[0]["source"] == "linkedin"
        assert artifacts[0]["source_id"] == "urn:li:ugcPost:123"
        assert "transformer model" in artifacts[0]["text"]
        assert artifacts[0]["metadata"]["engagement_score"] == 500 + (75 * 3) + (120 * 2)
    
    @pytest.mark.asyncio
    async def test_fetch_linkedin_artifacts_multiple_orgs(self):
        """Test fetching from multiple organizations."""
        linkedin_config = LinkedInConfig(
            access_token="test_token",
            organizations=["urn:li:organization:1337", "urn:li:organization:5678"]
        )
        sources_config = SourcesConfig(linkedin=linkedin_config)
        app_config = AppConfig(
            linkedin_access_token="test_token",
            sources=sources_config
        )
        settings = Settings(app=app_config)
        
        mock_posts_org1 = [
            {
                "id": "urn:li:ugcPost:111",
                "author": "urn:li:organization:1337",
                "created": {"time": 1699444800000},
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": "Organization 1 post about quantum computing research"}
                    }
                },
                "totalShareStatistics": {"likeCount": 100, "commentCount": 10, "shareCount": 5},
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
            }
        ]
        
        mock_posts_org2 = [
            {
                "id": "urn:li:ugcPost:222",
                "author": "urn:li:organization:5678",
                "created": {"time": 1699444800000},
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": "Organization 2 post about machine learning breakthroughs"}
                    }
                },
                "totalShareStatistics": {"likeCount": 200, "commentCount": 20, "shareCount": 10},
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
            }
        ]
        
        async def mock_get_org_posts(org_id, since=None, limit=50):
            if "1337" in org_id:
                return mock_posts_org1
            elif "5678" in org_id:
                return mock_posts_org2
            return []
        
        with patch(
            "signal_harvester.linkedin_client.LinkedInClient.get_organization_posts",
            side_effect=mock_get_org_posts,
        ):
            artifacts = await fetch_linkedin_artifacts(settings)
        
        assert len(artifacts) == 2
        assert artifacts[0]["text"] == "Organization 1 post about quantum computing research"
        assert artifacts[1]["text"] == "Organization 2 post about machine learning breakthroughs"
    
    @pytest.mark.asyncio
    async def test_fetch_linkedin_artifacts_error_handling(self):
        """Test that errors during fetch are handled gracefully."""
        linkedin_config = LinkedInConfig(
            access_token="test_token",
            organizations=["urn:li:organization:1337"]
        )
        sources_config = SourcesConfig(linkedin=linkedin_config)
        app_config = AppConfig(
            linkedin_access_token="test_token",
            sources=sources_config
        )
        settings = Settings(app=app_config)
        
        # Mock an exception during fetch
        with patch(
            "signal_harvester.linkedin_client.LinkedInClient.get_organization_posts",
            side_effect=Exception("API Error"),
        ):
            artifacts = await fetch_linkedin_artifacts(settings)
        
        # Should return empty list on error
        assert artifacts == []
