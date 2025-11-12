from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, List, Optional

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


class LLMClient:
    """Async wrapper for LLM analyzers to support chat interface."""
    
    def __init__(self, provider: str, model: str | None = None, temperature: float = 0.2):
        normalized_provider = (provider or "dummy").lower().strip()
        self.analyzer = get_llm_client(normalized_provider, model, temperature)
        self.provider = normalized_provider
        self.model = model
        self.temperature = temperature
    
    async def _chat_openai(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int = 1024,
    ) -> tuple[str, dict[str, Any]]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        model = self.model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        base_url = os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        # Prefer JSON responses for easier parsing when supported
        payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Retry without forcing JSON formatting for older models
            if exc.response.status_code == 400 and "response_format" in payload:
                payload.pop("response_format")
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{base_url.rstrip('/')}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                response.raise_for_status()
            else:
                raise
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("OpenAI response contained no choices")
        content = choices[0].get("message", {}).get("content", "")
        return content, data
    
    async def _chat_anthropic(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int = 1024,
    ) -> tuple[str, dict[str, Any]]:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        model = self.model or os.getenv("ANTHROPIC_MODEL") or "claude-3-5-haiku-latest"
        base_url = os.getenv("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
        url = f"{base_url.rstrip('/')}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        system_message = None
        converted_messages: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system_message = content
                continue
            anthropic_role = role if role in {"user", "assistant"} else "user"
            converted_messages.append(
                {
                    "role": anthropic_role,
                    "content": [
                        {
                            "type": "text",
                            "text": content,
                        }
                    ],
                }
            )
        if not converted_messages:
            raise RuntimeError("Anthropic chat requires at least one user message")
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": converted_messages,
        }
        if system_message:
            payload["system"] = system_message
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        content_blocks = data.get("content") or []
        text_content = "".join(
            block.get("text", "") for block in content_blocks if block.get("type") == "text"
        )
        # Normalize to OpenAI-like structure for downstream consumers
        normalized = {
            "id": data.get("id"),
            "model": data.get("model"),
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": text_content,
                    }
                }
            ],
            "raw_response": data,
        }
        return text_content, normalized
    
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
    ) -> dict[str, Any] | None:
        """Async chat interface for LLM."""
        temp = temperature if temperature is not None else self.temperature
        try:
            if self.provider == "openai":
                content, _ = await self._chat_openai(messages, temp)
                return {"content": content}
            if self.provider == "anthropic":
                content, _ = await self._chat_anthropic(messages, temp)
                return {"content": content}
        except Exception as exc:
            log.error("Error in LLM chat via provider '%s': %s", self.provider, exc)
        try:
            # Extract the last user/system messages for fallback analysis
            user_message = ""
            system_message = ""
            for msg in messages:
                if msg.get("role") == "user":
                    user_message = msg.get("content", "")
                elif msg.get("role") == "system":
                    system_message = msg.get("content", "")
            full_prompt = f"{system_message}\n\n{user_message}" if system_message else user_message
            analysis = self.analyzer.analyze_text(full_prompt)
            return {
                "content": json.dumps(
                    {
                        "category": analysis.category,
                        "sentiment": analysis.sentiment,
                        "urgency": analysis.urgency,
                        "tags": analysis.tags or [],
                        "reasoning": analysis.reasoning or "",
                    }
                )
            }
        except Exception as e:  # pragma: no cover - defensive fallback
            log.error("Error in LLM fallback analysis: %s", e)
            return None
    
    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Provider-compatible chat completion response."""
        temp = temperature if temperature is not None else self.temperature
        if self.provider == "openai":
            _, raw = await self._chat_openai(messages, temp, max_tokens=max_tokens)
            return raw
        if self.provider == "anthropic":
            _, raw = await self._chat_anthropic(messages, temp, max_tokens=max_tokens)
            return raw
        # Fallback for dummy and unsupported providers
        fallback = await self.chat(messages, temperature=temp)
        content = fallback.get("content") if fallback else ""
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content or "",
                    }
                }
            ]
        }
    
    async def analyze_artifact(self, title: str, text: str, source: str = "") -> dict[str, Any] | None:
        """Analyze a research artifact."""
        try:
            # Combine title and text
            full_text = f"{title}\n\n{text}" if title and text else (title or text)
            
            if not full_text.strip():
                return None
            
            analysis = self.analyzer.analyze_text(full_text)
            
            return {
                "category": analysis.category,
                "sentiment": analysis.sentiment,
                "urgency": analysis.urgency,
                "tags": analysis.tags or [],
                "reasoning": analysis.reasoning or ""
            }
        except Exception as e:
            log.error("Error analyzing artifact: %s", e)
            return None


def get_async_llm_client(provider: str, model: str | None = None, temperature: float = 0.2) -> LLMClient:
    """Get async LLM client wrapper."""
    return LLMClient(provider, model, temperature)
