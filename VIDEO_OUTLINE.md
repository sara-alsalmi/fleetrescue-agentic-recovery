# Three-minute video outline

**0:00–0:25 — Frame the challenge.** Show the single FleetRescue screen. Point out three robots, fixed stations, box markers, and the teal shared passage. State that positions, routes, reservations, and deliveries are engine state—not animation cues.

**0:25–0:55 — Normal work.** Click **Start simulation**. Let robots move and at least one delivery complete. Briefly show the tick, delivery, and passage-owner indicators changing.

**0:55–1:20 — Visible incident.** Click **Inject fault**. Identify the inactive robot outside the passage and its retained reservation. Let several ticks pass: healthy robots visibly wait and the delivery count stalls.

**1:20–2:20 — Actual agent actions.** Click **Run recovery agent**. Call out the “real model running” badge and narrate actual tool cards as they appear: robot state, reservation age, recent events, and physical passage occupancy. Emphasize that the release tool—not the model—enforces empty-passage and inactivity checks. Show the chosen release/quarantine actions.

**2:20–2:50 — Verified recovery.** Watch healthy robots resume and a new delivery complete. Show the independent verification summary: `COMPLETE`, positive new-delivery count, and zero safety violations. Mention that the evaluator ignores the model’s claim and observes the engine.

**2:50–3:00 — Safety close.** State that an inactive robot inside the passage cannot be remotely cleared; the validated action is denied and the agent must escalate. Note that offline tests cover this and healthy-reservation preservation.
