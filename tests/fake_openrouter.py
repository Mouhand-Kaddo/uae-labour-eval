"""A scripted stand-in for OpenRouter, served through httpx.MockTransport."""

import json

import httpx

FAKE_KEY = "sk-or-v1-fake-key-that-must-never-leak-0123456789"

MODELS = [
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
        "id": "openai/gpt-5.6-terra",
        "pricing": {"prompt": "0.000002", "completion": "0.000012"},
        "supported_parameters": ["max_tokens", "reasoning", "tools"],
    },
]


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


class FakeOpenRouter:
    def __init__(self, chat_responses, key_usage=0.0, key_status=200):
        self.chat_responses = list(chat_responses)
        self.key_usage = key_usage
        self.key_status = key_status
        self.chat_requests = []
        self.transport = httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        path = request.url.path
        if path == "/api/v1/models":
            return httpx.Response(200, json={"data": MODELS})
        if path == "/api/v1/key":
            if self.key_status != 200:
                return httpx.Response(self.key_status, json={"error": {"message": "down"}})
            return httpx.Response(200, json={"data": {"usage": self.key_usage, "limit": None}})
        if path == "/api/v1/chat/completions":
            self.chat_requests.append(json.loads(request.content))
            return httpx.Response(200, json=self.chat_responses.pop(0))
        return httpx.Response(404)
