"""Feature flag helpers for PRO/derived outputs.

Flags default to OFF to preserve Lite determinism. Callers can override
per-run (e.g., CLI options) to enable derived fields.
"""

from __future__ import annotations

from typing import Dict

DEFAULT_FEATURE_FLAGS: Dict[str, bool] = {
    "ev_bands": False,
    "race_summary": False,
    "pretty_output": False,
    "mobile_output": False,
}


def resolve_feature_flags(overrides: Dict[str, bool] | None = None) -> Dict[str, bool]:
    flags = DEFAULT_FEATURE_FLAGS.copy()
    if overrides:
        for key, value in overrides.items():
            if key in flags:
                flags[key] = bool(value)
    return flags
