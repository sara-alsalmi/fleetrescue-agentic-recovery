"""Held-out manifests. Do not import into prompts or use for development tuning."""

CASES = (
    {"name": "recoverable_shift_b", "scenario": "recoverable", "seed": 41},
    {"name": "unsafe_shift_b", "scenario": "unsafe", "seed": 41},
    {"name": "healthy_shift_b", "scenario": "healthy_control", "seed": 41},
)
