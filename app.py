from __future__ import annotations

import html
import os
from threading import Event, Thread

import streamlit as st
from dotenv import load_dotenv

from fleetrescue.agent import AnthropicProvider, RecoveryAgent
from fleetrescue.engine import HEIGHT, PASSAGE, STATIONS, WIDTH
from fleetrescue.scenarios import make_scenario
from fleetrescue.tools import RecoveryTools

st.set_page_config(page_title="FleetRescue", page_icon="FR", layout="wide")
load_dotenv()
st.markdown("""
<style>
:root { --navy:#071522; --panel:#0d2232; --teal:#23d5c3; --muted:#8ea5b7; }
.stApp { background:var(--navy); color:#eef8fb; }
[data-testid="stMetric"] { background:#0d2232; border:1px solid #17384b; padding:12px; border-radius:12px; }
.mode { display:inline-block; padding:5px 10px; border-radius:999px; background:#123044; color:#8ff5e9; font-size:.78rem; }
.activity { background:#0b1d2b; border-left:3px solid #23d5c3; padding:9px 12px; margin:6px 0; border-radius:5px; }
.subtle { color:#8ea5b7; font-size:.88rem; }
</style>""", unsafe_allow_html=True)


def reset() -> None:
    st.session_state.engine = make_scenario("normal")
    st.session_state.engine.running = False
    st.session_state.activity = []
    st.session_state.agent_job = {"running": False, "result": None}
    st.session_state.cancel = Event()


if "engine" not in st.session_state:
    reset()


def warehouse_svg(engine) -> str:
    cell, pad = 62, 16
    width, height = WIDTH * cell + pad * 2, HEIGHT * cell + pad * 2
    station_at = {position: name for name, position in STATIONS.items()}
    robot_colors = ["#23d5c3", "#ffbd59", "#9b8cff", "#4fa3ff", "#ff718d", "#7ed957"]
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Warehouse map">',
             '<rect width="100%" height="100%" rx="18" fill="#091b29"/>']
    for y in range(HEIGHT):
        for x in range(WIDTH):
            px, py = pad + x * cell, pad + y * cell
            floor = x <= 4 or x >= 7 or (x, y) in PASSAGE
            fill = "#113449" if (x, y) in PASSAGE else ("#0e293b" if floor else "#06121d")
            stroke = "#23d5c3" if (x, y) in PASSAGE else "#17384b"
            parts.append(f'<rect x="{px}" y="{py}" width="{cell-3}" height="{cell-3}" rx="7" fill="{fill}" stroke="{stroke}"/>')
            if (x, y) in station_at:
                label = station_at[(x, y)]
                parts.append(f'<rect x="{px+9}" y="{py+9}" width="{cell-21}" height="{cell-21}" rx="5" fill="#17465a"/>')
                parts.append(f'<text x="{px+cell/2}" y="{py+cell/2+6}" text-anchor="middle" fill="#9eece4" font-size="17" font-weight="700">{label}</text>')
    parts.append(f'<text x="{pad+6*cell}" y="{pad+3*cell-8}" text-anchor="middle" fill="#72dcd1" font-size="11">SHARED PASSAGE</text>')
    for index, robot in enumerate(engine.robots.values()):
        x, y = robot.position
        cx, cy = pad + x * cell + (cell-3)/2, pad + y * cell + (cell-3)/2
        color = robot_colors[index % len(robot_colors)]
        opacity = ".45" if robot.mode.value != "active" else "1"
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="20" fill="{color}" opacity="{opacity}" stroke="#eef8fb" stroke-width="2"/>')
        parts.append(f'<text x="{cx}" y="{cy+5}" text-anchor="middle" fill="#06121d" font-size="12" font-weight="800">{html.escape(robot.robot_id)}</text>')
        if robot.carrying:
            parts.append(f'<rect x="{cx+13}" y="{cy-26}" width="13" height="13" fill="#f0d77a" stroke="#fff1b3"/>')
    parts.append('</svg>')
    return "".join(parts)


