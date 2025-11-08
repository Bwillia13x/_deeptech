from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import List, Optional

import httpx

from .logger import get_logger

log = get_logger(__name__)


@dataclass
class Analysis:
    category: str
    sentiment: str
    urgency: int
    tags: Optional[List[str]] = None
    reasoning: Optional[str] = None


class BaseAnalyzer:
    def analyze_text(self, text: str) -> Analysis:
        raise NotImplementedError


NEG_WORDS = {
    "down",
    "broken",
    "can't",
    "cannot",
    "won't",
    "error",
    "fail",
    "failed",
    "failing",
    "issue",
    "problem",
    "outage",
    "offline",
    "bug",
    "crash",
    "latency",
    "slow",
}
POS_WORDS = {"love", "great", "awesome", "amazing", "thanks", "thank you", "excellent", "perfect", "fantastic", "cool"}


def _contains_any(text: str, words: set[str]) -> bool:
    t = text.lower()
    return any(w in t for w in words)


class DummyAnalyzer(BaseAnalyzer):
    def analyze_text(self, text: str) -> Analysis:
        t = (text or "").strip()
        tl = t.lower()

        # Category heuristics
        if any(k in tl for k in [
            "outage", "downtime", "service down", "status page",
            "cannot connect", "can't connect", "down"
        ]):
            category = "outage"
            urgency = 5
        security_keywords = [
            "breach", "vuln", "vulnerability", "leak", "rce",
            "xss", "csrf", "zero-day", "0day", "security"
        ]
        if any(k in tl for k in security_keywords):
            category = "security"
            urgency = 4
        elif any(k in tl for k in [
            "bug", "broken", "not working", "doesn't work",
            "can't use", "error", "fail"
        ]):
            category = "bug"
            urgency = 3
        elif "?" in tl or any(k in tl for k in ["how do i", "how to", "anyone know", "help", "question"]):
            category = "question"
            urgency = 2
        elif _contains_any(tl, POS_WORDS):
            category = "praise"
            urgency = 1
        else:
            category = "other"
            urgency = 1

        # Sentiment heuristic
        if _contains_any(tl, NEG_WORDS):
            sentiment = "negative"
            urgency = max(urgency, 3)
        elif _contains_any(tl, POS_WORDS):
            sentiment = "positive"
        else:
            sentiment = "neutral"

        # Tags from hashtags and simple keywords
        tags = set()
        for m in re.findall(r"#(\w+)", t):
            tags.add(m.lower())
        for kw in ["outage", "security", "bug", "latency", "api", "login", "payment"]:
            if kw in tl:
                tags.add(kw)

        reasoning = "Heuristic analysis based on keywords and punctuation."
        return Analysis(category=category, sentiment=sentiment, urgency=urgency, tags=sorted(tags), reasoning=reasoning)


class OpenAIAnalyzer(BaseAnalyzer):
    def __init__(
        self,
        model: str | None = None,
        temperature: float = 0.0,
        api_key: str | None = None,
        base_url: str | None = None
    ):
        self.model = model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.temperature = float(temperature or 0.0)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        if not self.api_key:
            log.warning("OPENAI_API_KEY not set; falling back to DummyAnalyzer")
            raise RuntimeError("Missing OpenAI API key")

    def analyze_text(self, text: str) -> Analysis:
        prompt = {
            "role": "system",
            "content": (
                "You are a triage assistant. Classify the user text into:\n"
                "- category: one of [outage, security, bug, question, praise, other]\n"
                "- sentiment: one of [positive, neutral, negative]\n"
                "- urgency: integer 0..5 (5=critical, 0=none)\n"
                "- tags: up to 8 concise lowercase tags\n"
                "Return ONLY a JSON object with keys: category, sentiment, urgency, tags, reasoning.\n"
            ),
        }
        user = {"role": "user", "content": text.strip()[:4000]}

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [prompt, user],
            "response_format": {"type": "json_object"},
        }
        max_attempts = 3
        backoff = 1.0
        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(timeout=20.0) as client:
                    resp = client.post(url, headers=headers, json=body)
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    if attempt < max_attempts:
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                obj = json.loads(content)
                category = str(obj.get("category") or "other").lower()
                if category not in {"outage", "security", "bug", "question", "praise", "other"}:
                    category = "other"
                sentiment = str(obj.get("sentiment") or "neutral").lower()
                if sentiment not in {"positive", "neutral", "negative"}:
                    sentiment = "neutral"
                urgency = int(obj.get("urgency") or 0)
                tags = obj.get("tags") or []
                if not isinstance(tags, list):
                    tags = []
                tags = [str(t).strip().lower() for t in tags if str(t).strip()]
                reasoning = str(obj.get("reasoning") or "")[:400]
                return Analysis(category=category, sentiment=sentiment, urgency=urgency, tags=tags, reasoning=reasoning)
            except Exception as e:
                log.error("OpenAI analyze attempt %d failed: %s", attempt, e)
                if attempt < max_attempts:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                return DummyAnalyzer().analyze_text(text)
        return DummyAnalyzer().analyze_text(text)  # Should never reach here, but satisfies mypy


