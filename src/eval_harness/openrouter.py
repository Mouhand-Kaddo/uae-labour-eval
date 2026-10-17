"""Thin httpx client for OpenRouter (ADR-0001, ADR-0002). It never logs headers or the key."""

from dataclasses import dataclass
from typing import Any

import httpx

BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterError(Exception):
    pass


ROUTING_METADATA_HEADER = {"X-OpenRouter-Metadata": "enabled"}


@dataclass(frozen=True)
class ChatResponse:
    message: dict[str, Any]
    finish_reason: str | None
    usage: dict[str, Any]
    provider: str | None = None

    @property
    def cost(self) -> float:
        return float(self.usage["cost"])


@dataclass(frozen=True)
class EmbeddingResponse:
    vectors: list[list[float]]
    usage: dict[str, Any]

    @property
    def cost(self) -> float:
        return float(self.usage["cost"])


@dataclass(frozen=True)
class ModelInfo:
    """Live prices (USD per token) and capabilities. The peak prices are the highest across the
    base price and every `pricing.overrides` entry (time- or size-based surcharges)."""

    id: str
    prompt_price_usd: float
    completion_price_usd: float
    supported_parameters: frozenset[str]
    peak_prompt_price_usd: float
    peak_completion_price_usd: float

    @property
    def peak_factor(self) -> float:
        """How many times the base price a call may cost under the dearest override."""
        ratios = [
            peak / base
            for peak, base in (
                (self.peak_prompt_price_usd, self.prompt_price_usd),
                (self.peak_completion_price_usd, self.completion_price_usd),
            )
            if base > 0
        ]
        return max(ratios, default=1.0)


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
        """POST /chat/completions; returns the first choice, the raw `usage` object and the
        provider that served the call (None if OpenRouter did not say)."""
        body = self._request(
            "POST", "/chat/completions", json=payload, headers=ROUTING_METADATA_HEADER
        )
        try:
            choice = body["choices"][0]
            usage = body["usage"]
            float(usage["cost"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise OpenRouterError(f"chat response lacks choices or usage.cost: {exc!r}") from exc
        return ChatResponse(
            choice["message"], choice.get("finish_reason"), usage, _serving_provider(body)
        )

    def embed(self, model: str, texts: list[str]) -> EmbeddingResponse:
        """POST /embeddings; one vector per text, in input order, plus the raw `usage` object."""
        body = self._request("POST", "/embeddings", json={"model": model, "input": texts})
        try:
            rows = sorted(body["data"], key=lambda row: row["index"])
            vectors = [[float(x) for x in row["embedding"]] for row in rows]
            usage = body["usage"]
            float(usage["cost"])
        except (KeyError, TypeError, ValueError) as exc:
            raise OpenRouterError(f"embeddings response lacks data or usage.cost: {exc!r}") from exc
        if len(vectors) != len(texts):
            raise OpenRouterError(f"asked for {len(texts)} embeddings, got {len(vectors)}")
        return EmbeddingResponse(vectors, usage)

    def models(self) -> dict[str, ModelInfo]:
        """Live prices and capabilities for every chat model, keyed by model ID."""
        return self._model_list("/models")

    def embedding_models(self) -> dict[str, ModelInfo]:
        """Live prices for every embedding model, keyed by model ID."""
        return self._model_list("/embeddings/models")

    def _model_list(self, path: str) -> dict[str, ModelInfo]:
        body = self._request("GET", path)
        try:
            return {m["id"]: _model_info(m) for m in body["data"]}
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
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


def _model_info(model: dict[str, Any]) -> ModelInfo:
    pricing = model["pricing"]
    prompt, completion = float(pricing["prompt"]), float(pricing["completion"])
    overrides = pricing.get("overrides") or []
    if not isinstance(overrides, list):
        raise TypeError(f"{model['id']}: pricing.overrides is not a list")
    return ModelInfo(
        id=model["id"],
        prompt_price_usd=prompt,
        completion_price_usd=completion,
        supported_parameters=frozenset(model.get("supported_parameters") or ()),
        peak_prompt_price_usd=max([prompt, *(float(o.get("prompt", prompt)) for o in overrides)]),
        peak_completion_price_usd=max(
            [completion, *(float(o.get("completion", completion)) for o in overrides)]
        ),
    )


def _serving_provider(body: dict[str, Any]) -> str | None:
    """The selected endpoint's provider from `openrouter_metadata`, else a top-level `provider`."""
    metadata = body.get("openrouter_metadata")
    endpoints = metadata.get("endpoints") if isinstance(metadata, dict) else None
    available = endpoints.get("available") if isinstance(endpoints, dict) else None
    for endpoint in available if isinstance(available, list) else []:
        if (
            isinstance(endpoint, dict)
            and endpoint.get("selected") is True
            and isinstance(endpoint.get("provider"), str)
        ):
            return endpoint["provider"]
    provider = body.get("provider")
    return provider if isinstance(provider, str) else None
