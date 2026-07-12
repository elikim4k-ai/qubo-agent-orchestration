"""Model clients for the harness.

Two implementations of one contract:
  * OpenAICompatClient — a real Hermes checkpoint behind any OpenAI-compatible
    endpoint (vLLM, llama.cpp, ollama, Nous API). Pin the checkpoint hash.
  * MockModelClient — a deterministic simulated agent for tests and for
    generating realistic telemetry without GPUs. Skill per category controls
    success probability; a malformed-call rate exercises the repair path.
"""
from __future__ import annotations

import json
import random
import urllib.request
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    name: str
    arguments: str  # raw JSON string — may be malformed; harness validates


@dataclass
class ModelResponse:
    text: str = ""
    tool_call: ToolCall | None = None
    tokens_prompt: int = 0
    tokens_completion: int = 0


def _est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockModelClient:
    """Scripted Hermes stand-in. Reads one linked note, then submits a result
    via complete_task; quality is drawn from per-category skill."""

    def __init__(self, skill: dict[str, float], seed: int = 0,
                 malformed_rate: float = 0.05, checkpoint: str = "mock:deterministic"):
        self.skill = skill
        self.rng = random.Random(seed)
        self.malformed_rate = malformed_rate
        self.checkpoint = checkpoint
        self._step = 0

    def start_task(self) -> None:
        self._step = 0

    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> ModelResponse:
        prompt_tokens = _est_tokens(system + json.dumps(messages) + json.dumps(tools))
        last = messages[-1]["content"] if messages else ""
        self._step += 1

        if "malformed" not in last and self.rng.random() < self.malformed_rate:
            # broken JSON arguments -> harness must catch and issue ONE repair
            call = ToolCall("complete_task", '{"result": "unterminated')
            return ModelResponse(tool_call=call, tokens_prompt=prompt_tokens,
                                 tokens_completion=12)
        if "repair" in last.lower():
            call = ToolCall("complete_task", json.dumps({"result": "repaired submission"}))
            return ModelResponse(tool_call=call, tokens_prompt=prompt_tokens,
                                 tokens_completion=18)
        if self._step == 1 and "[[" in last:
            # follow the first wiki-link, as a real agent pulls context
            name = last.split("[[", 1)[1].split("]]", 1)[0].split("|")[0]
            call = ToolCall("read_note", json.dumps({"name": name}))
            return ModelResponse(tool_call=call, tokens_prompt=prompt_tokens,
                                 tokens_completion=15)
        call = ToolCall("complete_task", json.dumps({"result": f"done at step {self._step}"}))
        return ModelResponse(tool_call=call, tokens_prompt=prompt_tokens,
                             tokens_completion=25)

    def task_succeeds(self, category: str) -> bool:
        return self.rng.random() < self.skill.get(category, 0.5)


class OpenAICompatClient:
    """Minimal chat-completions client (no SDK dependency). The endpoint hosts
    the pinned Hermes checkpoint; `checkpoint` goes into every telemetry event."""

    def __init__(self, base_url: str, model: str, checkpoint: str,
                 api_key: str | None = None, timeout_s: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.checkpoint = checkpoint
        self.api_key = api_key
        self.timeout_s = timeout_s

    def start_task(self) -> None:
        pass

    def complete(self, system: str, messages: list[dict], tools: list[dict]) -> ModelResponse:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "tools": [{"type": "function", "function": t} for t in tools],
        }
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        choice = data["choices"][0]["message"]
        usage = data.get("usage", {})
        tool_call = None
        if choice.get("tool_calls"):
            fn = choice["tool_calls"][0]["function"]
            tool_call = ToolCall(fn["name"], fn.get("arguments", "{}"))
        return ModelResponse(
            text=choice.get("content") or "",
            tool_call=tool_call,
            tokens_prompt=usage.get("prompt_tokens", 0),
            tokens_completion=usage.get("completion_tokens", 0),
        )
