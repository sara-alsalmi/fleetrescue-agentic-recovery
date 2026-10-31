from __future__ import annotations

from dataclasses import dataclass

from .engine import PASSAGE, WarehouseEngine
from .models import RobotMode


@dataclass
class RecoveryTools:
    engine: WarehouseEngine
    minimum_inactive_ticks: int = 3

    def definitions(self) -> list[dict[str, object]]:
        empty = {"type": "object", "properties": {}, "additionalProperties": False}
        robot_arg = {"type": "object", "properties": {"robot_id": {"type": "string"}},
                     "required": ["robot_id"], "additionalProperties": False}
        return [
            {"name": "inspect_robots", "description": "Inspect robot state and recent motion evidence.", "input_schema": empty},
            {"name": "inspect_passage", "description": "Inspect current physical passage occupancy.", "input_schema": empty},
            {"name": "read_recent_events", "description": "Read a compact window of recent system events.", "input_schema": empty},
            {"name": "inspect_reservations", "description": "Inspect the current passage reservation and age.", "input_schema": empty},
            {"name": "release_reservation", "description": "Attempt to release a reservation; safety checks cannot be bypassed.", "input_schema": robot_arg},
            {"name": "quarantine_robot", "description": "Isolate an inactive robot from scheduling.", "input_schema": robot_arg},
            {"name": "observe_progress", "description": "Advance an observation window and report delivery progress and safety.",
             "input_schema": {"type": "object", "properties": {"ticks": {"type": "integer", "minimum": 1, "maximum": 20}},
                              "required": ["ticks"], "additionalProperties": False}},
            {"name": "escalate", "description": "Escalate when no permitted safe automated repair exists.",
             "input_schema": {"type": "object", "properties": {"reason": {"type": "string"}},
                              "required": ["reason"], "additionalProperties": False}},
        ]

    def call(self, name: str, args: dict[str, object]) -> dict[str, object]:
        method = getattr(self, name, None)
        if method is None or name.startswith("_"):
            return {"ok": False, "error": "unknown tool"}
        result = method(**args)
        if name in {"release_reservation", "quarantine_robot", "escalate"}:
            self.engine.action_history.append({"tick": self.engine.tick_count, "tool": name, "args": args, "result": result})
        return result

    def inspect_robots(self) -> dict[str, object]:
        return {"tick": self.engine.tick_count, "robots": [
            {"robot_id": r.robot_id, "position": r.position, "mode": r.mode.value, "status": r.status,
             "ticks_since_motion": self.engine.tick_count - r.last_progress_tick, "deliveries": r.deliveries}
            for r in self.engine.robots.values()
        ]}

    def inspect_passage(self) -> dict[str, object]:
        occupants = [r.robot_id for r in self.engine.robots.values() if r.position in PASSAGE]
        return {"tick": self.engine.tick_count, "cells": sorted(PASSAGE), "occupants": occupants, "physically_empty": not occupants}

    def read_recent_events(self) -> dict[str, object]:
        return {"tick": self.engine.tick_count, "events": [e.public() for e in self.engine.events[-12:]]}

    def inspect_reservations(self) -> dict[str, object]:
        reservation = self.engine.reservation
        if not reservation:
            return {"tick": self.engine.tick_count, "reservation": None}
        return {"tick": self.engine.tick_count, "reservation": {"owner": reservation.owner,
            "age_ticks": self.engine.tick_count - reservation.acquired_tick,
            "ticks_since_owner_progress": self.engine.tick_count - reservation.owner_last_progress_tick}}

    def release_reservation(self, robot_id: str) -> dict[str, object]:
        reservation = self.engine.reservation
        if not reservation or reservation.owner != robot_id:
            return {"ok": False, "reason": "robot does not own current reservation"}
        if any(r.position in PASSAGE for r in self.engine.robots.values()):
            return {"ok": False, "reason": "passage is physically occupied"}
        robot = self.engine.robots.get(robot_id)
        if not robot or robot.mode == RobotMode.ACTIVE:
            return {"ok": False, "reason": "reservation owner is active"}
        inactive_ticks = self.engine.tick_count - (robot.inactive_since if robot.inactive_since is not None else self.engine.tick_count)
        motionless_ticks = self.engine.tick_count - robot.last_progress_tick
        if inactive_ticks < self.minimum_inactive_ticks or motionless_ticks < self.minimum_inactive_ticks:
            return {"ok": False, "reason": "insufficient inactivity evidence", "inactive_ticks": inactive_ticks,
                    "motionless_ticks": motionless_ticks, "required": self.minimum_inactive_ticks}
        self.engine.reservation = None
        self.engine.log("action", f"Validated release of {robot_id}'s reservation", robot_id)
        return {"ok": True, "released_owner": robot_id, "safety_checks": {"passage_empty": True,
                "owner_inactive_ticks": inactive_ticks, "owner_motionless_ticks": motionless_ticks}}

    def quarantine_robot(self, robot_id: str) -> dict[str, object]:
        robot = self.engine.robots.get(robot_id)
        if not robot:
            return {"ok": False, "reason": "unknown robot"}
        if robot.mode == RobotMode.ACTIVE:
            return {"ok": False, "reason": "cannot quarantine a healthy active robot"}
        self.engine.quarantine(robot_id)
        return {"ok": True, "robot_id": robot_id}

    def observe_progress(self, ticks: int) -> dict[str, object]:
        before = self.engine.total_deliveries
        safety_before = self.engine.safety.violations
        self.engine.tick(ticks)
        return {"ticks_observed": ticks, "new_deliveries": self.engine.total_deliveries - before,
                "safety_violations": self.engine.safety.violations - safety_before,
                "reservation_owner": self.engine.reservation.owner if self.engine.reservation else None}

    def escalate(self, reason: str) -> dict[str, object]:
        self.engine.escalated = True
        self.engine.escalation_reason = reason[:240]
        self.engine.log("escalation", "Recovery escalated for human review")
        return {"ok": True, "status": "escalated"}
