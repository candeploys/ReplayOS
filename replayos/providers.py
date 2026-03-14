from __future__ import annotations

from dataclasses import dataclass
import json
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from .config import AppConfig


@dataclass
class ProviderResponse:
    provider: str
    model: str
    text: str
    error: str | None = None


class BaseProvider:
    name = "base"

    def generate(self, prompt: str) -> ProviderResponse:
        raise NotImplementedError


class LocalQwenProvider(BaseProvider):
    name = "local_qwen"

    def __init__(self, base_url: str, model: str, timeout_seconds: int):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt: str) -> ProviderResponse:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        url = f"{self.base_url}/api/generate"
        try:
            data = _post_json(url, payload, headers={}, timeout_seconds=self.timeout_seconds)
            text = str(data.get("response", "")).strip()
            if not text:
                return ProviderResponse(self.name, self.model, "", "Empty response from local model")
            return ProviderResponse(self.name, self.model, text)
        except Exception as exc:  # noqa: BLE001
            return ProviderResponse(self.name, self.model, "", str(exc))


class ClaudeProvider(BaseProvider):
    name = "claude_api"

    def __init__(self, api_key: str, model: str, timeout_seconds: int):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt: str) -> ProviderResponse:
        if not self.api_key:
            return ProviderResponse(self.name, self.model, "", "ANTHROPIC_API_KEY is missing")

        payload = {
            "model": self.model,
            "max_tokens": 900,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        try:
            data = _post_json(
                "https://api.anthropic.com/v1/messages",
                payload,
                headers=headers,
                timeout_seconds=self.timeout_seconds,
            )
            content = data.get("content", [])
            chunks = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    chunks.append(str(block.get("text", "")))
            text = "\n".join(chunks).strip()
            if not text:
                return ProviderResponse(self.name, self.model, "", "Empty response from Claude API")
            return ProviderResponse(self.name, self.model, text)
        except Exception as exc:  # noqa: BLE001
            return ProviderResponse(self.name, self.model, "", str(exc))


class OpenAIProvider(BaseProvider):
    name = "openai_api"

    def __init__(self, api_key: str, model: str, timeout_seconds: int):
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    def generate(self, prompt: str) -> ProviderResponse:
        if not self.api_key:
            return ProviderResponse(self.name, self.model, "", "OPENAI_API_KEY is missing")

        payload = {
            "model": self.model,
            "input": prompt,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        try:
            data = _post_json(
                "https://api.openai.com/v1/responses",
                payload,
                headers=headers,
                timeout_seconds=self.timeout_seconds,
            )
            text = ""
            if isinstance(data.get("output_text"), str):
                text = data["output_text"].strip()
            if not text:
                output = data.get("output", [])
                parts: list[str] = []
                for item in output:
                    if not isinstance(item, dict):
                        continue
                    for content in item.get("content", []):
                        if isinstance(content, dict) and content.get("type") == "output_text":
                            parts.append(str(content.get("text", "")))
                text = "\n".join(parts).strip()
            if not text:
                return ProviderResponse(self.name, self.model, "", "Empty response from OpenAI API")
            return ProviderResponse(self.name, self.model, text)
        except Exception as exc:  # noqa: BLE001
            return ProviderResponse(self.name, self.model, "", str(exc))


def build_provider(config: AppConfig) -> BaseProvider:
    provider_name = config.provider.default
    timeout_seconds = config.runtime.provider_timeout_seconds

    if provider_name == "local_qwen":
        return LocalQwenProvider(
            config.provider.local_base_url,
            config.provider.local_model,
            timeout_seconds=timeout_seconds,
        )
    if provider_name == "claude_api":
        return ClaudeProvider(
            config.anthropic_api_key,
            config.provider.claude_model,
            timeout_seconds=timeout_seconds,
        )
    if provider_name == "openai_api":
        return OpenAIProvider(
            config.openai_api_key,
            config.provider.openai_model,
            timeout_seconds=timeout_seconds,
        )
    raise ValueError(f"Unsupported provider: {provider_name}")


def _post_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    timeout_seconds: int,
    retries: int = 2,
    initial_backoff_seconds: float = 0.35,
) -> dict:
    req_headers = {"Content-Type": "application/json", **headers}
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        req = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=req_headers,
            method="POST",
        )
        try:
            with urlopen(req, timeout=timeout_seconds) as res:
                body = res.read().decode("utf-8")
                return json.loads(body)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            transient = exc.code >= 500 or exc.code in {408, 429}
            last_error = RuntimeError(f"HTTP {exc.code}: {body}")
            if transient and attempt < retries:
                sleep_seconds = initial_backoff_seconds * (2**attempt)
                time.sleep(sleep_seconds)
                continue
            raise last_error from exc
        except URLError as exc:
            last_error = RuntimeError(f"Network error: {exc.reason}")
            if attempt < retries:
                sleep_seconds = initial_backoff_seconds * (2**attempt)
                time.sleep(sleep_seconds)
                continue
            raise last_error from exc

    if last_error is not None:
        raise last_error
    raise RuntimeError("Request failed unexpectedly")
