from types import SimpleNamespace

from fleetrescue.agent import AgentLimits, RecoveryAgent
from fleetrescue.mock_provider import Block, MockProvider
from fleetrescue.scenarios import make_scenario
from fleetrescue.tools import RecoveryTools


def tool(name, payload=None, number=1):
    return Block("tool_use", id=f"t{number}", name=name, input=payload or {})


def test_mocked_tool_loop_recovers_and_independently_verifies():
    engine = make_scenario("recoverable")
    owner = engine.reservation.owner
    provider = MockProvider([
        [tool("inspect_robots"), tool("inspect_passage", number=2), tool("inspect_reservations", number=3)],
        [tool("release_reservation", {"robot_id": owner}, 4), tool("quarantine_robot", {"robot_id": owner}, 5)],
        [tool("observe_progress", {"ticks": 20}, 6)],
        [Block("text", text="Verified recovery.")],
    ])
    run = RecoveryAgent(RecoveryTools(engine), provider).run()
    assert run.status == "complete"
    assert run.evaluation.new_deliveries >= 1
    assert run.evaluation.safety_violations == 0


def test_mocked_tool_loop_escalates_unsafe_case():
    engine = make_scenario("unsafe")
    owner = engine.reservation.owner
    provider = MockProvider([
        [tool("inspect_passage"), tool("inspect_robots", number=2)],
        [tool("release_reservation", {"robot_id": owner}, 3)],
        [tool("escalate", {"reason": "Inactive robot physically occupies passage"}, 4)],
        [Block("text", text="Escalated.")],
    ])
    run = RecoveryAgent(RecoveryTools(engine), provider).run()
    assert run.status == "escalated"
    assert engine.reservation.owner == owner


def test_mocked_healthy_control_does_not_release():
    engine = make_scenario("healthy_control")
    owner = engine.reservation.owner
    provider = MockProvider([[tool("release_reservation", {"robot_id": owner})], [Block("text", text="No action.")]])
    run = RecoveryAgent(RecoveryTools(engine), provider).run()
    release = next(item for item in run.trace if item["tool"] == "release_reservation")
    assert release["result"]["ok"] is False
    assert engine.robots[owner].mode.value == "active"


def test_failed_verification_allows_one_bounded_correction():
    engine = make_scenario("recoverable")
    owner = engine.reservation.owner
    provider = MockProvider([
        [tool("release_reservation", {"robot_id": owner}), tool("quarantine_robot", {"robot_id": owner}, 2)],
        [tool("observe_progress", {"ticks": 1}, 3)],
        [Block("text", text="Recovered.")],
        [tool("observe_progress", {"ticks": 20}, 4)],
        [Block("text", text="Recovered after correction.")],
    ])
    run = RecoveryAgent(RecoveryTools(engine), provider).run()
    observations = [item for item in run.trace if item["tool"] == "observe_progress"]
    assert len(observations) == 2
    assert run.status == "complete"


def test_retries_count_toward_model_attempt_limit_and_errors_are_redacted():
    class FailingProvider:
        name = "offline-failure"
        model = "offline-model"

        def __init__(self):
            self.attempts = 0

        def create(self, **_):
            self.attempts += 1
            raise RuntimeError("secret-value-must-not-be-reported")

    provider = FailingProvider()
    limits = AgentLimits(max_model_calls=2, max_retries=10)
    run = RecoveryAgent(RecoveryTools(make_scenario("recoverable")), provider, limits=limits).run()
    assert provider.attempts == 2
    assert "secret-value" not in (run.error or "")


def test_bad_request_diagnostic_is_sanitized():
    class FakeBadRequest(Exception):
        status_code = 400
        body = {
            "error": {
                "type": "invalid_request_error",
                "message": "temperature is not supported; api_key=sk-ant-secretvalue",
            }
        }

    class BadRequestProvider:
        name = "offline-bad-request"
        model = "offline-model"

        def create(self, **_):
            raise FakeBadRequest()

    limits = AgentLimits(max_retries=0)
    run = RecoveryAgent(RecoveryTools(make_scenario("recoverable")), BadRequestProvider(), limits=limits).run()
    assert "http_status=400" in run.error
    assert "anthropic_error_type=invalid_request_error" in run.error
    assert "temperature is not supported" in run.error
    assert "sk-ant-secretvalue" not in run.error
    assert "[REDACTED]" in run.error


def test_cumulative_output_limit_reduces_next_request_allowance():
    class UsageProvider:
        name = "offline-usage"
        model = "offline-model"

        def __init__(self):
            self.allowances = []

        def create(self, *, max_tokens, **_):
            self.allowances.append(max_tokens)
            content = [tool("inspect_robots")] if len(self.allowances) == 1 else [Block("text", text="done")]
            output = 6 if len(self.allowances) == 1 else 4
            return SimpleNamespace(content=content, usage=SimpleNamespace(input_tokens=10, output_tokens=output))

    provider = UsageProvider()
    limits = AgentLimits(max_model_calls=8, max_output_tokens_per_call=7, max_output_tokens=10)
    RecoveryAgent(RecoveryTools(make_scenario("recoverable")), provider, limits=limits).run()
    assert provider.allowances == [7, 4]


def test_tool_calls_are_capped_at_fourteen():
    provider = MockProvider([[tool("inspect_robots", number=index) for index in range(20)]])
    run = RecoveryAgent(RecoveryTools(make_scenario("recoverable")), provider).run()
    assert len(run.trace) == 14


def test_elapsed_timeout_prevents_another_provider_request(monkeypatch):
    import fleetrescue.agent as agent_module

    class CountingProvider:
        name = "offline-timeout"
        model = "offline-model"

        def __init__(self):
            self.calls = 0

        def create(self, **_):
            self.calls += 1
            usage = SimpleNamespace(input_tokens=10, output_tokens=5)
            return SimpleNamespace(content=[tool("inspect_robots")], usage=usage)

    clock = iter([0.0, 0.0, 41.0])
    monkeypatch.setattr(agent_module, "monotonic", lambda: next(clock))
    provider = CountingProvider()
    run = RecoveryAgent(RecoveryTools(make_scenario("recoverable")), provider).run()
    assert provider.calls == 1
    assert run.status == "provider-interrupted"
    assert run.summary == "Wall-clock limit reached"