class AnthropicAnalyzer(BaseAnalyzer):
    def __init__(self, model: Optional[str] = None, temperature: float = 0.0, api_key: Optional[str] = None):
        self.model = model or os.getenv("ANTHROPIC_MODEL") or "claude-3-5-haiku-latest"
        self.temperature = float(temperature or 0.0)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            log.warning("ANTHROPIC_API_KEY not set; falling back to DummyAnalyzer")
            raise RuntimeError("Missing Anthropic API key")

    def analyze_text(self, text: str) -> Analysis:
        # Use HTTP API to avoid hard dependency
        url = "https://api.anthropic.com/v1/messages"
        headers: dict[str, str] = {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        sys = (
            "Classify the user text into a JSON object {category, sentiment, urgency, tags, reasoning}. "
            "category in [outage, security, bug, question, praise, other], sentiment in [positive, neutral, negative], "
            "urgency integer 0..5, tags array (<=8). Return ONLY JSON."
        )
        body = {
            "model": self.model,
            "max_tokens": 256,
            "temperature": self.temperature,
            "system": sys,
            "messages": [{"role": "user", "content": text.strip()[:4000]}],
        }
        max_attempts = 3
        backoff = 1.0
        for attempt in range(1, max_attempts + 1):
            try:
                with httpx.Client(timeout=20.0) as client:
                    resp = client.post(url, headers=headers, json=body)
                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    if attempt < max_attempts:
                        time.sleep(backoff)
                        backoff *= 2
                        continue
                resp.raise_for_status()
                data = resp.json()
                # Messages API returns content as list of blocks
                content_blocks = data.get("content") or []
                content_text = ""
                for b in content_blocks:
                    if b.get("type") == "text":
                        content_text += b.get("text") or ""
                obj = json.loads(content_text)
                category = str(obj.get("category") or "other").lower()
                if category not in {"outage", "security", "bug", "question", "praise", "other"}:
                    category = "other"
                sentiment = str(obj.get("sentiment") or "neutral").lower()
                if sentiment not in {"positive", "neutral", "negative"}:
                    sentiment = "neutral"
                urgency = int(obj.get("urgency") or 0)
                tags = obj.get("tags") or []
                if not isinstance(tags, list):
                    tags = []
                tags = [str(t).strip().lower() for t in tags if str(t).strip()]
                reasoning = str(obj.get("reasoning") or "")[:400]
                return Analysis(category=category, sentiment=sentiment, urgency=urgency, tags=tags, reasoning=reasoning)
            except Exception as e:
                log.error("Anthropic analyze attempt %d failed: %s", attempt, e)
                if attempt < max_attempts:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                return DummyAnalyzer().analyze_text(text)
        return DummyAnalyzer().analyze_text(text)  # Should never reach here, but satisfies mypy


def get_llm_client(provider: Optional[str], model: Optional[str], temperature: float = 0.0) -> BaseAnalyzer:
    p = (provider or "dummy").lower().strip()
    if p == "openai":
        try:
            return OpenAIAnalyzer(model=model, temperature=temperature)
        except Exception:
            return DummyAnalyzer()
    if p == "anthropic":
        try:
            return AnthropicAnalyzer(model=model, temperature=temperature)
        except Exception:
            return DummyAnalyzer()
    if p == "dummy":
        return DummyAnalyzer()
    # Placeholder for other providers like Ollama
    log.warning("Unknown LLM provider '%s'; using DummyAnalyzer", provider)
    return DummyAnalyzer()
