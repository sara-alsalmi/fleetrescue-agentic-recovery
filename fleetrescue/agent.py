from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from threading import Event
from time import monotonic
from typing import Any, Callable, Protocol

from dotenv import load_dotenv

from .evaluator import EvaluationResult, Evaluator
from .models import RobotMode
from .tools import RecoveryTools


SYSTEM_PROMPT = """You are FleetRescue's bounded warehouse recovery agent.
Investigate using tools. Do not assume the incident type. A passage reservation may be released only when
the passage is physically empty and its owner has sufficient inactivity evidence; the tool enforces this.
Preserve healthy robots and legitimate reservations. If an inactive robot occupies the passage, escalate.
After any repair, use observe_progress and require actual new deliveries without safety violations.
Keep explanations short. Never claim success based only on an action returning ok."""


class Provider(Protocol):
    name: str
    model: str

    def create(self, *, messages: list[dict[str, Any]], tools: list[dict[str, object]],
               max_tokens: int) -> Any: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        load_dotenv()
        model = os.getenv("FLEETRESCUE_MODEL", "").strip()
        if not model:
            raise RuntimeError("FLEETRESCUE_MODEL is required; no model ID is guessed")
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required for a live run")
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("Install requirements before a live run") from exc
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def create(self, *, messages: list[dict[str, Any]], tools: list[dict[str, object]], max_tokens: int) -> Any:
        return self._client.messages.create(model=self.model, system=SYSTEM_PROMPT, messages=messages,
                                            tools=tools, max_tokens=max_tokens,
                                            thinking={"type": "between_tools"},
                                            tool_choice={"type": "auto"})


@dataclass
class AgentLimits:
    max_model_calls: int = 8
    max_tool_calls: int = 14
    max_output_tokens_per_call: int = 700
    max_input_tokens: int = 60_000
    max_output_tokens: int = 5_600
    max_retries: int = 1
    wall_clock_seconds: float = 40.0


@dataclass
class AgentRun:
    status: str
    summary: str
    trace: list[dict[str, object]] = field(default_factory=list)
    evaluation: EvaluationResult | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None


def _block_value(block: Any, name: str, default: Any = None) -> Any:
    return getattr(block, name, block.get(name, default) if isinstance(block, dict) else default)


def _block_payload(block: Any) -> dict[str, object] | None:
    if isinstance(block, dict):
        return dict(block)
    model_dump = getattr(block, "model_dump", None)
    if callable(model_dump):
        return dict(model_dump(mode="json", exclude_none=True))
    return None


