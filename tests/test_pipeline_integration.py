"""Integration tests for the discovery pipeline with Phase 2.5 sources."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from signal_harvester.config import AppConfig, ArxivConfig, FacebookConfig, GitHubConfig, Settings, SourcesConfig
from signal_harvester.db import connect, init_db, run_migrations
from signal_harvester.pipeline_discovery import fetch_artifacts


@pytest.mark.asyncio
async def test_fetch_artifacts_github_integration(tmp_path: Path, mocker) -> None:
    """Test that fetch_artifacts correctly integrates with GitHub client."""
    
    # Setup database
    db_path = tmp_path / "pipeline_test.db"
    init_db(str(db_path))
    run_migrations(str(db_path))
    
    # Create settings with GitHub enabled
    github_config = GitHubConfig(
        token="test-token",
        topics=["quantum-computing"],
        orgs=["quantum-lab"],
        enabled=True,
    )
    sources_config = SourcesConfig(github=github_config)
    app_config = AppConfig(
        database_path=str(db_path),
        sources=sources_config,
    )
    settings = Settings(app=app_config, queries=[])
    
    # Mock the GitHubClient
    mock_client = AsyncMock()
    
    # Mock repository fetch
    mock_client.fetch_repositories_by_topics = AsyncMock(return_value=[{
        "id": 12345,
        "full_name": "quantum-lab/quantum-sdk",
        "description": "Quantum computing SDK",
        "html_url": "https://github.com/quantum-lab/quantum-sdk",
        "created_at": "2024-06-01T10:00:00Z",
        "updated_at": "2025-11-08T15:30:00Z",
        "owner": {"login": "quantum-lab"},
        "stargazers_count": 2500,
        "language": "Python",
        "topics": ["quantum-computing", "sdk"]
    }])
    
    # Mock organization repos
    mock_client.get_organization_repos = AsyncMock(return_value=[])
    
    # Mock releases
    mock_client.fetch_recent_releases = AsyncMock(return_value=[{
        "id": 67890,
        "name": "v3.0.0",
        "body": "Major release with quantum error correction",
        "html_url": "https://github.com/quantum-lab/quantum-sdk/releases/tag/v3.0.0",
        "published_at": "2025-11-05T12:00:00Z",
        "author": {"login": "drquantum"},
        "prerelease": False,
        "tag_name": "v3.0.0",
        "repo": {
            "name": "quantum-sdk",
            "owner": "quantum-lab",
            "topics": ["quantum-computing"]
        }
    }])
    
    # Setup context manager mocks
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    # Patch GitHubClient
    mocker.patch("signal_harvester.github_client.GitHubClient", return_value=mock_client)
    
    # Mock upsert_artifact within db module since it's imported locally in fetch_artifacts
    mock_upsert = mocker.patch("signal_harvester.db.upsert_artifact")
    mock_upsert.return_value = 1  # Return artifact ID
    
    # Run fetch_artifacts
    stats = await fetch_artifacts(settings)
    
    # Verify stats
    assert "sources" in stats
    assert "github" in stats["sources"]
    assert stats["sources"]["github"]["repos"] == 1
    assert stats["sources"]["github"]["releases"] == 1
    
    # Verify upsert_artifact was called correctly
    assert mock_upsert.call_count == 2  # 1 repo + 1 release
    
    # Check repo artifact call
    repo_call = [call for call in mock_upsert.call_args_list if call[1]["artifact_type"] == "repo"][0]
    assert repo_call[1]["source"] == "github"
    assert repo_call[1]["source_id"] == "12345"  # Uses repo ID
    assert repo_call[1]["title"] == "quantum-lab/quantum-sdk"
    assert "Quantum computing SDK" in repo_call[1]["text"]
    
    # Check release artifact call
    release_call = [call for call in mock_upsert.call_args_list if call[1]["artifact_type"] == "release"][0]
    assert release_call[1]["source"] == "github"
    assert release_call[1]["source_id"] == "quantum-lab/quantum-sdk:67890"  # Uses owner/repo:id format
    assert release_call[1]["title"] == "v3.0.0"
    assert "quantum error correction" in release_call[1]["text"]


@pytest.mark.asyncio
async def test_fetch_artifacts_all_sources_disabled(tmp_path: Path, mocker) -> None:
    """Test fetch_artifacts when all sources are explicitly disabled."""
    
    # Setup database
    db_path = tmp_path / "pipeline_test.db"
    init_db(str(db_path))
    run_migrations(str(db_path))
    
    # Create settings with all sources explicitly disabled
    github_config = GitHubConfig(enabled=False, token="", topics=[], orgs=[])
    arxiv_config = ArxivConfig(enabled=False)
    facebook_config = FacebookConfig(enabled=False, access_token="", pages=[], groups=[])
    
    sources_config = SourcesConfig(
        github=github_config,
        arxiv=arxiv_config,
        facebook=facebook_config,
    )
    app_config = AppConfig(
        database_path=str(db_path),
        sources=sources_config,
    )
    settings = Settings(app=app_config, queries=[])
    
    # Run fetch_artifacts
    stats = await fetch_artifacts(settings)
    
    # Should have sources dict but no entries since all disabled
    assert "sources" in stats
    assert len(stats["sources"]) == 0


@pytest.mark.asyncio
async def test_fetch_artifacts_github_disabled(tmp_path: Path) -> None:
    """Test that disabled GitHub source is skipped."""
    
    # Setup database
    db_path = tmp_path / "pipeline_test.db"
    init_db(str(db_path))
    run_migrations(str(db_path))
    
    # Create settings with GitHub disabled
    github_config = GitHubConfig(
        token="",
        topics=[],
        orgs=[],
        enabled=False,
    )
    sources_config = SourcesConfig(github=github_config)
    app_config = AppConfig(
        database_path=str(db_path),
        sources=sources_config,
    )
    settings = Settings(app=app_config, queries=[])
    
    # Run fetch_artifacts
    stats = await fetch_artifacts(settings)
    
    # Should not have GitHub in stats
    assert "github" not in stats["sources"]


@pytest.mark.asyncio
async def test_fetch_artifacts_github_error_handling(tmp_path: Path, mocker, caplog) -> None:
    """Test that GitHub fetch errors are caught and logged."""
    
    # Setup database
    db_path = tmp_path / "pipeline_test.db"
    init_db(str(db_path))
    run_migrations(str(db_path))
    
    # Create settings with GitHub enabled
    github_config = GitHubConfig(
        token="test-token",
        topics=["test"],
        orgs=[],
        enabled=True,
    )
    sources_config = SourcesConfig(github=github_config)
    app_config = AppConfig(
        database_path=str(db_path),
        sources=sources_config,
    )
    settings = Settings(app=app_config, queries=[])
    
    # Mock the GitHubClient to raise an error
    mock_client = AsyncMock()
    mock_client.fetch_repositories_by_topics = AsyncMock(side_effect=Exception("API Rate Limit"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    mocker.patch("signal_harvester.github_client.GitHubClient", return_value=mock_client)
    
    # Run fetch_artifacts
    stats = await fetch_artifacts(settings)
    
    # Should have error in stats
    assert "github" in stats["sources"]
    assert "error" in stats["sources"]["github"]
    assert "API Rate Limit" in stats["sources"]["github"]["error"]
    
    # Should have logged the error
    assert "Error fetching from GitHub" in caplog.text


@pytest.mark.asyncio
async def test_fetch_artifacts_github_with_database_storage(tmp_path: Path, mocker) -> None:
    """Test that artifacts are actually stored in the database."""
    
    # Setup database with full migrations
    db_path = tmp_path / "pipeline_test.db"
    init_db(str(db_path))
    run_migrations(str(db_path))
    
    # Create settings with GitHub enabled
    github_config = GitHubConfig(
        token="test-token",
        topics=["quantum-computing"],
        orgs=["quantum-lab"],
        enabled=True,
    )
    arxiv_config = ArxivConfig(enabled=False)
    facebook_config = FacebookConfig(enabled=False, access_token="", pages=[], groups=[])
    
    sources_config = SourcesConfig(
        github=github_config,
        arxiv=arxiv_config,
        facebook=facebook_config,
    )
    app_config = AppConfig(
        database_path=str(db_path),
        sources=sources_config,
    )
    settings = Settings(app=app_config, queries=[])
    
    # Mock the GitHubClient
    mock_client = AsyncMock()
    
    # Mock repository fetch
    mock_client.fetch_repositories_by_topics = AsyncMock(return_value=[{
        "id": 99999,
        "full_name": "test-org/test-repo",
        "description": "Test repository for integration",
        "html_url": "https://github.com/test-org/test-repo",
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-11-09T00:00:00Z",
        "owner": {"login": "test-org"},
        "stargazers_count": 100,
        "language": "Python",
        "topics": ["testing"]
    }])
    
    # Mock organization repos and releases
    mock_client.get_organization_repos = AsyncMock(return_value=[])
    mock_client.fetch_recent_releases = AsyncMock(return_value=[])
    
    # Setup context manager mocks
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    # Patch GitHubClient
    mocker.patch("signal_harvester.github_client.GitHubClient", return_value=mock_client)
    
    # Run fetch_artifacts - this should actually write to the database
    stats = await fetch_artifacts(settings)
    
    # Verify stats
    assert "sources" in stats
    assert "github" in stats["sources"]
    assert stats["sources"]["github"]["repos"] == 1
    
    # Verify database contains the artifact
    conn = connect(str(db_path))
    cursor = conn.cursor()
    
    # Check artifact was inserted
    cursor.execute("SELECT * FROM artifacts WHERE source = 'github' AND type = 'repo'")
    rows = cursor.fetchall()
    assert len(rows) == 1
    
    artifact = dict(rows[0])
    assert artifact["source_id"] == "99999"
    assert artifact["title"] == "test-org/test-repo"
    assert "Test repository" in artifact["text"]
    assert artifact["url"] == "https://github.com/test-org/test-repo"
    
    conn.close()
    """Test that fetch_artifacts correctly integrates with Facebook client."""
    
    # Setup database
    db_path = tmp_path / "pipeline_test.db"
    init_db(str(db_path))
    run_migrations(str(db_path))
    
    # Create settings with Facebook enabled, other sources disabled
    facebook_config = FacebookConfig(
        access_token="test-token",
        pages=["testpage"],
        groups=[],
        enabled=True,
    )
    github_config = GitHubConfig(enabled=False, token="", topics=[], orgs=[])
    arxiv_config = ArxivConfig(enabled=False)
    
    sources_config = SourcesConfig(
        facebook=facebook_config,
        github=github_config,
        arxiv=arxiv_config,
    )
    app_config = AppConfig(
        database_path=str(db_path),
        sources=sources_config,
    )
    settings = Settings(app=app_config, queries=[])
    
    # Mock fetch_facebook_artifacts
    mock_artifacts = [{
        "type": "page_post",
        "source": "facebook",
        "source_id": "testpage_12345",
        "title": "Test Post",
        "text": "This is a test post about AI research",
        "url": "https://facebook.com/testpage/posts/12345",
        "published_at": "2025-11-08T10:00:00Z",
        "author": "Test Page",
        "likes": 100,
        "shares": 50,
        "comments": 25,
    }]
    
    mocker.patch(
        "signal_harvester.facebook_client.fetch_facebook_artifacts",
        new_callable=AsyncMock,
        return_value=mock_artifacts,
    )
    
    # Mock upsert_artifact
    mock_upsert = mocker.patch("signal_harvester.db.upsert_artifact")
    mock_upsert.return_value = 1
    
    # Run fetch_artifacts
    stats = await fetch_artifacts(settings)
    
    # Verify stats
    assert "sources" in stats
    assert "facebook" in stats["sources"]
    assert stats["sources"]["facebook"]["inserted"] == 1
    assert stats["sources"]["facebook"]["seen"] == 1
    
    # Verify upsert_artifact was called
    assert mock_upsert.call_count == 1
    call_args = mock_upsert.call_args[1]
    assert call_args["artifact_type"] == "page_post"
    assert call_args["source"] == "facebook"
    assert call_args["source_id"] == "testpage_12345"
    assert "AI research" in call_args["text"]