def run_agent(engine, activity: list[dict[str, object]], cancel: Event, job: dict[str, object]) -> None:
    # The background thread receives plain shared objects; it never calls Streamlit APIs.
    def record(item: dict[str, object]) -> None:
        activity.append(item)
    try:
        provider = AnthropicProvider()
        result = RecoveryAgent(RecoveryTools(engine), provider, activity=record).run(cancel)
    except Exception as exc:
        result = {"status": "provider-interrupted", "summary": "Live agent could not start", "error": str(exc)}
    job["result"] = result
    job["running"] = False


st.title("FleetRescue")
st.caption("A real stateful warehouse simulation with safety-validated AI recovery")

engine = st.session_state.engine
job = st.session_state.agent_job
top = st.columns([1.2, 1, 1, 1])
top[0].markdown('<span class="mode">DETERMINISTIC SIMULATION</span>', unsafe_allow_html=True)
top[1].metric("Tick", engine.tick_count)
top[2].metric("Deliveries", engine.total_deliveries)
top[3].metric("Passage", engine.reservation.owner if engine.reservation else "Available")

buttons = st.columns(4)
if buttons[0].button("Start simulation", type="primary", use_container_width=True, disabled=engine.running):
    engine.running = True
    engine.log("system", "Simulation resumed")
if buttons[1].button("Inject fault", use_container_width=True, disabled=engine.injected or job["running"]):
    try:
        owner = engine.inject_stale_reservation()
        st.session_state.activity.append({"tool": "fault injection", "result": f"{owner} stopped; reservation remains"})
    except ValueError as exc:
        st.warning(str(exc))
if buttons[2].button("Run recovery agent", use_container_width=True,
                     disabled=job["running"] or not engine.injected):
    job["running"] = True
    job["result"] = None
    thread = Thread(target=run_agent, args=(engine, st.session_state.activity, st.session_state.cancel, job), daemon=True)
    thread.start()
if buttons[3].button("Reset", use_container_width=True, disabled=job["running"]):
    reset()
    st.rerun()


@st.fragment(run_every=0.35)
def live_panel() -> None:
    engine = st.session_state.engine
    job = st.session_state.agent_job
    if engine.running and not job["running"]:
        engine.tick()
    left, right = st.columns([1.65, 1])
    with left:
        st.markdown(warehouse_svg(engine), unsafe_allow_html=True)
        cols = st.columns(len(engine.robots))
        for col, robot in zip(cols, engine.robots.values()):
            col.markdown(f"**{robot.robot_id}** · {robot.mode.value}<br><span class='subtle'>{html.escape(robot.status)} · {robot.deliveries} delivered</span>", unsafe_allow_html=True)
    with right:
        connected = bool(os.getenv("ANTHROPIC_API_KEY", "").strip() and os.getenv("FLEETRESCUE_MODEL", "").strip())
        label = "REAL MODEL RUNNING" if job["running"] else ("REAL MODEL CONFIGURED" if connected else "LIVE MODEL NOT CONFIGURED")
        st.markdown(f'<span class="mode">{label}</span>', unsafe_allow_html=True)
        st.subheader("Agent activity")
        if not st.session_state.activity:
            st.caption("Actual tool calls will appear here. Offline mocks are used only in tests.")
        for item in st.session_state.activity[-7:]:
            name = html.escape(str(item.get("tool", "event")))
            result = html.escape(str(item.get("result", "")))
            st.markdown(f'<div class="activity"><b>{name}</b><br><span class="subtle">{result[:280]}</span></div>', unsafe_allow_html=True)
        result = job["result"]
        if result:
            st.subheader("Independent verification")
            if isinstance(result, dict):
                st.error(f"{result['summary']}: {result.get('error', '')}")
            elif result.evaluation:
                ev = result.evaluation
                (st.success if ev.outcome == "complete" else st.warning)(
                    f"{ev.outcome.upper()} · +{ev.new_deliveries} deliveries · {ev.safety_violations} safety violations"
                )
                st.caption(f"Provider: {ev.provider} · Model: {ev.model} · Tokens: {ev.input_tokens} in / {ev.output_tokens} out")


live_panel()
