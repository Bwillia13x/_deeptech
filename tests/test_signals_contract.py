from __future__ import annotations

import re
from pathlib import Path

from signal_harvester.api import (
    Signal as BackendSignal,
)
from signal_harvester.api import (
    SignalsStats as BackendSignalsStats,
)
from signal_harvester.api import (
    SignalStatus as BackendSignalStatus,
)

FRONTEND_TYPES_PATH = Path(__file__).resolve().parents[1] / "frontend" / "src" / "types" / "api.ts"
FRONTEND_TYPES_TEXT = FRONTEND_TYPES_PATH.read_text()


def _load_frontend_type_fields(type_name: str) -> set[str]:
    match = re.search(rf"export type {type_name} = \{{(.*?)\}};", FRONTEND_TYPES_TEXT, re.S)
    if not match:
        raise AssertionError(f"Could not find {type_name} type definition in frontend types")
    body = match.group(1)
    field_names = re.findall(r"^\s*([a-zA-Z_]\w*)\??\s*:", body, re.M)
    if not field_names:
        raise AssertionError(f"{type_name} type definition is empty or unparsable")
    return set(field_names)


def _load_frontend_signal_status_values() -> set[str]:
    match = re.search(r"export type SignalStatus = ([^;]+);", FRONTEND_TYPES_TEXT, re.S)
    if not match:
        raise AssertionError("Could not find SignalStatus union in frontend types")
    unions = match.group(1)
    values = {part.strip().strip('"') for part in unions.split("|") if part.strip()}
    if not values:
        raise AssertionError("SignalStatus union is empty or unparsable")
    return values


def test_signals_stats_contract_matches_frontend_type() -> None:
    backend_fields = set(BackendSignalsStats.model_fields.keys())
    frontend_fields = _load_frontend_type_fields("SignalsStats")
    assert backend_fields == frontend_fields, (
        f"SignalsStats mismatch: backend={sorted(backend_fields)} frontend={sorted(frontend_fields)}"
    )


def test_signal_contract_matches_frontend_type() -> None:
    backend_fields = set(BackendSignal.model_fields.keys())
    frontend_fields = _load_frontend_type_fields("Signal")
    assert backend_fields == frontend_fields, (
        f"Signal mismatch: backend={sorted(backend_fields)} frontend={sorted(frontend_fields)}"
    )


def test_signal_status_enum_matches_frontend_union() -> None:
    backend_values = {status.value for status in BackendSignalStatus}
    frontend_values = _load_frontend_signal_status_values()
    assert backend_values == frontend_values, (
        f"SignalStatus mismatch: backend={sorted(backend_values)} frontend={sorted(frontend_values)}"
    )
