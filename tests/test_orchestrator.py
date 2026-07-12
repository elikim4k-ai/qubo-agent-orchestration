"""Orchestrator: epoch loop end-to-end with mock harnesses, decision records
as audit trail, idle ticks, and the never-blocking quantum mirror (§4.1)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import json
import time

from src.orchestrator import run_epoch
from src.registry import Registry
from src.vault import AgentProfile, TaskCard, Vault


def seed_vault(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.write_agent(AgentProfile(id="A-01", model_checkpoint="mock:big", capacity=3))
    vault.write_agent(AgentProfile(id="A-02", model_checkpoint="mock:small", capacity=3))
    for i, (cat, effort) in enumerate([("analysis", 2), ("analysis", 2),
                                       ("extraction", 1)], start=1):
        vault.write_task(TaskCard(id=f"T-{i}", title=f"task {i}", category=cat,
                                  effort=effort, status="eligible",
                                  body=f"See [[shared-note]] for context {i}."))
    (vault.root / "postmortems" / "shared-note.md").write_text("ctx", encoding="utf-8")
    return vault


def trained_registry():
    reg = Registry()
    for i in range(10):
        for agent, cat, ok in [("A-01", "analysis", True), ("A-01", "extraction", i % 2 == 0),
                               ("A-02", "analysis", i % 3 == 0), ("A-02", "extraction", True)]:
            reg.ingest([
                {"ts": "2026-07-12T00:00:00Z", "agent_id": agent, "task_id": f"X-{agent}-{cat}-{i}",
                 "category": cat, "event": "tool_call", "tool_call_valid": True},
                {"ts": "2026-07-12T00:00:01Z", "agent_id": agent, "task_id": f"X-{agent}-{cat}-{i}",
                 "category": cat, "event": "task_done" if ok else "task_failed",
                 "outcome": "success" if ok else "failure",
                 "tokens_prompt": 800, "tokens_completion": 200, "duration_ms": 4000},
            ])
    return reg


def test_epoch_assigns_all_tasks_and_writes_decision(tmp_path):
    vault = seed_vault(tmp_path)
    report = run_epoch(vault, trained_registry(), epoch=1)
    assert not report.idle and report.result.feasible
    assigned = sorted(t for ts in report.dispatched.values() for t in ts)
    assert assigned == ["T-1", "T-2", "T-3"]           # coverage
    assert report.decision_path is not None
    text = report.decision_path.read_text(encoding="utf-8")
    assert "backend: exact" in text and "[[T-1]]" in text
    assert all(vault.get_task(t).status == "assigned" for t in assigned)


def test_dispatch_callback_drives_task_status(tmp_path):
    vault = seed_vault(tmp_path)
    outcomes = {"T-1": True, "T-2": True, "T-3": False}
    report = run_epoch(vault, trained_registry(), epoch=1,
                       dispatch=lambda agent, task: outcomes[task.id])
    assert vault.get_task("T-1").status == "done"
    assert vault.get_task("T-3").status == "failed"
    assert not report.idle


def test_idle_tick_when_nothing_eligible(tmp_path):
    vault = Vault(tmp_path / "vault")
    vault.write_agent(AgentProfile(id="A-01", capacity=3))
    report = run_epoch(vault, Registry(), epoch=1)
    assert report.idle and report.decision_path is None


def test_quantum_mirror_is_async_and_logged(tmp_path):
    vault = seed_vault(tmp_path)
    log = tmp_path / "mirror.jsonl"
    start = time.monotonic()
    report = run_epoch(vault, trained_registry(), epoch=1,
                       quantum_mirror=True, mirror_backend="sa",
                       mirror_log=log, mirror_budget_s=30)
    classical_wall = time.monotonic() - start
    assert report.mirror_started
    assert classical_wall < 25           # dispatch did not wait for the mirror
    for _ in range(200):                 # mirror lands asynchronously
        if log.exists() and log.read_text(encoding="utf-8").strip():
            break
        time.sleep(0.1)
    record = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert record["epoch"] == 1 and record["meta"]["mirror"] is True
    assert record["feasible"] is True


def test_mirror_skipped_above_qubit_cap(tmp_path):
    vault = Vault(tmp_path / "vault")
    for a in range(4):
        vault.write_agent(AgentProfile(id=f"A-{a}", capacity=12))
    for t in range(8):
        vault.write_task(TaskCard(id=f"T-{t}", category="analysis",
                                  effort=1, status="eligible"))
    report = run_epoch(vault, Registry(), epoch=1, quantum_mirror=True)
    assert report.num_vars > 24 and not report.mirror_started
    assert report.result.feasible        # classical path unaffected
