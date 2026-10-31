from fastapi.testclient import TestClient

from app import app, session
from fleetrescue.agent import RecoveryAgent
from fleetrescue.mock_provider import Block, MockProvider
from fleetrescue.tools import RecoveryTools


client = TestClient(app)


def setup_function():
    session.reset()


def test_api_exposes_real_engine_state_and_controls():
    initial = client.get("/api/state").json()
    initial_scene = initial["sceneId"]
    initial_version = initial["version"]
    assert initial["tick"] == 0
    assert initial["deliveries"] == 0
    assert len(initial["robots"]) == 3

    started = client.post("/api/start").json()
    assert started["running"] is True
    advanced = client.post("/api/tick").json()
    assert advanced["tick"] == 1
    assert advanced["version"] > initial_version
    assert next(robot for robot in advanced["robots"] if robot["id"] == "R3")["position"] == [9, 6]

    incident = client.post("/api/fault").json()
    assert incident["sceneId"] > initial_scene
    assert incident["sceneReason"] == "fault"
    assert incident["injected"] is True
    assert incident["reservation"]["owner"] == "R3"
    failed = next(robot for robot in incident["robots"] if robot["id"] == "R3")
    assert failed["position"] == [9, 6]
    assert failed["mode"] == "inactive"

    reset = client.post("/api/reset").json()
    assert reset["tick"] == 0
    assert reset["injected"] is False
    assert reset["sceneId"] > incident["sceneId"]
    assert reset["version"] > incident["version"]


def test_recovery_requires_fault_without_starting_provider():
    response = client.post("/api/recover")
    assert response.status_code == 409
    assert "Inject a fault" in response.json()["detail"]


def test_normal_snapshots_match_engine_motion_and_faulted_robot_stays_fixed():
    client.post("/api/start")
    positions = []
    versions = []
    for _ in range(5):
        snapshot = client.post("/api/tick").json()
        positions.append({robot["id"]: robot["position"] for robot in snapshot["robots"]})
        versions.append(snapshot["version"])

    assert positions[0]["R3"] == [9, 6]
    assert positions[1]["R3"] == [8, 6]
    assert positions[2]["R3"] == [7, 6]
    assert positions[3]["R3"] == [7, 5]
    assert versions == sorted(versions)
    assert len(set(versions)) == len(versions)

    incident = client.post("/api/fault").json()
    incident_scene = incident["sceneId"]
    failed_position = next(robot for robot in incident["robots"] if robot["id"] == "R3")["position"]
    for _ in range(8):
        snapshot = client.post("/api/tick").json()
        failed = next(robot for robot in snapshot["robots"] if robot["id"] == "R3")
        assert snapshot["sceneId"] == incident_scene
        assert failed["position"] == failed_position
        assert failed["mode"] == "inactive"


def test_rapid_control_sequence_returns_coherent_scene_versions():
    started = client.post("/api/start").json()
    faulted = client.post("/api/fault").json()
    reset = client.post("/api/reset").json()
    restarted = client.post("/api/start").json()

    assert started["version"] < faulted["version"] < reset["version"] < restarted["version"]
    assert faulted["sceneId"] < reset["sceneId"]
    assert restarted["sceneId"] == reset["sceneId"]
    assert restarted["running"] is True


def test_mocked_recovery_serializes_real_activity_and_verification_state():
    session.inject_fault()
    owner = session.engine.reservation.owner

    def tool(name, payload=None, number=1):
        return Block("tool_use", id=f"api-{number}", name=name, input=payload or {})

    provider = MockProvider([
        [tool("inspect_robots"), tool("inspect_passage", number=2), tool("inspect_reservations", number=3)],
        [tool("release_reservation", {"robot_id": owner}, 4)],
        [tool("observe_progress", {"ticks": 20}, 5)],
        [Block("text", text="Recovery verified.")],
    ])
    run = RecoveryAgent(RecoveryTools(session.engine), provider, activity=session.record).run()
    with session.lock:
        session.result = run
        session._touch()

    state = client.get("/api/state").json()
    assert [item["tool"] for item in state["activity"]] == [
        "inspect_robots", "inspect_passage", "inspect_reservations", "release_reservation", "observe_progress"
    ]
    assert state["result"]["status"] == "complete"
    assert state["result"]["evaluation"]["new_deliveries"] >= 1
    assert state["result"]["evaluation"]["safety_violations"] == 0
    failed = next(robot for robot in state["robots"] if robot["id"] == "R3")
    assert failed["position"] == [9, 6]
