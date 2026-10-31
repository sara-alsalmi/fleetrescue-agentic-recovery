from fleetrescue.evaluator import Evaluator, run_restart_baseline
from fleetrescue.scenarios import make_scenario


def test_evaluator_does_not_trust_action_success_without_progress():
    engine = make_scenario("recoverable")
    engine.running = False
    result = Evaluator(observation_ticks=8).evaluate(engine, deliveries_before=engine.total_deliveries,
        healthy_before={rid for rid, r in engine.robots.items() if r.mode.value == "active"})
    assert result.outcome == "incomplete"


def test_restart_baseline_is_explicit_and_keeps_reservation():
    engine = make_scenario("recoverable")
    owner = engine.reservation.owner
    result = run_restart_baseline(engine, owner)
    assert result.actions[0]["tool"] == "restart_robot"
    assert result.actions[0]["result"]["reservation_unchanged"] is True
