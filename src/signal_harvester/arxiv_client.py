"""arXiv API client for fetching research papers."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

from .logger import get_logger

log = get_logger(__name__)

# arXiv API base URL
ARXIV_API_URL = "https://export.arxiv.org/api/query"

# Common arXiv categories for deep tech
DEFAULT_CATEGORIES = [
    "cs.LG",  # Machine Learning
    "cs.AI",  # Artificial Intelligence
    "cs.RO",  # Robotics
    "cs.CV",  # Computer Vision
    "physics.optics",  # Optics
    "quant-ph",  # Quantum Physics
    "cs.CL",  # Computation and Language
    "cs.NE",  # Neural and Evolutionary Computing
]


class ArxivClient:
    """Client for fetching papers from arXiv API."""
    
    def __init__(self, max_results: int = 50, categories: list[str] | None = None):
        self.max_results = max_results
        self.categories = categories or DEFAULT_CATEGORIES
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def __aenter__(self) -> "ArxivClient":
        return self
    
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any | None,
    ) -> None:
        await self.client.aclose()
    
    def build_query(self, query_terms: list[str] | None = None) -> str:
        """Build arXiv search query from categories and terms."""
        # Category queries
        category_queries = [f"cat:{cat}" for cat in self.categories]
        
        # Search term queries
        term_queries = []
        if query_terms:
            term_queries = [f"all:{term}" for term in query_terms]
        
        # Combine with OR
        all_queries = category_queries + term_queries
        return " OR ".join(all_queries)
    
    async def fetch_recent(self, hours: int = 24, query_terms: list[str] | None = None) -> list[dict[str, Any]]:
        """Fetch recent papers from arXiv."""
        query = self.build_query(query_terms)
        
        params: dict[str, str | int] = {
            "search_query": query,
            "start": 0,
            "max_results": self.max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending"
        }
        
        try:
            log.info("Fetching arXiv papers with query: %s", query)
            response = await self.client.get(ARXIV_API_URL, params=params)
            response.raise_for_status()
            
            papers = self.parse_xml_response(response.text)
            
            # Filter by date
            cutoff_time = datetime.now(timezone.utc).timestamp() - (hours * 3600)
            recent_papers = [
                paper for paper in papers
                if paper["published_at"] and datetime.fromisoformat(paper["published_at"]).timestamp() > cutoff_time
            ]
            
            log.info("Found %d recent arXiv papers (out of %d total)", len(recent_papers), len(papers))
            return recent_papers
            
        except Exception as e:
            log.error("Error fetching from arXiv: %s", e)
            return []
    
    def parse_xml_response(self, xml_text: str) -> list[dict[str, Any]]:
        """Parse arXiv Atom XML response."""
        try:
            root = ET.fromstring(xml_text)
            
            # Define namespaces
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom"
            }
            
            papers = []
            
            for entry in root.findall("atom:entry", ns):
                try:
                    # Extract basic info
                    title = entry.find("atom:title", ns)
                    summary = entry.find("atom:summary", ns)
                    published = entry.find("atom:published", ns)
                    updated = entry.find("atom:updated", ns)
                    id_elem = entry.find("atom:id", ns)
                    
                    # Extract authors
                    authors = []
                    for author in entry.findall("atom:author", ns):
                        name_elem = author.find("atom:name", ns)
                        if name_elem is not None and name_elem.text:
                            authors.append(name_elem.text.strip())
                    
                    # Extract categories
                    categories = []
                    for category in entry.findall("arxiv:primary_category", ns) + entry.findall("atom:category", ns):
                        term = category.get("term")
                        if term:
                            categories.append(term)
                    
                    # Extract arXiv ID from URL
                    arxiv_id = ""
                    if id_elem is not None and id_elem.text:
                        arxiv_id = id_elem.text.split("/")[-1]  # Get last part of URL
                    
                    paper = {
                        "source_id": arxiv_id,
                        "title": title.text.strip() if title is not None and title.text else "",
                        "text": summary.text.strip() if summary is not None and summary.text else "",
                        "published_at": published.text if published is not None else "",
                        "updated_at": updated.text if updated is not None else "",
                        "authors": authors,
                        "categories": categories,
                        "url": id_elem.text if id_elem is not None else "",
                    }
                    
                    papers.append(paper)
                    
                except Exception as e:
                    log.warning("Error parsing arXiv entry: %s", e)
                    continue
            
            return papers
            
        except ET.ParseError as e:
            log.error("Error parsing arXiv XML: %s", e)
            return []
    
    async def fetch_by_id(self, arxiv_id: str) -> dict[str, Any] | None:
        """Fetch a specific paper by arXiv ID."""
        params: dict[str, str | int] = {
            "id_list": arxiv_id,
            "max_results": 1
        }
        
        try:
            response = await self.client.get(ARXIV_API_URL, params=params)
            response.raise_for_status()
            
            papers = self.parse_xml_response(response.text)
            return papers[0] if papers else None
            
        except Exception as e:
            log.error("Error fetching arXiv paper %s: %s", arxiv_id, e)
            return None


async def fetch_arxiv_papers(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch arXiv papers based on configuration."""
    arxiv_config = config.get("sources", {}).get("arxiv", {})
    
    if not arxiv_config.get("enabled", True):
        log.info("arXiv source is disabled")
        return []
    
    max_results = arxiv_config.get("max_results", 50)
    categories = arxiv_config.get("categories", DEFAULT_CATEGORIES)
    query_terms = arxiv_config.get("query_terms", ["novel", "breakthrough", "state-of-the-art"])
    
    async with ArxivClient(max_results=max_results, categories=categories) as client:
        # Fetch papers from last 24 hours by default
        papers = await client.fetch_recent(hours=24, query_terms=query_terms)
        return papers
