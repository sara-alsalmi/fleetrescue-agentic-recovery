from fleetrescue.engine import PASSAGE
from fleetrescue.scenarios import make_scenario


def test_normal_operation_completes_deliveries_without_violations():
    engine = make_scenario("normal")
    engine.tick(100)
    assert engine.total_deliveries >= 3
    assert engine.safety.violations == 0
    assert len([r for r in engine.robots.values() if r.position in PASSAGE]) <= 1


def test_fault_mutates_state_and_stalls_then_safe_release_resumes():
    engine = make_scenario("recoverable")
    owner = engine.reservation.owner
    assert owner == "R3"
    assert engine.robots[owner].position not in PASSAGE
    assert engine.robots[owner].mode.value == "inactive"
    assert all(engine.robots[owner].position not in robot.route
               for robot in engine.robots.values() if robot.robot_id != owner)
    from fleetrescue.tools import RecoveryTools
    tools = RecoveryTools(engine)
    assert tools.release_reservation(owner)["ok"] is True
    assert tools.quarantine_robot(owner)["ok"] is True
    before = engine.total_deliveries
    blocked_position = engine.robots[owner].position
    engine.tick(60)
    assert engine.total_deliveries > before
    assert engine.robots["R1"].deliveries > 0
    assert engine.robots["R2"].deliveries > 0
    assert engine.robots[owner].position == blocked_position
    assert engine.safety.violations == 0
