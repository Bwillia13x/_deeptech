"""Research-focused LLM classifier for deep tech discovery.

Classifies research artifacts such as papers, preprints, code releases, and tweets about research.
Then extracts structured metadata for downstream taxonomy and scoring."""

from __future__ import annotations

import json
from typing import Any, cast

from .llm_client import LLMClient
from .logger import get_logger

log = get_logger(__name__)

RESEARCH_CLASSIFIER_PROMPT = """You are an analyst for deep-tech research discovery.
Your task is to classify research artifacts (papers, preprints, code releases, tweets about research)
and extract structured information.

**Categories:**
- Preprint: New research paper/preprint (arXiv, etc.)
- Breakthrough: Claims significant improvement or novel approach
- Lab Milestone: Achievement from research lab or institution
- Open-Source Release: Code, model, or dataset release
- Funding/Grant: Research funding announcement
- Conference/Workshop: Academic event or paper acceptance
- Other: None of the above

**Taxonomy (use these paths or create sub-paths as needed):**
ai/ml/rl, ai/ml/llms, ai/ml/cv, ai/ml/genai, ai/ml/systems, ai/ml/theory
robotics/manipulation, robotics/locomotion, robotics/humanoids
photonics/quantum, photonics/optical-computing
quantum/algorithms, quantum/hardware, quantum/error-correction
bio/genomics, bio/synbio, bio/protein-design
space/satellites, space/propulsion
materials/2d, materials/superconductors
energy/batteries, energy/fusion, energy/solar

**Extract:**
- category: from list above
- sentiment: "positive", "neutral", or "negative" (based on research claims)
- urgency: 0-3 (how time-sensitive: 3=very urgent, 0=not urgent)
- tags: array of key methods, techniques, datasets, instruments (max 8)
- topics: array of taxonomy paths that apply
- entities.people: array of person names mentioned
- entities.labs: array of lab/institution names
- entities.orgs: array of organization/company names
- reasoning: brief explanation of classification and significance

**Output strict JSON matching this schema:**
{
  "category": "string",
  "sentiment": "string",
  "urgency": integer,
  "tags": ["string", ...],
  "topics": ["string", ...],
  "entities": {
    "people": ["string", ...],
    "labs": ["string", ...],
    "orgs": ["string", ...]
  },
  "reasoning": "string"
}

Be concise but thorough. Focus on technical novelty, methods, and potential impact."""

RESEARCH_CLASSIFIER_USER_TEMPLATE = """Classify this research artifact:

Title: {title}
Text: {text}
Source: {source}
Published: {published_at}

Provide JSON output only."""


