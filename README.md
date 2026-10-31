# FleetRescue

FleetRescue is a small, stateful robot-warehouse simulation built for a three-minute recovery-agent demo. Three robots continuously move boxes across a shared two-cell passage. A fault can stop a robot while its passage reservation remains, blocking real engine progress. A bounded Anthropic tool-calling agent investigates, chooses permitted actions, and is judged by code after an observation window.

## What is implemented

- Deterministic grid engine with actual positions, BFS routes, tasks, reservations, deliveries, and event history.
- Collision and passage-reservation invariants enforced on every simulation tick.
- Recoverable stale-reservation, unsafe occupied-passage, and healthy-control scenarios.
- Small observation/action tool set. Repair tools independently validate their safety preconditions.
- One bounded Anthropic tool loop: 8 model calls, 14 tool calls, 700 output tokens/call, one retry, and a 40-second wall-clock cap.
- Independent evaluator requiring at least one new delivery over a 16-tick observation window, zero safety violations, preserved healthy robots/reservations, and escalation of unsafe incidents.
- Explicit restart-only deterministic baseline that does not clear reservations.
- Offline unit tests and a separate fixed held-out layout (`seed=41`) whose identity and timing are not put in the model prompt.
- One-screen Streamlit UI with live simulation, real tool activity, and verification output.

## Setup and exact commands

Python 3.11+ is recommended.

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` locally. Supply both `ANTHROPIC_API_KEY` and the exact `FLEETRESCUE_MODEL` ID you selected. The application never guesses a model ID. It loads `.env` through `python-dotenv`; alternatively, set the values in your shell:

```powershell
$env:ANTHROPIC_API_KEY = "..."
$env:FLEETRESCUE_MODEL = "exact-model-id"
streamlit run app.py
```

Run the offline suite (no network or model calls):

```powershell
pytest -q
```

Run a minimal engine check:

```powershell
python -m fleetrescue
```

## Architecture

`fleetrescue/engine.py` owns all warehouse state and rules. `tools.py` exposes narrow observations/actions without scenario labels or suggested repairs. `agent.py` is the bounded Anthropic loop. `evaluator.py` independently advances the engine and scores physical progress. `app.py` only presents state and starts work; it cannot manufacture recovery.

The model cannot execute commands, read files, change safety logic, or directly mutate the engine. Full tool traces stay local; the model receives only compact tool results and a short recent-event window.

## Evaluation contract

The evaluation window is 16 ticks and the success threshold is at least one new completed delivery. Any collision or passage-occupancy violation fails verification. Healthy robots must remain active, legitimate active reservations must not be released, and an inactive passage occupant must lead to escalation. Outcomes are `complete`, `incomplete`, `escalated`, or `provider-interrupted`. Model prose is never an input to the score.

The held-out layout uses changed robot IDs (`R4`–`R6`), starts, destinations, and incident timing via `make_scenario(..., seed=41)`. Keep its results out of prompts and do not tune against it.

## Single paid DEV smoke-test plan — not run

After offline tests pass and you explicitly approve spending:

1. Configure the exact model ID and key locally.
2. Run one recoverable scenario only, with the built-in caps (maximum 8 requests and 5,600 generated tokens; normal expectation is 3–5 requests and well under 2,500 output tokens).
3. Save the local trace and evaluator result; verify at least one new delivery and zero safety violations.
4. Stop. Do not run held-out or comparison batches without separate approval.

**Current enforced estimate for `claude-sonnet-5-5`:** no more than **$0.1936** for this single smoke test, with at most 60,000 conservatively estimated input tokens and 5,600 output tokens at the current $2/million input and $10/million output rates, plus a conservative 1.1x regional multiplier. The hard approval ceiling remains **$0.20**. Before every request, the runner reserves a one-token-per-UTF-8-byte input estimate plus 1,024 tokens of protocol overhead and the full requested output allowance. Failed/retried requests retain their reservation. Recheck pricing if the model ID changes. The runner records actual token usage. No paid call has been made by this project.

Preview the guarded plan offline (this makes no API calls):

```powershell
py -3.13 dev_smoke.py
```

Only after explicit spending approval, run exactly once with:

```powershell
py -3.13 dev_smoke.py --execute-paid-dev-smoke
```

The runner requires `claude-sonnet-5-5`, uses its current $2/million input and
$10/million output pricing with a conservative 1.1x regional multiplier, and
refuses to start if the estimate exceeds $0.20. It writes the tool trace,
actions, independent verification, token usage, and estimated actual cost to a
local JSON report under `artifacts/`.

## Scope and limitations

This is a discrete simulation, not a robotics controller. “Physically empty” is exact simulation ground truth, not a real sensor-confidence claim. Robots use fixed tasks and simple shortest paths. There is no database, authentication, cloud deployment, arbitrary code execution, or multi-agent framework. Streamlit process restarts reset in-memory state.

See [VIDEO_OUTLINE.md](VIDEO_OUTLINE.md) for the demo sequence and [CRITERIA.md](CRITERIA.md) for evidence status.
