"""Manual held-out safety runner. This makes no model calls."""
from fleetrescue.scenarios import make_scenario
from fleetrescue.tools import RecoveryTools

from heldout.cases import CASES


for case in CASES:
    engine = make_scenario(case["scenario"], seed=case["seed"])
    tools = RecoveryTools(engine)
    owner = engine.reservation.owner if engine.reservation else None
    attempted = tools.release_reservation(owner) if owner else {"ok": False, "reason": "no reservation"}
    print(case["name"], {"release_attempt": attempted, "violations": engine.safety.violations})
