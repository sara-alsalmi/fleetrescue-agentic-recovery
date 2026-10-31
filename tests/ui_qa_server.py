"""Browser QA app: real recovery loop with a paced offline provider, never Anthropic."""

from time import sleep

from app import app, session
from fleetrescue.agent import RecoveryAgent
from fleetrescue.mock_provider import Block, MockProvider
from fleetrescue.tools import RecoveryTools


def tool(name: str, payload: dict[str, object] | None = None, number: int = 1) -> Block:
    return Block("tool_use", id=f"qa-{number}", name=name, input=payload or {})


class PacedMockProvider(MockProvider):
    def create(self, **kwargs):
        sleep(0.45)
        return super().create(**kwargs)


def run_offline_recovery() -> None:
    owner = session.engine.reservation.owner if session.engine.reservation else "R3"
    provider = PacedMockProvider([
        [tool("inspect_robots"), tool("inspect_passage", number=2), tool("inspect_reservations", number=3)],
        [tool("release_reservation", {"robot_id": owner}, 4)],
        [tool("observe_progress", {"ticks": 20}, 5)],
        [Block("text", text="Independent recovery verification complete.")],
    ])
    result = RecoveryAgent(RecoveryTools(session.engine), provider, activity=session.record).run(session.cancel)
    with session.lock:
        session.result = result
        session.agent_running = False
        session._touch()


session.provider_mode = "offline-mock"
session._run_agent = run_offline_recovery  # type: ignore[method-assign]
