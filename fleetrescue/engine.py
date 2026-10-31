from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import RLock

from .models import Event, Position, Reservation, Robot, RobotMode, SafetyState, Task

WIDTH, HEIGHT = 12, 7
PASSAGE: frozenset[Position] = frozenset({(5, 3), (6, 3)})
APPROACH: frozenset[Position] = frozenset({(4, 3), (7, 3)})
STATIONS: dict[str, Position] = {"A": (1, 1), "B": (10, 1), "C": (1, 5), "D": (10, 5)}


def is_floor(pos: Position) -> bool:
    x, y = pos
    if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
        return False
    return x <= 4 or x >= 7 or pos in PASSAGE


def shortest_route(start: Position, goal: Position) -> list[Position]:
    if start == goal:
        return []
    queue = deque([start])
    parent: dict[Position, Position | None] = {start: None}
    while queue:
        current = queue.popleft()
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            nxt = (current[0] + dx, current[1] + dy)
            if is_floor(nxt) and nxt not in parent:
                parent[nxt] = current
                if nxt == goal:
                    route: list[Position] = []
                    cursor = nxt
                    while cursor != start:
                        route.append(cursor)
                        cursor = parent[cursor]  # type: ignore[assignment]
                    return list(reversed(route))
                queue.append(nxt)
    raise ValueError(f"No route from {start} to {goal}")


@dataclass
class WarehouseEngine:
    robots: dict[str, Robot]
    tick_count: int = 0
    reservation: Reservation | None = None
    events: list[Event] = field(default_factory=list)
    safety: SafetyState = field(default_factory=SafetyState)
    running: bool = False
    injected: bool = False
    escalated: bool = False
    escalation_reason: str | None = None
    action_history: list[dict[str, object]] = field(default_factory=list)
    _lock: RLock = field(default_factory=RLock, repr=False)

    @property
    def total_deliveries(self) -> int:
        return sum(robot.deliveries for robot in self.robots.values())

    def log(self, kind: str, message: str, robot_id: str | None = None) -> None:
        self.events.append(Event(self.tick_count, kind, message, robot_id))

    def _set_return_task(self, robot: Robot) -> None:
        old = robot.task
        robot.task = Task(old.destination, old.source, old.box_id)
        robot.route = shortest_route(robot.position, robot.task.destination)
        robot.carrying = True

    def _validate_invariants(self) -> None:
        positions = [r.position for r in self.robots.values()]
        if len(positions) != len(set(positions)):
            self.safety.collisions += 1
            raise RuntimeError("Collision invariant violated")
        occupants = [r for r in self.robots.values() if r.position in PASSAGE]
        if len(occupants) > 1:
            self.safety.passage_violations += 1
            raise RuntimeError("Multiple robots occupy passage")
        if occupants and (self.reservation is None or self.reservation.owner != occupants[0].robot_id):
            self.safety.passage_violations += 1
            raise RuntimeError("Passage occupant lacks its reservation")

    def tick(self, steps: int = 1) -> None:
        with self._lock:
            for _ in range(steps):
                self.tick_count += 1
                if not self.running:
                    continue
                occupied = {robot.position for robot in self.robots.values()}
                for robot_id in sorted(self.robots):
                    robot = self.robots[robot_id]
                    if robot.mode != RobotMode.ACTIVE:
                        robot.status = robot.mode.value
                        continue
                    if not robot.route:
                        robot.deliveries += 1
                        self.log("delivery", f"{robot_id} completed delivery {robot.deliveries}", robot_id)
                        self._set_return_task(robot)
                    if not robot.route:
                        continue
                    nxt = robot.route[0]
                    # Reserve before entering a gateway approach. This prevents an opposing
                    # robot from parking on the owner's exit cell and creating a gridlock.
                    enters_approach = (nxt in APPROACH and len(robot.route) > 1 and robot.route[1] in PASSAGE)
                    needs_reservation = nxt in PASSAGE or enters_approach
                    if needs_reservation and self.reservation is None:
                        self.reservation = Reservation(robot_id, self.tick_count, robot.last_progress_tick)
                        robot.status = "reserved passage"
                        self.log("reservation", f"{robot_id} acquired passage reservation", robot_id)
                        continue
                    if needs_reservation and self.reservation.owner != robot_id:  # type: ignore[union-attr]
                        robot.status = "waiting: passage reserved"
                        continue
                    if nxt in occupied:
                        robot.status = "waiting: cell occupied"
                        continue
                    occupied.remove(robot.position)
                    robot.position = robot.route.pop(0)
                    occupied.add(robot.position)
                    robot.last_progress_tick = self.tick_count
                    robot.status = "moving"
                    if self.reservation and self.reservation.owner == robot_id:
                        self.reservation.owner_last_progress_tick = self.tick_count
                    if robot.position not in PASSAGE and self.reservation and self.reservation.owner == robot_id:
                        # Release only after a robot has traversed the passage, not while approaching it.
                        if all(cell not in robot.route[:2] for cell in PASSAGE):
                            self.log("reservation", f"{robot_id} released passage reservation", robot_id)
                            self.reservation = None
                self._validate_invariants()

    def inject_stale_reservation(self, robot_id: str | None = None, *, in_passage: bool = False) -> str:
        with self._lock:
            if self.injected:
                raise ValueError("A fault is already active")
            candidates = [r for r in self.robots.values() if r.mode == RobotMode.ACTIVE]
            if robot_id:
                candidates = [r for r in candidates if r.robot_id == robot_id]
            if not candidates:
                raise ValueError("No active target robot")
            target = sorted(candidates, key=lambda r: r.robot_id)[0]
            if in_passage:
                if any(r.position in PASSAGE and r.robot_id != target.robot_id for r in self.robots.values()):
                    raise ValueError("Passage is occupied")
                old = target.position
                target.position = (5, 3)
                target.route = shortest_route(target.position, target.task.destination)
                self.log("movement", f"{target.robot_id} entered the passage from {old}", target.robot_id)
            elif target.position in PASSAGE:
                raise ValueError("Target must be outside passage")
            self.reservation = Reservation(target.robot_id, self.tick_count, target.last_progress_tick)
            target.mode = RobotMode.INACTIVE
            target.inactive_since = self.tick_count
            target.status = "inactive"
            self.injected = True
            self.log("fault", f"{target.robot_id} stopped responding", target.robot_id)
            self._validate_invariants()
            return target.robot_id

    def quarantine(self, robot_id: str) -> None:
        robot = self.robots[robot_id]
        robot.mode = RobotMode.QUARANTINED
        robot.status = "quarantined"
        self.log("action", f"{robot_id} quarantined", robot_id)

    def restart_robot(self, robot_id: str) -> bool:
        robot = self.robots[robot_id]
        if robot.position in PASSAGE:
            return False
        robot.mode = RobotMode.ACTIVE
        robot.inactive_since = None
        robot.status = "restarted"
        self.log("action", f"{robot_id} restarted", robot_id)
        return True

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "tick": self.tick_count,
                "running": self.running,
                "deliveries": self.total_deliveries,
                "reservation": None if not self.reservation else self.reservation.owner,
                "robots": {rid: {"position": r.position, "mode": r.mode.value, "status": r.status,
                                  "deliveries": r.deliveries} for rid, r in self.robots.items()},
            }
