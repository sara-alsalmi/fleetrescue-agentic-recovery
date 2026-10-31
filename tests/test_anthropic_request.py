import copy
from types import SimpleNamespace

from fleetrescue.agent import AnthropicProvider, RecoveryAgent
from fleetrescue.mock_provider import Block
from fleetrescue.scenarios import make_scenario
from fleetrescue.tools import RecoveryTools


class CapturingMessages:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1))


def test_sonnet_55_request_uses_supported_parameters_and_valid_tools():
    messages_api = CapturingMessages()
    provider = object.__new__(AnthropicProvider)
    provider.model = "claude-sonnet-5-5"
    provider._client = SimpleNamespace(messages=messages_api)
    tools = RecoveryTools(make_scenario("recoverable")).definitions()

    provider.create(
        messages=[{"role": "user", "content": "Investigate."}],
        tools=tools,
        max_tokens=700,
    )

    request = messages_api.kwargs
    assert request["model"] == "claude-sonnet-5-5"
    assert request["max_tokens"] == 700
    assert request["thinking"] == {"type": "between_tools"}
    assert request["tool_choice"] == {"type": "auto"}
    assert "temperature" not in request
    assert "top_p" not in request
    assert "top_k" not in request
    assert request["messages"] == [{"role": "user", "content": "Investigate."}]
    assert all({"name", "description", "input_schema"} <= definition.keys() for definition in request["tools"])


def test_signed_thinking_block_is_preserved_for_next_tool_turn():
    class ThinkingBlock:
        type = "thinking"

        def model_dump(self, **_):
            return {"type": "thinking", "thinking": "private reasoning", "signature": "signed-value"}

    class ThinkingProvider:
        name = "offline-thinking"
        model = "claude-sonnet-5-5"

        def __init__(self):
            self.calls = 0
            self.second_messages = None

        def create(self, *, messages, **_):
            self.calls += 1
            usage = SimpleNamespace(input_tokens=10, output_tokens=5)
            if self.calls == 1:
                tool = Block("tool_use", id="t1", name="inspect_robots", input={})
                return SimpleNamespace(content=[ThinkingBlock(), tool], usage=usage)
            self.second_messages = copy.deepcopy(messages)
            return SimpleNamespace(content=[Block("text", text="done")], usage=usage)

    provider = ThinkingProvider()
    RecoveryAgent(RecoveryTools(make_scenario("recoverable")), provider).run()
    assistant = provider.second_messages[-2]
    assert assistant["role"] == "assistant"
    assert assistant["content"][0] == {
        "type": "thinking",
        "thinking": "private reasoning",
        "signature": "signed-value",
    }
