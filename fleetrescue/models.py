from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

Position = tuple[int, int]


class RobotMode(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    QUARANTINED = "quarantined"


@dataclass
class Task:
    source: Position
    destination: Position
    box_id: str


@dataclass
class Robot:
    robot_id: str
    position: Position
    task: Task
    route: list[Position] = field(default_factory=list)
    mode: RobotMode = RobotMode.ACTIVE
    status: str = "ready"
    carrying: bool = True
    deliveries: int = 0
    last_progress_tick: int = 0
    inactive_since: int | None = None


@dataclass
class Reservation:
    owner: str
    acquired_tick: int
    owner_last_progress_tick: int


@dataclass
class Event:
    tick: int
    kind: str
    message: str
    robot_id: str | None = None

    def public(self) -> dict[str, object]:
        return {"tick": self.tick, "kind": self.kind, "message": self.message, "robot_id": self.robot_id}


@dataclass
class SafetyState:
    collisions: int = 0
    passage_violations: int = 0

    @property
    def violations(self) -> int:
        return self.collisions + self.passage_violations
