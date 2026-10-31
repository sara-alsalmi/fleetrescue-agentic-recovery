"""One-shot paid Anthropic DEV smoke test.

Planning is offline. A live run requires an explicit execution flag and refuses
to start if its conservative estimated cost exceeds the approved ceiling.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fleetrescue.agent import AgentLimits, AnthropicProvider, Provider, RecoveryAgent, SYSTEM_PROMPT
from fleetrescue.scenarios import make_scenario
from fleetrescue.tools import RecoveryTools


EXPECTED_MODEL = "claude-sonnet-5-5"
INPUT_RATE_PER_MILLION_USD = 2.0
OUTPUT_RATE_PER_MILLION_USD = 10.0
REGIONAL_PRICE_MULTIPLIER = 1.1
MAX_INPUT_TOKENS = 60_000
MAX_MODEL_CALLS = 8
MAX_OUTPUT_TOKENS_PER_CALL = 700
ESTIMATED_MAX_OUTPUT_TOKENS = MAX_MODEL_CALLS * MAX_OUTPUT_TOKENS_PER_CALL
APPROVED_COST_CEILING_USD = 0.20
REQUEST_OVERHEAD_TOKEN_ALLOWANCE = 1_024


def estimated_cost(input_tokens: int, output_tokens: int) -> float:
    base = (
        input_tokens * INPUT_RATE_PER_MILLION_USD
        + output_tokens * OUTPUT_RATE_PER_MILLION_USD
    ) / 1_000_000
    return base * REGIONAL_PRICE_MULTIPLIER


def conservative_input_estimate(
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, object]],
    max_tokens: int,
) -> int:
    """Conservative local estimate: one token per UTF-8 byte plus API overhead."""
    payload = {
        "model": model,
        "system": SYSTEM_PROMPT,
        "messages": messages,
        "tools": tools,
        "max_tokens": max_tokens,
        "thinking": {"type": "between_tools"},
        "tool_choice": {"type": "auto"},
    }
    serialized_bytes = len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return serialized_bytes + REQUEST_OVERHEAD_TOKEN_ALLOWANCE


class BudgetedProvider:
    """Reserve worst-case tokens and cost before every delegated API request."""

    name = "anthropic"

    def __init__(self, delegate: Provider):
        self.delegate = delegate
        self.model = delegate.model
        self.reserved_input_tokens = 0
        self.reserved_output_tokens = 0
        self.api_requests = 0

    def create(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, object]],
        max_tokens: int,
    ) -> Any:
        next_input = conservative_input_estimate(self.model, messages, tools, max_tokens)
        projected_input = self.reserved_input_tokens + next_input
        projected_output = self.reserved_output_tokens + max_tokens
        projected_cost = estimated_cost(projected_input, projected_output)
        if projected_input > MAX_INPUT_TOKENS:
            raise RuntimeError("DEV input-token limit would be exceeded")
        if projected_output > ESTIMATED_MAX_OUTPUT_TOKENS:
            raise RuntimeError("DEV output-token limit would be exceeded")
        if projected_cost > APPROVED_COST_CEILING_USD:
            raise RuntimeError("DEV cost ceiling would be exceeded")

        # Reserve before delegating so failed/retried requests consume the same budget.
        self.reserved_input_tokens = projected_input
        self.reserved_output_tokens = projected_output
        self.api_requests += 1
        return self.delegate.create(messages=messages, tools=tools, max_tokens=max_tokens)


def plan() -> dict[str, object]:
    estimate = estimated_cost(MAX_INPUT_TOKENS, ESTIMATED_MAX_OUTPUT_TOKENS)
    return {
        "mode": "plan-only",
        "provider": "anthropic",
        "required_model_id": EXPECTED_MODEL,
        "scenario": "recoverable",
        "maximum_model_calls": MAX_MODEL_CALLS,
        "maximum_tool_calls": 14,
        "maximum_output_tokens": ESTIMATED_MAX_OUTPUT_TOKENS,
        "maximum_estimated_input_tokens": MAX_INPUT_TOKENS,
        "estimated_cost_usd": round(estimate, 6),
        "approved_cost_ceiling_usd": APPROVED_COST_CEILING_USD,
        "paid_api_calls_executed": 0,
    }


def execute() -> int:
    smoke_plan = plan()
    if float(smoke_plan["estimated_cost_usd"]) > APPROVED_COST_CEILING_USD:
        raise RuntimeError("Estimated cost exceeds the approved DEV ceiling")

    live_provider = AnthropicProvider()
    if live_provider.model != EXPECTED_MODEL:
        raise RuntimeError(
            f"Configured model must be {EXPECTED_MODEL}; refusing to use an unpriced model"
        )
    provider = BudgetedProvider(live_provider)

    engine = make_scenario("recoverable")
    limits = AgentLimits(
        max_model_calls=MAX_MODEL_CALLS,
        max_tool_calls=14,
        max_output_tokens_per_call=MAX_OUTPUT_TOKENS_PER_CALL,
        max_input_tokens=MAX_INPUT_TOKENS,
        max_output_tokens=ESTIMATED_MAX_OUTPUT_TOKENS,
        max_retries=1,
        wall_clock_seconds=40.0,
    )
    run = RecoveryAgent(RecoveryTools(engine), provider, limits=limits).run()
    actual_cost = estimated_cost(run.input_tokens, run.output_tokens)
    report = {
        "provider": provider.name,
        "model_id": provider.model,
        "scenario": "recoverable",
        "status": run.status,
        "summary": run.summary,
        "tool_calls": run.trace,
        "actions": list(engine.action_history),
        "verification": run.evaluation.as_dict() if run.evaluation else None,
        "token_usage": {"input": run.input_tokens, "output": run.output_tokens},
        "api_requests": provider.api_requests,
        "reserved_token_budget": {
            "input": provider.reserved_input_tokens,
            "output": provider.reserved_output_tokens,
        },
        "estimated_cost_usd": round(actual_cost, 6),
        "cost_ceiling_usd": APPROVED_COST_CEILING_USD,
        "error": run.error,
    }
    output_dir = Path("artifacts")
    output_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"anthropic_dev_smoke_{stamp}.json"
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({**report, "report_path": str(output_path)}, indent=2))
    return 0 if run.status == "complete" and actual_cost <= APPROVED_COST_CEILING_USD else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute-paid-dev-smoke",
        action="store_true",
        help="Make the single real Anthropic DEV run after explicit spending approval.",
    )
    args = parser.parse_args()
    if not args.execute_paid_dev_smoke:
        print(json.dumps(plan(), indent=2))
        return 0
    return execute()


if __name__ == "__main__":
    raise SystemExit(main())
