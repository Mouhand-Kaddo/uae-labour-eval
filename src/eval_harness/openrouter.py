"""Thin httpx client for OpenRouter (ADR-0001, ADR-0002). It never logs headers or the key."""

from dataclasses import dataclass
from typing import Any

import httpx

BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterError(Exception):
    pass


@dataclass(frozen=True)
class ChatResponse:
    message: dict[str, Any]
    finish_reason: str | None
    usage: dict[str, Any]

    @property
    def cost(self) -> float:
        return float(self.usage["cost"])


@dataclass(frozen=True)
class ModelInfo:
    id: str
    prompt_price_usd: float
    completion_price_usd: float
    supported_parameters: frozenset[str]


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.BaseTransport | None = None,
        base_url: str = BASE_URL,
        timeout_s: float = 120.0,
    ):
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=timeout_s,
        )

    def chat(self, payload: dict[str, Any]) -> ChatResponse:
        """POST /chat/completions; returns the first choice and the raw `usage` object."""
        body = self._request("POST", "/chat/completions", json=payload)
        try:
            choice = body["choices"][0]
            usage = body["usage"]
            float(usage["cost"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise OpenRouterError(f"chat response lacks choices or usage.cost: {exc!r}") from exc
        return ChatResponse(choice["message"], choice.get("finish_reason"), usage)

    def models(self) -> dict[str, ModelInfo]:
        """Live prices and capabilities for every model, keyed by model ID."""
        body = self._request("GET", "/models")
        try:
            return {
                m["id"]: ModelInfo(
                    id=m["id"],
                    prompt_price_usd=float(m["pricing"]["prompt"]),
                    completion_price_usd=float(m["pricing"]["completion"]),
                    supported_parameters=frozenset(m.get("supported_parameters") or ()),
                )
                for m in body["data"]
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise OpenRouterError(f"unexpected models response: {exc!r}") from exc

    def key_usage(self) -> float:
        """Total USD spent on this key, from GET /key."""
        body = self._request("GET", "/key")
        try:
            return float(body["data"]["usage"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OpenRouterError(f"unexpected key response: {exc!r}") from exc

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"{method} {path} failed: {type(exc).__name__}") from None
        if response.status_code != 200:
            raise OpenRouterError(
                f"{method} {path} returned HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            body = response.json()
        except ValueError:
            raise OpenRouterError(f"{method} {path} returned non-JSON body") from None
        if not isinstance(body, dict) or "error" in body:
            raise OpenRouterError(f"{method} {path} returned an error: {str(body)[:500]}")
        return body