class ResearchClassifier:
    """Research artifact classifier using LLM."""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
    
    async def classify(self, artifact: dict[str, Any]) -> dict[str, Any] | None:
        """Classify a research artifact."""
        try:
            # Prepare text for classification
            title = artifact.get("title", "")
            text = artifact.get("text", "")
            source = artifact.get("source", "")
            published_at = artifact.get("published_at", "")
            
            # Combine title and text for classification
            full_text = f"{title}\n\n{text}" if title and text else (title or text)
            
            if not full_text.strip():
                log.warning("Empty text for artifact %s", artifact.get("source_id"))
                return None
            
            # Build prompts
            system_prompt = RESEARCH_CLASSIFIER_PROMPT
            user_prompt = RESEARCH_CLASSIFIER_USER_TEMPLATE.format(
                title=title,
                text=text[:2000],  # Limit text length to avoid token limits
                source=source,
                published_at=published_at
            )
            
            # Call LLM
            response = await self.llm_client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2
            )
            
            if not response:
                log.error("Empty response from LLM for artifact %s", artifact.get("source_id"))
                return None
            
            # Parse JSON response
            try:
                # Try to extract JSON from response (in case there's extra text)
                content = response.get("content", "")
                
                # Look for JSON object in response
                start_idx = content.find("{")
                end_idx = content.rfind("}")
                
                if start_idx >= 0 and end_idx > start_idx:
                    json_str = content[start_idx:end_idx + 1]
                    result: dict[str, Any] = cast(dict[str, Any], json.loads(json_str))
                else:
                    # Try to parse entire response as JSON
                    result = cast(dict[str, Any], json.loads(content))
                
                # Validate required fields
                # Ensure required fields exist with sensible defaults
                required_fields = ["category", "sentiment", "urgency", "tags", "topics", "entities", "reasoning"]
                for field in required_fields:
                    if field not in result:
                        log.warning("Missing required field %s in classification result; filling default", field)
                        if field == "tags":
                            result[field] = []
                        elif field == "topics":
                            result[field] = []
                        elif field == "entities":
                            result[field] = {"people": [], "labs": [], "orgs": []}
                        elif field == "urgency":
                            result[field] = 0
                        elif field == "reasoning":
                            result[field] = "Fallback classification via heuristic analyzer."
                        else:
                            result[field] = "other"

                # Normalize entity structure
                entities = result.get("entities") or {}
                result["entities"] = {
                    "people": list(entities.get("people", [])),
                    "labs": list(entities.get("labs", [])),
                    "orgs": list(entities.get("orgs", [])),
                }

                # Normalize tags
                if not isinstance(result.get("tags"), list):
                    result["tags"] = [str(result.get("tags", "")).strip()] if result.get("tags") else []

                # Ensure topics present; infer defaults when missing
                topics = result.get("topics") if isinstance(result.get("topics"), list) else []
                if not topics:
                    inferred_topic = self._infer_default_topic(artifact, result)
                    topics = [inferred_topic]
                else:
                    # Filter invalid topics
                    valid_topics = [t for t in topics if validate_taxonomy_path(t)]
                    if not valid_topics:
                        inferred_topic = self._infer_default_topic(artifact, result)
                        valid_topics = [inferred_topic]
                    topics = valid_topics
                result["topics"] = topics

                return result

            except json.JSONDecodeError as e:
                log.error("Error parsing JSON response: %s\nResponse: %s", e, response.get("content", ""))
                return None
                
        except Exception as e:
            log.error("Error classifying artifact: %s", e)
            return None
    
    async def classify_batch(self, artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Classify multiple artifacts."""
        results = []
        
        for artifact in artifacts:
            try:
                classification = await self.classify(artifact)
                if classification:
                    results.append({
                        "artifact": artifact,
                        "classification": classification
                    })
            except Exception as e:
                log.error("Error classifying artifact %s: %s", artifact.get("source_id"), e)
                continue
        
        return results

    def _infer_default_topic(self, artifact: dict[str, Any], classification: dict[str, Any]) -> str:
        """Infer a reasonable default taxonomy topic when LLM output is incomplete."""
        text = f"{artifact.get('title', '')} {artifact.get('text', '')}".lower()
        source = (artifact.get("source") or "").lower()
        category = (classification.get("category") or "").lower()

        keyword_topics = [
            ("quantum", "quantum/algorithms"),
            ("photon", "photonics/quantum"),
            ("robot", "robotics/manipulation"),
            ("genom", "bio/genomics"),
            ("protein", "bio/protein-design"),
            ("fusion", "energy/fusion"),
            ("battery", "energy/batteries"),
            ("satellite", "space/satellites"),
            ("optics", "photonics/optical-computing"),
        ]

        for keyword, topic in keyword_topics:
            if keyword in text:
                if validate_taxonomy_path(topic):
                    return topic

        source_defaults = {
            "arxiv": "ai/ml/theory",
            "github": "ai/ml/systems",
            "facebook": "ai/ml/genai",
            "x": "ai/ml/systems",
        }
        if source in source_defaults and validate_taxonomy_path(source_defaults[source]):
            return source_defaults[source]

        category_defaults = {
            "preprint": "ai/ml/theory",
            "open-source release": "ai/ml/systems",
            "breakthrough": "ai/ml/genai",
            "lab milestone": "robotics/locomotion",
            "funding/grant": "ai/ml/systems",
            "conference/workshop": "ai/ml/theory",
        }
        for cat, topic in category_defaults.items():
            if cat in category and validate_taxonomy_path(topic):
                return topic

        # Final fallback to a known valid path
        fallback = "ai/ml/systems"
        return fallback if validate_taxonomy_path(fallback) else "ai/ml/rl"


# Research taxonomy for validation and auto-completion
TaxonomyNode = dict[str, "TaxonomyNode"] | list[str]

RESEARCH_TAXONOMY: dict[str, TaxonomyNode] = {
    "ai": {
        "ml": ["rl", "llms", "cv", "genai", "systems", "theory", "optimization"],
        "theory": ["complexity", "learning-theory"]
    },
    "robotics": {
        "manipulation": [],
        "locomotion": [],
        "humanoids": [],
        "drones": []
    },
    "photonics": {
        "quantum": [],
        "optical-computing": [],
        "metrology": []
    },
    "quantum": {
        "algorithms": [],
        "hardware": [],
        "error-correction": [],
        "networking": []
    },
    "bio": {
        "genomics": [],
        "synbio": [],
        "protein-design": [],
        "drug-discovery": []
    },
    "space": {
        "satellites": [],
        "propulsion": [],
        "exploration": []
    },
    "materials": {
        "2d": [],
        "superconductors": [],
        "metamaterials": []
    },
    "energy": {
        "batteries": [],
        "fusion": [],
        "solar": [],
        "nuclear": []
    },
    "semiconductors": {
        "design": [],
        "fabrication": [],
        "novel-materials": []
    }
}


def validate_taxonomy_path(path: str) -> bool:
    """Validate a taxonomy path against the research taxonomy."""
    if not path or "/" not in path:
        return False
    
    parts = path.split("/")
    current: TaxonomyNode = RESEARCH_TAXONOMY
    
    for part in parts:
        if not isinstance(current, dict):
            return False
        if part not in current:
            return False
        current = current[part]
        if isinstance(current, list):
            # Leaf node - should be at end of path
            break
    
    return True


def get_all_taxonomy_paths() -> list[str]:
    """Get all valid taxonomy paths as flat list."""
    paths = []
    
    def traverse(current: TaxonomyNode, prefix: str = "") -> None:
        if isinstance(current, list):
            # Leaf level
            for item in current:
                paths.append(f"{prefix}/{item}" if prefix else item)
        else:
            # Dictionary level
            for key, value in current.items():
                new_prefix = f"{prefix}/{key}" if prefix else key
                traverse(value, new_prefix)
    
    traverse(RESEARCH_TAXONOMY)
    return paths
