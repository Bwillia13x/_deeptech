"""Tests for Phase 2.5 Enhanced GitHub functionality."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from signal_harvester.config import AppConfig, GitHubConfig, Settings, SourcesConfig
from signal_harvester.github_client import (
    GitHubClient,
    fetch_github_artifacts,
    release_to_artifact,
    repo_to_artifact,
)


class TestGitHubEnhancedFeatures:
    """Test enhanced GitHub features for Phase 2.5."""
    
    @pytest.mark.asyncio
    async def test_get_commit_details_success(self, mocker):
        """Test getting detailed commit information."""
        client = GitHubClient(token="test_token")
        
        # Mock response - client.get() returns synchronous json()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "sha": "abc123def456",
            "commit": {
                "author": {"name": "Alice Chen", "email": "alice@example.com"},
                "message": "Fix quantum error correction bug in surface code implementation"
            },
            "stats": {"additions": 150, "deletions": 25, "total": 175},
            "files": [
                {"filename": "quantum/error_correction.py", "additions": 100, "deletions": 10},
                {"filename": "tests/test_error_correction.py", "additions": 50, "deletions": 15}
            ]
        }
        mock_response.raise_for_status = MagicMock()
        
        mocker.patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response)
        
        commit_details = await client.get_commit_details("quantum-lab", "quantum-research", "abc123")
        
        assert commit_details is not None
        assert commit_details["sha"] == "abc123def456"
        assert commit_details["commit"]["author"]["name"] == "Alice Chen"
        assert commit_details["stats"]["additions"] == 150
        assert len(commit_details["files"]) == 2
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_get_contributors_success(self, mocker):
        """Test getting repository contributors."""
        client = GitHubClient(token="test_token")
        
        # Mock response - client.get() returns synchronous json()
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"login": "alicechen", "contributions": 150},
            {"login": "bobsmith", "contributions": 89},
            {"login": "charliedev", "contributions": 45}
        ]
        mock_response.raise_for_status = MagicMock()
        
        mocker.patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response)
        
        contributors = await client.get_contributors("quantum-lab", "quantum-research")
        
        assert len(contributors) == 3
        assert contributors[0]["login"] == "alicechen"
        assert contributors[0]["contributions"] == 150
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_get_user_success(self, mocker):
        """Test getting user information."""
        client = GitHubClient(token="test_token")
        
        # Mock response - client.get() returns synchronous json()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "login": "alicechen",
            "name": "Alice Chen",
            "company": "Quantum Research Lab",
            "bio": "Researcher in quantum computing and error correction",
            "followers": 250,
            "public_repos": 42
        }
        mock_response.raise_for_status = MagicMock()
        
        mocker.patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response)
        
        user = await client.get_user("alicechen")
        
        assert user is not None
        assert user["login"] == "alicechen"
        assert user["name"] == "Alice Chen"
        assert user["company"] == "Quantum Research Lab"
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_get_repository_dependencies(self, mocker):
        """Test getting repository dependencies."""
        client = GitHubClient(token="test_token")
        
        # Mock requirements.txt found
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "requirements.txt",
            "path": "requirements.txt",
            "type": "file"
        }
        
        mocker.patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response)
        
        dependencies = await client.get_repository_dependencies("quantum-lab", "quantum-research")
        
        assert "requirements.txt" in dependencies
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_analyze_commit_activity_success(self, mocker):
        """Test analyzing commit activity."""
        client = GitHubClient(token="test_token")
        
        # Track call count for different responses
        call_count = [0]
        
        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            
            if call_count[0] == 1:
                # First call for commits
                mock_response.json.return_value = [
                    {"sha": "abc123"},
                    {"sha": "def456"},
                    {"sha": "ghi789"}
                ]
            else:
                # Subsequent calls for commit details
                mock_response.json.return_value = {
                    "sha": "abc123",
                    "commit": {"author": {"name": "Alice Chen"}},
                    "stats": {"additions": 100, "deletions": 20}
                }
            
            return mock_response
        
        mocker.patch.object(client.client, "get", side_effect=mock_get)
        
        activity = await client.analyze_commit_activity("quantum-lab", "quantum-research", days=30)
        
        assert activity["active"] is True
        assert activity["commit_count"] == 3
        assert "Alice Chen" in activity["contributors"]
        assert activity["top_contributor"] == "Alice Chen"
        assert activity["total_additions"] == 300  # 100 * 3
        assert activity["total_deletions"] == 60   # 20 * 3
        
        await client.__aexit__(None, None, None)
    
    @pytest.mark.asyncio
    async def test_analyze_commit_activity_no_commits(self, mocker):
        """Test analyzing commit activity with no commits."""
        client = GitHubClient(token="test_token")
        
        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        
        mocker.patch.object(client.client, "get", new_callable=AsyncMock, return_value=mock_response)
        
        activity = await client.analyze_commit_activity("quantum-lab", "quantum-research", days=30)
        
        assert activity["active"] is False
        assert activity["commit_count"] == 0
        assert activity["contributors"] == []
        
        await client.__aexit__(None, None, None)


class TestGitHubArtifactConversion:
    """Test artifact conversion functions."""
    
    def test_repo_to_artifact(self):
        """Test converting repository to artifact format."""
        repo = {
            "id": 123456,
            "full_name": "quantum-lab/quantum-research",
            "description": "Advanced quantum computing research projects",
            "html_url": "https://github.com/quantum-lab/quantum-research",
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2025-11-08T14:20:00Z",
            "owner": {"login": "quantum-lab"},
            "stargazers_count": 1500,
            "language": "Python",
            "topics": ["quantum-computing", "error-correction", "surface-codes"]
        }
        
        artifact = repo_to_artifact(repo)
        
        assert artifact["type"] == "repo"
        assert artifact["source"] == "github"
        assert artifact["source_id"] == "123456"
        assert artifact["title"] == "quantum-lab/quantum-research"
        assert artifact["text"] == "Advanced quantum computing research projects"
        assert artifact["stars"] == 1500
        assert "quantum-computing" in artifact["topics"]
    
    def test_release_to_artifact(self):
        """Test converting release to artifact format."""
        release = {
            "id": 789012,
            "name": "v2.1.0 - Quantum Error Correction Update",
            "body": "Major improvements to surface code error correction algorithms",
            "html_url": "https://github.com/quantum-lab/quantum-research/releases/tag/v2.1.0",
            "published_at": "2025-11-01T16:45:00Z",
            "author": {"login": "alicechen"},
            "prerelease": False,
            "tag_name": "v2.1.0",
            "repo": {
                "name": "quantum-research",
                "owner": "quantum-lab",
                "topics": ["quantum-computing", "error-correction"]
            }
        }
        
        artifact = release_to_artifact(release)
        
        assert artifact["type"] == "release"
        assert artifact["source"] == "github"
        assert artifact["title"] == "v2.1.0 - Quantum Error Correction Update"
        assert artifact["author"] == "alicechen"
        assert artifact["tag_name"] == "v2.1.0"
        assert artifact["prerelease"] is False


class TestGitHubIntegration:
    """Integration tests for GitHub functionality."""
    
    def test_configuration_loading(self):
        """Test that GitHub configuration is properly loaded."""
        github_config = GitHubConfig(
            token="test_token",
            topics=["quantum-computing", "ai"],
            orgs=["openai", "google-research"],
            min_stars=50
        )
        
        sources_config = SourcesConfig(github=github_config)
        app_config = AppConfig(sources=sources_config)
        
        settings = Settings(app=app_config, queries=[])
        
        assert settings.app.sources.github.token == "test_token"
        assert "quantum-computing" in settings.app.sources.github.topics
        assert settings.app.sources.github.min_stars == 50
    
    @pytest.mark.asyncio
    async def test_fetch_github_artifacts_with_enhanced_features(self, mocker):
        """Test fetching GitHub artifacts with enhanced features."""
        github_config = GitHubConfig(
            token="test_token",
            topics=["quantum-computing"],
            orgs=["quantum-lab"],
            min_stars=10
        )
        
        sources_config = SourcesConfig(github=github_config)
        app_config = AppConfig(sources=sources_config)
        settings = Settings(app=app_config, queries=[])
        
        # Mock the GitHubClient
        mock_client = AsyncMock()
        
        # Mock repository fetch by topics (used by fetch_github_artifacts)
        mock_client.fetch_repositories_by_topics = AsyncMock(return_value=[{
            "id": 123456,
            "full_name": "quantum-lab/quantum-research",
            "description": "Quantum computing research",
            "html_url": "https://github.com/quantum-lab/quantum-research",
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2025-11-08T14:20:00Z",
            "owner": {"login": "quantum-lab"},
            "stargazers_count": 1500,
            "language": "Python",
            "topics": ["quantum-computing"]
        }])
        
        # Mock organization repos
        mock_client.get_organization_repos = AsyncMock(return_value=[])
        
        # Mock releases
        mock_client.fetch_recent_releases = AsyncMock(return_value=[{
            "id": 789012,
            "name": "v2.1.0",
            "body": "Quantum error correction improvements",
            "html_url": "https://github.com/quantum-lab/quantum-research/releases/tag/v2.1.0",
            "published_at": "2025-11-01T16:45:00Z",
            "author": {"login": "alicechen"},
            "prerelease": False,
            "tag_name": "v2.1.0",
            "repo": {
                "name": "quantum-research",
                "owner": "quantum-lab",
                "topics": ["quantum-computing"]
            }
        }])
        
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        
        mocker.patch("signal_harvester.github_client.GitHubClient", return_value=mock_client)
        
        # Pass Settings as dict
        repo_artifacts, release_artifacts = await fetch_github_artifacts(settings.model_dump())
        
        assert len(repo_artifacts) == 1
        assert len(release_artifacts) == 1
        assert repo_artifacts[0]["title"] == "quantum-lab/quantum-research"
        assert release_artifacts[0]["title"] == "v2.1.0"