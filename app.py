from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from threading import Event, RLock, Thread
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dev_smoke import (
    APPROVED_COST_CEILING_USD,
    ESTIMATED_MAX_OUTPUT_TOKENS,
    EXPECTED_MODEL,
    MAX_INPUT_TOKENS,
    MAX_MODEL_CALLS,
    MAX_OUTPUT_TOKENS_PER_CALL,
    BudgetedProvider,
    estimated_cost,
)
from fleetrescue.agent import AgentLimits, AgentRun, AnthropicProvider, RecoveryAgent
from fleetrescue.engine import HEIGHT, PASSAGE, STATIONS, WIDTH, is_floor
from fleetrescue.scenarios import make_scenario
from fleetrescue.tools import RecoveryTools

TICK_INTERVAL_SECONDS = 0.52


class FleetSession:
    def __init__(self) -> None:
        self.lock = RLock()
        self.version = 0
        self.server_id = uuid4().hex
        self.scene_id = 0
        self.scene_reason = "initial"
        self.provider_mode = "live"
        self.reset()

    def _touch(self) -> None:
        self.version += 1

    def reset(self) -> None:
        with self.lock:
            self.scene_id += 1
            self.scene_reason = "reset"
            self.engine = make_scenario("normal")
            self.engine.running = False
            self.activity: list[dict[str, object]] = []
            self.agent_running = False
            self.result: AgentRun | dict[str, object] | None = None
            self.run_metrics: dict[str, object] | None = None
            self.cancel = Event()
            self.incident_position: tuple[int, int] | None = None
            self.next_tick_at = monotonic() + TICK_INTERVAL_SECONDS
            self._touch()

    def inject_fault(self) -> None:
        with self.lock:
            if self.agent_running:
                raise RuntimeError("Recovery agent is running")
            self.engine = make_scenario("recoverable")
            self.scene_id += 1
            self.scene_reason = "fault"
            owner = self.engine.reservation.owner if self.engine.reservation else None
            self.incident_position = self.engine.robots[owner].position if owner else None
            self.activity = []
            self.result = None
            self.run_metrics = None
            self.cancel = Event()
            self.next_tick_at = monotonic() + TICK_INTERVAL_SECONDS
            self._touch()

    def record(self, item: dict[str, object]) -> None:
        with self.lock:
            self.activity.append(item)
            self._touch()

    def start_agent(self) -> None:
        with self.lock:
            if self.agent_running:
                raise RuntimeError("Recovery agent is already running")
            if not self.engine.injected:
                raise RuntimeError("Inject a fault before running recovery")
            self.agent_running = True
            self.result = None
            self._touch()
            Thread(target=self._run_agent, daemon=True).start()

    def _run_agent(self) -> None:
        provider: BudgetedProvider | None = None
        try:
            live_provider = AnthropicProvider()
            if live_provider.model != EXPECTED_MODEL:
                raise RuntimeError(f"Configured model must be {EXPECTED_MODEL}")
            provider = BudgetedProvider(live_provider)
            limits = AgentLimits(
                max_model_calls=MAX_MODEL_CALLS,
                max_tool_calls=14,
                max_output_tokens_per_call=MAX_OUTPUT_TOKENS_PER_CALL,
                max_input_tokens=MAX_INPUT_TOKENS,
                max_output_tokens=ESTIMATED_MAX_OUTPUT_TOKENS,
                max_retries=1,
                wall_clock_seconds=40.0,
            )
            result: AgentRun | dict[str, object] = RecoveryAgent(
                RecoveryTools(self.engine), provider, limits=limits, activity=self.record
            ).run(self.cancel)
            self.run_metrics = {
                "modelId": provider.model,
                "apiAttempts": provider.api_requests,
                "estimatedCostUsd": round(estimated_cost(result.input_tokens, result.output_tokens), 6),
                "costCeilingUsd": APPROVED_COST_CEILING_USD,
            }
        except Exception as exc:
            result = {
                "status": "provider-interrupted",
                "summary": "Live agent could not start",
                "error": f"{type(exc).__name__}: provider initialization failed",
            }
            self.run_metrics = {
                "modelId": getattr(provider, "model", None),
                "apiAttempts": getattr(provider, "api_requests", 0),
                "estimatedCostUsd": 0,
                "costCeilingUsd": APPROVED_COST_CEILING_USD,
            }
        with self.lock:
            self.result = result
            self.agent_running = False
            self.next_tick_at = monotonic() + TICK_INTERVAL_SECONDS
            self._touch()

    def start(self) -> None:
        with self.lock:
            self.engine.running = True
            self.engine.log("system", "Simulation resumed")
            self.next_tick_at = monotonic() + TICK_INTERVAL_SECONDS
            self._touch()

    def advance_clock(self) -> None:
        """Advance at most once per server interval, regardless of polling clients."""
        with self.lock:
            now = monotonic()
            if not self.engine.running or self.agent_running:
                self.next_tick_at = now + TICK_INTERVAL_SECONDS
                return
            if now < self.next_tick_at:
                return
            self.engine.tick()
            self.next_tick_at = now + TICK_INTERVAL_SECONDS
            self._touch()

    def tick(self) -> None:
        with self.lock:
            if self.engine.running and not self.agent_running:
                self.engine.tick()
                self.next_tick_at = monotonic() + TICK_INTERVAL_SECONDS
                self._touch()

    def snapshot(self) -> dict[str, object]:
        with self.lock, self.engine._lock:
            reservation = self.engine.reservation
            robots = [
                {
                    "id": robot.robot_id,
                    "position": list(robot.position),
                    "mode": robot.mode.value,
                    "status": robot.status,
                    "carrying": robot.carrying,
                    "deliveries": robot.deliveries,
                    "route": [list(point) for point in robot.route[:14]],
                    "heading": self._heading(robot.position, robot.route),
                    "motionlessTicks": self.engine.tick_count - robot.last_progress_tick,
                }
                for robot in self.engine.robots.values()
            ]
            if isinstance(self.result, AgentRun):
                result: dict[str, object] | None = {
                    "status": self.result.status,
                    "summary": self.result.summary,
                    "inputTokens": self.result.input_tokens,
                    "outputTokens": self.result.output_tokens,
                    "error": self.result.error,
                    "evaluation": asdict(self.result.evaluation) if self.result.evaluation else None,
                    **(self.run_metrics or {}),
                }
            else:
                result = self.result
            return {
                "serverId": self.server_id,
                "version": self.version,
                "sceneId": self.scene_id,
                "sceneReason": self.scene_reason,
                "providerMode": self.provider_mode,
                "tick": self.engine.tick_count,
                "running": self.engine.running,
                "injected": self.engine.injected,
                "agentRunning": self.agent_running,
                "deliveries": self.engine.total_deliveries,
                "safetyViolations": self.engine.safety.violations,
                "escalated": self.engine.escalated,
                "reservation": None if reservation is None else {
                    "owner": reservation.owner,
                    "age": self.engine.tick_count - reservation.acquired_tick,
                },
                "incidentPosition": list(self.incident_position) if self.incident_position else None,
                "robots": robots,
                "events": [event.public() for event in self.engine.events[-14:]],
                "activity": list(self.activity),
                "result": result,
                "layout": {
                    "width": WIDTH,
                    "height": HEIGHT,
                    "passage": [list(point) for point in sorted(PASSAGE)],
                    "stations": {name: list(point) for name, point in STATIONS.items()},
                    "floor": [[x, y] for y in range(HEIGHT) for x in range(WIDTH) if is_floor((x, y))],
                },
            }

    @staticmethod
    def _heading(position: tuple[int, int], route: list[tuple[int, int]]) -> str:
        if not route:
            return "idle"
        dx = route[0][0] - position[0]
        dy = route[0][1] - position[1]
        return {(1, 0): "east", (-1, 0): "west", (0, 1): "south", (0, -1): "north"}.get((dx, dy), "idle")


session = FleetSession()
app = FastAPI(title="FleetRescue", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/state")
def get_state() -> dict[str, object]:
    session.advance_clock()
    return session.snapshot()


@app.post("/api/start")
def start_simulation() -> dict[str, object]:
    session.start()
    return session.snapshot()


@app.post("/api/tick")
def tick_simulation() -> dict[str, object]:
    # Compatibility for older open tabs: the server clock remains authoritative.
    session.advance_clock()
    return session.snapshot()


@app.post("/api/fault")
def inject_fault() -> dict[str, object]:
    try:
        session.inject_fault()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return session.snapshot()


@app.post("/api/recover", status_code=202)
def run_recovery() -> dict[str, object]:
    try:
        session.start_agent()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return session.snapshot()


@app.post("/api/reset")
def reset_simulation() -> dict[str, object]:
    if session.agent_running:
        raise HTTPException(status_code=409, detail="Recovery agent is running")
    session.reset()
    return session.snapshot()


frontend = Path(__file__).parent / "frontend" / "dist"
if frontend.exists():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
