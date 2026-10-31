from fleetrescue.scenarios import make_scenario
from fleetrescue.tools import RecoveryTools


def test_unsafe_occupied_passage_cannot_be_released():
    engine = make_scenario("unsafe")
    owner = engine.reservation.owner
    result = RecoveryTools(engine).release_reservation(owner)
    assert result["ok"] is False
    assert "occupied" in result["reason"]
    assert engine.reservation.owner == owner


def test_active_legitimate_owner_is_preserved():
    engine = make_scenario("healthy_control")
    owner = engine.reservation.owner
    result = RecoveryTools(engine).release_reservation(owner)
    assert result["ok"] is False
    assert result["reason"] == "reservation owner is active"
    assert engine.reservation.owner == owner


def test_inactivity_evidence_threshold_is_enforced():
    engine = make_scenario("normal")
    owner = engine.inject_stale_reservation("R1")
    result = RecoveryTools(engine).release_reservation(owner)
    assert result["ok"] is False
    assert "insufficient" in result["reason"]
