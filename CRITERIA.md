# Criteria and current evidence

| Area | Evidence | Status |
|---|---|---|
| Task performance | Stateful movement, deliveries, injected stale reservation, validated release, post-action observation | Implemented; offline tests passed |
| Robustness | Occupied-passage denial, active-owner denial, inactivity threshold, bounded provider failure states | Implemented; offline tests passed |
| Evaluation | 16-tick code evaluator, ≥1 new delivery, zero violations, preservation checks, explicit baseline, held-out layout | Implemented; held-out and live comparisons not yet run |
| Technical judgment | Engine/UI/agent separation, compact evidence, backend-only credentials, exact configured model ID, no arbitrary tools | Implemented |
| Engineering quality | Small modules, typed state, deterministic scenarios, offline pytest suite, minimal dependencies | Implemented; 10/10 offline tests passed |
| Communication | One-screen UI, activity summaries, README, video outline, explicit limitations | Implemented |
| Real-agent result | Paid Anthropic recovery run and actual cost/usage | **Not demonstrated; deliberately not run** |
