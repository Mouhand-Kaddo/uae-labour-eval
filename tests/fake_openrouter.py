"""A scripted stand-in for OpenRouter, served through httpx.MockTransport."""

import json
import re
from typing import Any

import httpx

FAKE_KEY = "sk-or-v1-fake-key-that-must-never-leak-0123456789"

MODELS: list[dict[str, Any]] = [
    {
        "id": "anthropic/claude-haiku-5.5",
        "pricing": {"prompt": "0.0000001", "completion": "0.0000005"},
        "supported_parameters": ["max_tokens", "reasoning", "tools", "tool_choice"],
    },
    {
        "id": "qwen/qwen3.8-flash",
        "pricing": {"prompt": "0.00000015", "completion": "0.00000047"},
        "supported_parameters": ["max_tokens", "reasoning", "temperature", "tools"],
    },
    {
        "id": "deepseek/deepseek-v4.1-flash",
        "pricing": {
            "prompt": "0.00000015",
            "completion": "0.0000006",
            "overrides": [
                {"utc_days": ["saturday"], "prompt": "0.00000015", "completion": "0.0000006"},
                {
                    "utc_days": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                    "utc_start": 100,
                    "utc_end": 400,
                    "prompt": "0.0000003",
                    "completion": "0.0000012",
                },
            ],
        },
        "supported_parameters": ["max_tokens", "reasoning", "temperature", "tools", "tool_choice"],
    },
    {
        "id": "openai/gpt-5.6-terra",
        "pricing": {"prompt": "0.000002", "completion": "0.000012"},
        "supported_parameters": [
            "max_tokens",
            "reasoning",
            "response_format",
            "structured_outputs",
            "tools",
        ],
    },
]

ENDPOINTS = {
    "deepseek/deepseek-v4.1-flash": [
        {
            "tag": "deepseek",
            "pricing": MODELS[2]["pricing"],
            "supported_parameters": MODELS[2]["supported_parameters"],
        },
        {
            "tag": "deepinfra/fp8",
            "pricing": {"prompt": "0.000001", "completion": "0.000004"},
            "supported_parameters": ["max_tokens", "reasoning", "tools"],
        },
        {
            "tag": "deepinfra/fp8/priority",
            "pricing": {"prompt": "0.00001", "completion": "0.00004"},
            "supported_parameters": ["max_tokens", "reasoning", "tools"],
        },
    ]
}

EMBEDDING_PRICE = "0.00000001"

CONCEPTS = {
    "probation": {"probation", "التجربة"},
    "leave": {"leave", "إجازة"},
    "gratuity": {"gratuity", "مكافأة"},
    "notice": {"notice", "warning", "الإنذار"},
    "wage": {"wage", "الأجر"},
}


def fake_embedding(text):
    """A deterministic stand-in for bge-m3: one dimension per concept, in either language."""
    words = re.findall(r"\w+", text.casefold())
    return [float(sum(word in terms for word in words)) for terms in CONCEPTS.values()]


def usage(cost, prompt_tokens=900, completion_tokens=60, cached_tokens=0):
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "prompt_tokens_details": {"cached_tokens": cached_tokens, "cache_write_tokens": 0},
        "completion_tokens_details": {"reasoning_tokens": 0},
        "cost": cost,
    }


def tool_call_response(name, arguments, cost=0.0001, cached_tokens=0, call_id="call_1"):
    return {
        "id": "gen-1",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                },
            }
        ],
        "usage": usage(cost, cached_tokens=cached_tokens),
    }


def final_answer_response(status, refusal_reason=None, cost=0.0001, cached_tokens=0):
    return tool_call_response(
        "final_answer",
        {
            "answer": "I can't advise on whether to sue. This is not legal advice.",
            "citations": [],
            "status": status,
            "refusal_reason": refusal_reason,
        },
        cost=cost,
        cached_tokens=cached_tokens,
    )


def text_response(text, finish_reason="stop", cost=0.0001):
    return {
        "id": "gen-1",
        "choices": [
            {"finish_reason": finish_reason, "message": {"role": "assistant", "content": text}}
        ],
        "usage": usage(cost),
    }


def served_by(response, provider):
    """The response as OpenRouter returns it with `X-OpenRouter-Metadata: enabled`."""
    endpoints = [
        {"model": "some/model", "provider": "Elsewhere", "selected": False},
        {"model": "some/model", "provider": provider, "selected": True},
    ]
    return response | {"openrouter_metadata": {"endpoints": {"available": endpoints, "total": 2}}}


def embeddings_response(texts, cost):
    return {
        "data": [
            {"object": "embedding", "index": i, "embedding": fake_embedding(text)}
            for i, text in enumerate(texts)
        ],
        "model": "baai/bge-m3",
        "usage": {"prompt_tokens": 10 * len(texts), "total_tokens": 10 * len(texts), "cost": cost},
    }


class FakeOpenRouter:
    def __init__(
        self,
        chat_responses=(),
        key_usage=0.0,
        key_status=200,
        embedding_cost=0.00001,
        embedding_price=EMBEDDING_PRICE,
        models=MODELS,
    ):
        self.chat_responses = list(chat_responses)
        self.models = models
        self.embedding_price = embedding_price
        self.key_usage = key_usage
        self.key_status = key_status
        self.embedding_cost = embedding_cost
        self.chat_requests = []
        self.chat_headers = []
        self.endpoint_requests = []
        self.embedding_requests = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        path = request.url.path
        if path == "/api/v1/models":
            return httpx.Response(200, json={"data": self.models})
        if path.startswith("/api/v1/models/") and path.endswith("/endpoints"):
            model_id = path.removeprefix("/api/v1/models/").removesuffix("/endpoints")
            self.endpoint_requests.append(model_id)
            endpoints = ENDPOINTS.get(model_id, [])
            return httpx.Response(200, json={"data": {"id": model_id, "endpoints": endpoints}})
        if path == "/api/v1/key":
            if self.key_status != 200:
                return httpx.Response(self.key_status, json={"error": {"message": "down"}})
            return httpx.Response(200, json={"data": {"usage": self.key_usage, "limit": None}})
        if path == "/api/v1/chat/completions":
            self.chat_requests.append(json.loads(request.content))
            self.chat_headers.append(request.headers)
            return httpx.Response(200, json=self.chat_responses.pop(0))
        if path == "/api/v1/embeddings/models":
            pricing = {"prompt": self.embedding_price, "completion": "0"}
            return httpx.Response(200, json={"data": [{"id": "baai/bge-m3", "pricing": pricing}]})
        if path == "/api/v1/embeddings":
            body = json.loads(request.content)
            self.embedding_requests.append(body)
            return httpx.Response(200, json=embeddings_response(body["input"], self.embedding_cost))
        return httpx.Response(404)
