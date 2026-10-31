"""Deterministic provider used only by offline tests; never substituted for live UI runs."""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any


@dataclass
class Block:
    type: str
    id: str | None = None
    name: str | None = None
    input: dict[str, object] | None = None
    text: str | None = None


class MockProvider:
    name = "offline-mock"
    model = "scripted-test-double"

    def __init__(self, calls: list[list[Block]]):
        self.calls = list(calls)

    def create(self, **_: Any) -> Any:
        content = self.calls.pop(0) if self.calls else [Block("text", text="done")]
        return SimpleNamespace(content=content, usage=SimpleNamespace(input_tokens=10, output_tokens=5))
