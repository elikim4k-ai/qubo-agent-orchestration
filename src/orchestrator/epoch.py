"""Orchestrator epoch loop (thesis §3.1/§4.1 process 2).

Each tick: eligible tasks from the vault -> coefficients from the registry ->
Instance -> solve_qubo (classical, for dispatch) -> validate/repair -> decision
record to the vault -> dispatch to harnesses. For instances small enough
(N <= 24) the solve is mirrored asynchronously to the quantum path; the mirror
is advisory, logged, and can never block or fail dispatch.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..qubo.builder import Instance, slack_coeffs
from ..registry.profiles import Registry
from ..solver.service import solve_qubo
from ..solver.types import SolveResult
from ..vault.store import AgentProfile, DecisionRecord, TaskCard, Vault

QUANTUM_MIRROR_MAX_VARS = 24     # Table 3.2: 'hardware, workable'
MIRROR_BUDGET_S = 900.0          # §5.7: 15-minute mirror budget


@dataclass
class EpochReport:
    epoch: int
    num_agents: int
    num_tasks: int
    num_vars: int
    result: SolveResult
    decision_path: Path | None
    dispatched: dict[str, list[str]] = field(default_factory=dict)
    mirror_started: bool = False
    idle: bool = False


def build_instance(vault: Vault, registry: Registry,
                   agents: list[AgentProfile], tasks: list[TaskCard],
                   alpha: float = 0.5) -> Instance:
    utilities, weights, capacities = registry.coefficients(agents, tasks)
    return Instance(
        utilities=utilities, weights=weights, capacities=capacities,
        affinity=vault.affinity(tasks), exclusions=vault.exclusions(tasks),
        alpha=alpha,
    )


def _num_vars(inst: Instance) -> int:
    return inst.m * inst.n + sum(len(slack_coeffs(c)) for c in inst.capacities)


def _default_mirror_log(root: Path) -> Path:
    return root / "telemetry" / "quantum_mirror_log.jsonl"


def _start_quantum_mirror(inst: Instance, epoch: int, backend: str,
                          log_path: Path, budget_s: float) -> threading.Thread:
    """Fire-and-forget mirror solve. Daemon thread: dispatch never waits."""
    def _mirror():
        result = solve_qubo(inst, backend=backend, budget_s=budget_s,
                            meta={"epoch": epoch, "mirror": True,
                                  "instance_id": f"epoch-{epoch}"})
        record = {"ts": datetime.now(timezone.utc).isoformat(), "epoch": epoch,
                  **result.to_dict()}
        record.pop("bits", None)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    thread = threading.Thread(target=_mirror, name=f"quantum-mirror-{epoch}",
                              daemon=True)
    thread.start()
    return thread


def run_epoch(vault: Vault, registry: Registry, epoch: int,
              dispatch=None, backend: str = "exact", budget_s: float = 30.0,
              quantum_mirror: bool = False, mirror_backend: str = "qaoa_sim",
              mirror_budget_s: float = MIRROR_BUDGET_S,
              mirror_log: Path | None = None, max_tasks: int | None = None,
              alpha: float = 0.5) -> EpochReport:
    """One scheduling tick. `dispatch(agent, task) -> bool` runs the task on
    its harness and reports semantic success; when None, tasks are only marked
    'assigned' and the caller drives the harnesses itself."""
    agents = vault.agents()
    tasks = vault.eligible_tasks()
    if max_tasks is not None:
        tasks = tasks[:max_tasks]
    if not agents or not tasks:
        empty = SolveResult(backend="none", energy=0.0, bits=None, assignment={},
                            feasible=True, repaired=False, objective_utility=0.0,
                            optimal=True, wall_ms=0, num_vars=0, meta={})
        return EpochReport(epoch, len(agents), len(tasks), 0, empty, None, idle=True)

    inst = build_instance(vault, registry, agents, tasks, alpha)
    num_vars = _num_vars(inst)

    mirror_started = False
    if quantum_mirror and num_vars <= QUANTUM_MIRROR_MAX_VARS:
        _start_quantum_mirror(
            inst, epoch, mirror_backend,
            mirror_log or _default_mirror_log(vault.root.parent), mirror_budget_s)
        mirror_started = True

    # classical dispatch path — the fleet never waits on the mirror
    result = solve_qubo(inst, backend=backend, budget_s=budget_s,
                        meta={"epoch": epoch})

    assignment_ids = {agents[i].id: [tasks[j].id for j in js]
                      for i, js in result.assignment.items() if js}
    decision_path = vault.write_decision(DecisionRecord(
        epoch=epoch, backend=result.backend, energy=result.energy,
        assignment=assignment_ids,
        calibration_snapshot=str(result.meta.get("calibration_snapshot", "")),
    ))

    dispatched: dict[str, list[str]] = {}
    assigned_task_ids = {tid for tids in assignment_ids.values() for tid in tids}
    for tid in assigned_task_ids:
        vault.set_task_status(tid, "assigned")
    for i, js in result.assignment.items():
        agent = agents[i]
        for j in js:
            task = tasks[j]
            dispatched.setdefault(agent.id, []).append(task.id)
            if dispatch is not None:
                success = bool(dispatch(agent, task))
                vault.set_task_status(task.id, "done" if success else "failed")

    return EpochReport(epoch, len(agents), len(tasks), num_vars, result,
                       decision_path, dispatched, mirror_started)


def run_loop(vault: Vault, registry: Registry, ticks: int,
             tick_seconds: float = 120.0, dispatch=None,
             telemetry_path: str | Path | None = None,
             **epoch_kwargs) -> list[EpochReport]:
    """The live loop (§5.7): tick every `tick_seconds`, idle through empty
    epochs, refresh registry coefficients from telemetry between ticks."""
    reports = []
    for t in range(ticks):
        if telemetry_path is not None:
            fresh = Registry.from_telemetry(telemetry_path, kappa=registry.kappa)
            fresh.rejected += registry.rejected
            registry = fresh
        report = run_epoch(vault, registry, epoch=t, dispatch=dispatch,
                           **epoch_kwargs)
        reports.append(report)
        if t < ticks - 1 and tick_seconds > 0:
            time.sleep(tick_seconds)
    return reports
