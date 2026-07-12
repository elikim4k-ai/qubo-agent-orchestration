"""Harness: BFS context assembly under budget, one-shot tool repair,
ceilings, and schema-valid telemetry from the very first run (thesis §4.3)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json

from src.vault import TaskCard, Vault
from src.harness import (
    HarnessLimits, MockModelClient, TelemetryWriter, assemble_context,
    read_events, run_task,
)


def make_vault(tmp_path):
    vault = Vault(tmp_path / "vault")
    (vault.root / "postmortems" / "note-a.md").write_text(
        "Alpha context, see [[note-b]].", encoding="utf-8")
    (vault.root / "postmortems" / "note-b.md").write_text(
        "Beta context. " * 200, encoding="utf-8")
    task = TaskCard(id="T-1", title="Summarise alpha", category="analysis",
                    status="eligible", body="Work from [[note-a]].")
    vault.write_task(task)
    return vault, task


def test_context_assembly_is_bfs_and_budgeted(tmp_path):
    vault, task = make_vault(tmp_path)
    ctx = assemble_context(vault, task, budget_tokens=100)
    assert "Alpha context" in ctx          # direct link included
    assert "Beta context" not in ctx       # second hop exceeds the budget
    ctx_big = assemble_context(vault, task, budget_tokens=5000)
    assert "Beta context" in ctx_big       # budget lifted -> BFS reaches hop 2


def test_run_task_success_and_telemetry_schema(tmp_path):
    vault, task = make_vault(tmp_path)
    tel_path = tmp_path / "telemetry.jsonl"
    client = MockModelClient({"analysis": 1.0}, seed=1, malformed_rate=0.0)
    writer = TelemetryWriter(tel_path, "A-01", "mock:deterministic")
    outcome = run_task(vault, task, client, writer)
    assert outcome.success and outcome.result
    events, rejected = read_events(tel_path)
    assert rejected == 0 and events  # every emitted event validates
    kinds = [e["event"] for e in events]
    assert kinds.count("task_done") == 1
    assert "tool_call" in kinds and "step" in kinds
    assert events[-1]["outcome"] == "success"
    assert all(e["agent_id"] == "A-01" for e in events)


def test_malformed_tool_call_gets_exactly_one_repair(tmp_path):
    vault, task = make_vault(tmp_path)
    tel_path = tmp_path / "telemetry.jsonl"
    client = MockModelClient({"analysis": 1.0}, seed=1, malformed_rate=1.0)
    writer = TelemetryWriter(tel_path, "A-01")
    outcome = run_task(vault, task, client, writer)
    events, _ = read_events(tel_path)
    kinds = [e["event"] for e in events]
    assert kinds.count("tool_repair") == 1
    validity = [e["tool_call_valid"] for e in events if e["event"] == "tool_call"]
    assert validity[0] is False and validity[-1] is True
    assert outcome.success  # repair recovered the call


def test_step_ceiling_fails_task_with_timeout_outcome(tmp_path):
    vault, task = make_vault(tmp_path)

    class Babbler:  # never issues a tool call
        def start_task(self): pass
        def complete(self, system, messages, tools):
            from src.harness import ModelResponse
            return ModelResponse(text="hmm", tokens_prompt=10, tokens_completion=5)

    tel_path = tmp_path / "telemetry.jsonl"
    outcome = run_task(vault, task, Babbler(), TelemetryWriter(tel_path, "A-02"),
                       HarnessLimits(max_steps=3))
    assert not outcome.success and outcome.reason == "step ceiling"
    events, _ = read_events(tel_path)
    assert events[-1]["event"] == "task_failed"
    assert events[-1]["outcome"] == "timeout"


def test_read_events_rejects_poisoned_lines(tmp_path):
    p = tmp_path / "t.jsonl"
    good = {"ts": "2026-07-12T00:00:00Z", "agent_id": "A-01", "task_id": "T-1",
            "category": "analysis", "event": "step"}
    p.write_text(json.dumps(good) + "\n"
                 + "not json at all\n"
                 + json.dumps({**good, "event": "rm -rf /"}) + "\n",
                 encoding="utf-8")
    events, rejected = read_events(p)
    assert len(events) == 1 and rejected == 2
