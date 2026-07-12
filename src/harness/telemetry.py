"""Telemetry emitter (thesis §4.3: 'telemetry is the product').

Every event is validated against telemetry/schema.json BEFORE it is written;
an event that fails validation is a bug in the harness, not a log line to
tolerate. Events are appended as JSONL, one file per run (or shared).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "telemetry" / "schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
_VALIDATOR = jsonschema.Draft7Validator(_SCHEMA)


def validate_event(event: dict) -> None:
    """Raise jsonschema.ValidationError if the event violates the schema."""
    _VALIDATOR.validate(event)


class TelemetryWriter:
    def __init__(self, path: str | Path, agent_id: str, model_checkpoint: str = ""):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.agent_id = agent_id
        self.model_checkpoint = model_checkpoint

    def emit(self, event: str, task_id: str, category: str, **fields) -> dict:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "agent_id": self.agent_id,
            "model_checkpoint": self.model_checkpoint,
            "task_id": task_id,
            "category": category,
            "event": event,
            **fields,
        }
        validate_event(record)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return record


def read_events(path: str | Path) -> tuple[list[dict], int]:
    """Read a telemetry JSONL file, dropping invalid lines.

    Returns (valid_events, rejected_count). Rejection rather than repair is
    deliberate: telemetry feeds the registry, which feeds the optimizer, and
    §4.4 / the week-two incident (§5.7) say malformed input must never
    propagate into coefficients.
    """
    events, rejected = [], 0
    p = Path(path)
    if not p.exists():
        return events, rejected
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
            validate_event(ev)
            events.append(ev)
        except (json.JSONDecodeError, jsonschema.ValidationError):
            rejected += 1
    return events, rejected
