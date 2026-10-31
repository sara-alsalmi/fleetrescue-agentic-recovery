from types import SimpleNamespace

import pytest

from dev_smoke import (
    APPROVED_COST_CEILING_USD,
    ESTIMATED_MAX_OUTPUT_TOKENS,
    MAX_INPUT_TOKENS,
    BudgetedProvider,
    estimated_cost,
)


class OfflineDelegate:
    name = "anthropic"
    model = "claude-sonnet-5-5"

    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail

    def create(self, **_):
        self.calls += 1
        if self.fail:
            raise RuntimeError("offline failure")
        usage = SimpleNamespace(input_tokens=1, output_tokens=1)
        return SimpleNamespace(content=[], usage=usage)


def test_declared_worst_case_remains_below_cost_ceiling():
    assert estimated_cost(MAX_INPUT_TOKENS, ESTIMATED_MAX_OUTPUT_TOKENS) == pytest.approx(0.1936)
    assert estimated_cost(MAX_INPUT_TOKENS, ESTIMATED_MAX_OUTPUT_TOKENS) < APPROVED_COST_CEILING_USD


def test_budget_reservation_blocks_ninth_request_before_delegate():
    delegate = OfflineDelegate()
    provider = BudgetedProvider(delegate)
    for _ in range(8):
        provider.create(messages=[], tools=[], max_tokens=700)
    with pytest.raises(RuntimeError, match="output-token limit"):
        provider.create(messages=[], tools=[], max_tokens=700)
    assert delegate.calls == 8
    assert provider.reserved_output_tokens == 5_600


def test_failed_request_keeps_its_budget_reservation_for_retry():
    delegate = OfflineDelegate(fail=True)
    provider = BudgetedProvider(delegate)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="offline failure"):
            provider.create(messages=[], tools=[], max_tokens=700)
    assert delegate.calls == 2
    assert provider.reserved_output_tokens == 1_400


def test_oversized_input_is_rejected_before_delegate():
    delegate = OfflineDelegate()
    provider = BudgetedProvider(delegate)
    oversized = [{"role": "user", "content": "x" * MAX_INPUT_TOKENS}]
    with pytest.raises(RuntimeError, match="input-token limit"):
        provider.create(messages=oversized, tools=[], max_tokens=700)
    assert delegate.calls == 0
