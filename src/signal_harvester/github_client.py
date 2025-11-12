"""GitHub API client for fetching repositories and releases."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

import httpx

from .logger import get_logger

log = get_logger(__name__)

# GitHub API base URL
GITHUB_API_URL = "https://api.github.com"

# Default topics for deep tech discovery
DEFAULT_TOPICS = [
    "quantum-computing",
    "photonics",
    "robotics",
    "foundation-models",
    "machine-learning",
    "artificial-intelligence",
    "computer-vision",
    "reinforcement-learning",
    "neural-networks",
    "deep-learning"
]

# Default organizations to monitor
DEFAULT_ORGS = [
    "openai",
    "google-research",
    "deepmind",
    "openrobotics",
    "pytorch",
    "tensorflow",
    "huggingface"
]


class GitHubClient:
    """Client for fetching repositories and releases from GitHub API."""
    
    def __init__(self, token: str | None = None, max_results: int = 50):
        self.token = token
        self.max_results = max_results
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"
        self.client = httpx.AsyncClient(timeout=30.0, headers=headers)
    
    async def __aenter__(self) -> "GitHubClient":
        return self
    
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> None:
        await self.client.aclose()
    
    async def search_repositories(self, query: str, sort: str = "updated") -> list[dict[str, Any]]:
        """Search repositories using GitHub search API."""
        params: dict[str, str | int] = {
            "q": query,
            "sort": sort,
            "order": "desc",
            "per_page": min(self.max_results, 100)  # GitHub max is 100
        }
        
        try:
            log.info("Searching GitHub repositories: %s", query)
            response = await self.client.get(f"{GITHUB_API_URL}/search/repositories", params=params)
            response.raise_for_status()
            
            data = cast(dict[str, Any], response.json())
            repos = cast(list[dict[str, Any]], data.get("items", []))

            log.info("Found %d repositories", len(repos))
            return repos
            
        except Exception as e:
            log.error("Error searching GitHub repositories: %s", e)
            return []
    
    async def get_repository(self, owner: str, repo: str) -> dict[str, Any] | None:
        """Get a specific repository."""
        try:
            response = await self.client.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}")
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except Exception as e:
            log.error("Error fetching GitHub repo %s/%s: %s", owner, repo, e)
            return None
    
    async def get_releases(self, owner: str, repo: str) -> list[dict[str, Any]]:
        """Get releases for a repository."""
        try:
            params: dict[str, str | int] = {"per_page": 50}
            response = await self.client.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}/releases", params=params)
            response.raise_for_status()
            return cast(list[dict[str, Any]], response.json())
        except Exception as e:
            log.error("Error fetching releases for %s/%s: %s", owner, repo, e)
            return []
    
    async def get_commits(self, owner: str, repo: str, since: datetime | None = None) -> list[dict[str, Any]]:
        """Get recent commits for a repository."""
        try:
            params: dict[str, str | int] = {"per_page": 50}
            if since:
                params["since"] = since.isoformat().replace("+00:00", "Z")
            
            response = await self.client.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits", params=params)
            response.raise_for_status()
            return cast(list[dict[str, Any]], response.json())
        except Exception as e:
            log.error("Error fetching commits for %s/%s: %s", owner, repo, e)
            return []
    
    async def get_commit_details(self, owner: str, repo: str, sha: str) -> dict[str, Any] | None:
        """Get detailed information about a specific commit."""
        try:
            response = await self.client.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}/commits/{sha}")
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except Exception as e:
            log.error("Error fetching commit details for %s/%s/%s: %s", owner, repo, sha, e)
            return None
    
    async def get_contributors(self, owner: str, repo: str) -> list[dict[str, Any]]:
        """Get contributors for a repository."""
        try:
            params: dict[str, str | int] = {"per_page": 100}
            response = await self.client.get(f"{GITHUB_API_URL}/repos/{owner}/{repo}/contributors", params=params)
            response.raise_for_status()
            return cast(list[dict[str, Any]], response.json())
        except Exception as e:
            log.error("Error fetching contributors for %s/%s: %s", owner, repo, e)
            return []
    
    async def get_user(self, username: str) -> dict[str, Any] | None:
        """Get user information."""
        try:
            response = await self.client.get(f"{GITHUB_API_URL}/users/{username}")
            response.raise_for_status()
            return cast(dict[str, Any], response.json())
        except Exception as e:
            log.error("Error fetching user %s: %s", username, e)
            return None
    
    async def get_repository_dependencies(self, owner: str, repo: str) -> list[str]:
        """Extract dependencies from repository (basic implementation)."""
        try:
            # Try to get package files (requirements.txt, package.json, etc.)
            dependencies = []
            
            # Check for common dependency files
            files_to_check = [
                "requirements.txt",
                "package.json", 
                "Cargo.toml",
                "go.mod",
                "pom.xml",
                "build.gradle"
            ]
            
            for file_path in files_to_check:
                try:
                    response = await self.client.get(
                        f"{GITHUB_API_URL}/repos/{owner}/{repo}/contents/{file_path}"
                    )
                    if response.status_code == 200:
                        # This is a simplified approach - in practice you'd decode the content
                        _ = response.json()
                        dependencies.append(file_path)
                except Exception:
                    continue
            
            return dependencies
        except Exception as e:
            log.error("Error fetching dependencies for %s/%s: %s", owner, repo, e)
            return []
    
    async def analyze_commit_activity(self, owner: str, repo: str, days: int = 30) -> dict[str, Any]:
        """Analyze commit activity for a repository."""
        try:
            since = datetime.now(timezone.utc) - timedelta(days=days)
            commits = await self.get_commits(owner, repo, since=since)
            
            if not commits:
                return {"active": False, "commit_count": 0, "contributors": []}
            
            # Analyze commit patterns
            contributors = {}
            total_additions = 0
            total_deletions = 0
            
            for commit in commits[:20]:  # Limit to avoid excessive API calls
                sha = commit.get("sha")
                if not sha:
                    continue
                
                details = await self.get_commit_details(owner, repo, sha)
                if not details:
                    continue
                
                author = details.get("commit", {}).get("author", {}).get("name", "Unknown")
                if author not in contributors:
                    contributors[author] = 0
                contributors[author] += 1
                
                stats = details.get("stats", {})
                total_additions += stats.get("additions", 0)
                total_deletions += stats.get("deletions", 0)
            
            top_contributor = (
                max(contributors.items(), key=lambda item: item[1])[0] if contributors else None
            )
            return {
                "active": len(commits) > 0,
                "commit_count": len(commits),
                "contributors": list(contributors.keys()),
                "top_contributor": top_contributor,
                "total_additions": total_additions,
                "total_deletions": total_deletions,
                "period_days": days,
            }
        except Exception as e:
            log.error("Error analyzing commit activity for %s/%s: %s", owner, repo, e)
            return {"active": False, "commit_count": 0, "contributors": [], "error": str(e)}
    
    async def get_organization_repos(self, org: str) -> list[dict[str, Any]]:
        """Get repositories for an organization."""
        try:
            params: dict[str, str | int] = {"type": "sources", "sort": "updated", "per_page": 50}
            response = await self.client.get(f"{GITHUB_API_URL}/orgs/{org}/repos", params=params)
            response.raise_for_status()
            return cast(list[dict[str, Any]], response.json())
        except Exception as e:
            log.error("Error fetching repos for org %s: %s", org, e)
            return []
    
    async def fetch_repositories_by_topics(self, topics: list[str], min_stars: int = 10) -> list[dict[str, Any]]:
        """Fetch repositories matching specific topics."""
        all_repos = []
        
        for topic in topics:
            query = f"topic:{topic} stars:>{min_stars}"
            repos = await self.search_repositories(query)
            all_repos.extend(repos)
        
        # Deduplicate by repo ID
        seen = set()
        unique_repos = []
        for repo in all_repos:
            repo_id = repo.get("id")
            if repo_id not in seen:
                seen.add(repo_id)
                unique_repos.append(repo)
        
        return unique_repos
    
    async def fetch_recent_releases(self, hours: int = 24) -> list[dict[str, Any]]:
        """Fetch recent releases across monitored repositories."""
        all_releases = []
        cutoff_time = datetime.now(timezone.utc).timestamp() - (hours * 3600)
        
        # Get repositories from topics
        repos = await self.fetch_repositories_by_topics(DEFAULT_TOPICS)
        
        # Also get from organizations
        for org in DEFAULT_ORGS:
            org_repos = await self.get_organization_repos(org)
            repos.extend(org_repos)
        
        # Deduplicate
        seen = set()
        unique_repos = []
        for repo in repos:
            repo_id = repo.get("id")
            if repo_id not in seen:
                seen.add(repo_id)
                unique_repos.append(repo)
        
        # Fetch releases for each repo
        for repo in unique_repos[:20]:  # Limit to avoid rate limits
            owner = repo.get("owner", {}).get("login")
            repo_name = repo.get("name")
            
            if not owner or not repo_name:
                continue
            
            releases = await self.get_releases(owner, repo_name)
            
            for release in releases:
                published_at = release.get("published_at")
                if not published_at:
                    continue
                
                # Check if release is recent
                try:
                    pub_time = datetime.fromisoformat(published_at.replace("Z", "+00:00")).timestamp()
                    if pub_time > cutoff_time:
                        # Enrich release with repo info
                        release["repo"] = {
                            "name": repo_name,
                            "owner": owner,
                            "description": repo.get("description"),
                            "topics": repo.get("topics", []),
                            "stars": repo.get("stargazers_count", 0),
                            "language": repo.get("language")
                        }
                        all_releases.append(release)
                except Exception as e:
                    log.warning("Error parsing release date %s: %s", published_at, e)
                    continue
        
        log.info("Found %d recent releases", len(all_releases))
        return all_releases


def repo_to_artifact(repo: dict[str, Any]) -> dict[str, Any]:
    """Convert GitHub repository to artifact format."""
    return {
        "type": "repo",
        "source": "github",
        "source_id": str(repo.get("id")),
        "title": repo.get("full_name", ""),
        "text": repo.get("description", ""),
        "url": repo.get("html_url", ""),
        "published_at": repo.get("created_at", ""),
        "updated_at": repo.get("updated_at", ""),
        "author": repo.get("owner", {}).get("login", ""),
        "stars": repo.get("stargazers_count", 0),
        "language": repo.get("language", ""),
        "topics": repo.get("topics", []),
        "raw_json": str(repo)
    }


def release_to_artifact(release: dict[str, Any]) -> dict[str, Any]:
    """Convert GitHub release to artifact format."""
    repo = release.get("repo", {})
    return {
        "type": "release",
        "source": "github",
        "source_id": f"{repo.get('owner', '')}/{repo.get('name', '')}:{release.get('id', '')}",
        "title": release.get("name", ""),
        "text": release.get("body", ""),
        "url": release.get("html_url", ""),
        "published_at": release.get("published_at", ""),
        "author": release.get("author", {}).get("login", ""),
        "repo_name": repo.get("name", ""),
        "repo_owner": repo.get("owner", ""),
        "tag_name": release.get("tag_name", ""),
        "prerelease": release.get("prerelease", False),
        "raw_json": str(release)
    }


async def fetch_github_artifacts(config: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Fetch GitHub repositories and releases based on configuration."""
    github_config = config.get("sources", {}).get("github", {})
    
    if not github_config.get("enabled", True):
        log.info("GitHub source is disabled")
        return [], []
    
    token = github_config.get("token")
    max_results = github_config.get("max_results", 50)
    topics = github_config.get("topics", DEFAULT_TOPICS)
    orgs = github_config.get("orgs", DEFAULT_ORGS)
    min_stars = github_config.get("min_stars", 10)
    
    async with GitHubClient(token=token, max_results=max_results) as client:
        # Fetch repositories by topics
        repos = await client.fetch_repositories_by_topics(topics, min_stars)
        
        # Also fetch from organizations
        for org in orgs:
            org_repos = await client.get_organization_repos(org)
            repos.extend(org_repos)
        
        # Deduplicate
        seen = set()
        unique_repos = []
        for repo in repos:
            repo_id = repo.get("id")
            if repo_id not in seen:
                seen.add(repo_id)
                unique_repos.append(repo)
        
        # Convert to artifacts
        repo_artifacts = [repo_to_artifact(repo) for repo in unique_repos[:max_results]]
        
        # Fetch recent releases
        releases = await client.fetch_recent_releases(hours=24)
        release_artifacts = [release_to_artifact(release) for release in releases]
        
        log.info("GitHub fetch complete: %d repos, %d releases", len(repo_artifacts), len(release_artifacts))
        return repo_artifacts, release_artifacts