def _provider_error_diagnostic(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    anthropic_type = type(exc).__name__
    reason = "provider request failed"
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            anthropic_type = str(error.get("type") or anthropic_type)
            reason = str(error.get("message") or reason)
    reason = re.sub(r"sk-ant-[A-Za-z0-9_-]+", "[REDACTED]", reason)
    reason = re.sub(r"(?i)(authorization\s*[:=]?\s*bearer\s+)\S+", r"\1[REDACTED]", reason)
    reason = re.sub(r"(?i)(api[-_ ]?key\s*[:=]\s*)\S+", r"\1[REDACTED]", reason)
    reason = " ".join(reason.split())[:300]
    return f"http_status={status or 'unknown'}; anthropic_error_type={anthropic_type}; reason={reason}"


class RecoveryAgent:
    def __init__(self, tools: RecoveryTools, provider: Provider, limits: AgentLimits | None = None,
                 activity: Callable[[dict[str, object]], None] | None = None):
        self.tools = tools
        self.provider = provider
        self.limits = limits or AgentLimits()
        self.activity = activity or (lambda _: None)

    def run(self, cancel: Event | None = None) -> AgentRun:
        start = monotonic()
        before = self.tools.engine.total_deliveries
        healthy = {rid for rid, r in self.tools.engine.robots.items() if r.mode == RobotMode.ACTIVE}
        messages: list[dict[str, Any]] = [{"role": "user", "content":
            "Deliveries appear stalled. Investigate, take only permitted actions, and verify the result."}]
        trace: list[dict[str, object]] = []
        model_calls = api_attempts = tool_calls = retries = input_tokens = output_tokens = 0
        repaired = observed_after_repair = False
        correction_attempts = 0
        try:
            while api_attempts < self.limits.max_model_calls and tool_calls < self.limits.max_tool_calls:
                if cancel and cancel.is_set():
                    return AgentRun("provider-interrupted", "Run cancelled", trace)
                if monotonic() - start > self.limits.wall_clock_seconds:
                    return AgentRun("provider-interrupted", "Wall-clock limit reached", trace)
                remaining_output = self.limits.max_output_tokens - output_tokens
                if remaining_output <= 0 or input_tokens >= self.limits.max_input_tokens:
                    break
                request_max_tokens = min(self.limits.max_output_tokens_per_call, remaining_output)
                api_attempts += 1
                try:
                    response = self.provider.create(messages=messages, tools=self.tools.definitions(),
                                                    max_tokens=request_max_tokens)
                except Exception as exc:
                    if retries < self.limits.max_retries:
                        retries += 1
                        continue
                    return AgentRun("provider-interrupted", "Provider call failed", trace,
                                    error=_provider_error_diagnostic(exc))
                model_calls += 1
                usage = getattr(response, "usage", None)
                input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
                output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
                if (input_tokens > self.limits.max_input_tokens
                        or output_tokens > self.limits.max_output_tokens):
                    return AgentRun("provider-interrupted", "Token limit reached", trace,
                                    input_tokens=input_tokens, output_tokens=output_tokens)
                content = getattr(response, "content", [])
                assistant_content: list[dict[str, object]] = []
                tool_results: list[dict[str, object]] = []
                text_parts: list[str] = []
                for block in content:
                    block_type = _block_value(block, "type")
                    payload = _block_payload(block)
                    if block_type in {"thinking", "redacted_thinking"}:
                        if payload:
                            assistant_content.append(payload)
                        continue
                    if block_type == "text":
                        text_value = str(_block_value(block, "text", ""))
                        text_parts.append(text_value)
                        assistant_content.append({"type": "text", "text": text_value})
                    elif block_type == "tool_use":
                        if tool_calls >= self.limits.max_tool_calls:
                            break
                        name = str(_block_value(block, "name"))
                        args = dict(_block_value(block, "input", {}) or {})
                        tool_id = str(_block_value(block, "id", f"tool-{tool_calls}"))
                        result = self.tools.call(name, args)
                        tool_calls += 1
                        if name in {"release_reservation", "quarantine_robot"} and result.get("ok"):
                            repaired = True
                        if name == "observe_progress" and repaired:
                            observed_after_repair = True
                        item = {"call": tool_calls, "tool": name, "args": args, "result": result}
                        trace.append(item)
                        self.activity(item)
                        assistant_content.append({"type": "tool_use", "id": tool_id, "name": name, "input": args})
                        tool_results.append({"type": "tool_result", "tool_use_id": tool_id, "content": str(result)[:1600]})
                messages.append({"role": "assistant", "content": assistant_content})
                if tool_results:
                    messages.append({"role": "user", "content": tool_results})
                    continue
                # A prose stop cannot bypass independent verification.
                if repaired and not observed_after_repair:
                    messages.append({"role": "user", "content": "A repair was attempted. Use observe_progress before concluding."})
                    continue
                if repaired and observed_after_repair and not self.tools.engine.escalated:
                    preliminary = Evaluator().evaluate(
                        self.tools.engine, deliveries_before=before, healthy_before=healthy,
                        provider=self.provider.name, model=self.provider.model,
                        usage=(input_tokens, output_tokens), started_at=start, advance=False,
                    )
                    if preliminary.outcome != "complete" and correction_attempts < 1:
                        correction_attempts += 1
                        observed_after_repair = False
                        messages.append({"role": "user", "content":
                            "Independent verification is incomplete: no verified delivery progress or a preservation/safety check failed. "
                            "You have one correction attempt within the existing limits. Inspect, act only if safe, then observe progress."})
                        continue
                break
            evaluation = Evaluator().evaluate(
                self.tools.engine, deliveries_before=before, healthy_before=healthy,
                unsafe=any(r.position in {(5, 3), (6, 3)} and r.mode != RobotMode.ACTIVE
                           for r in self.tools.engine.robots.values()),
                provider=self.provider.name, model=self.provider.model, usage=(input_tokens, output_tokens),
                started_at=start, advance=not observed_after_repair,
            )
            summary = "Independent verification passed" if evaluation.outcome == "complete" else (
                "Escalated safely" if evaluation.outcome == "escalated" else "Recovery not verified")
            return AgentRun(evaluation.outcome, summary, trace, evaluation, input_tokens, output_tokens)
        except Exception as exc:
            return AgentRun("incomplete", "Recovery loop stopped safely", trace, error=str(exc),
                            input_tokens=input_tokens, output_tokens=output_tokens)
