"""End-to-end demonstration of the full stack (thesis §4.1, all five processes
in one process for legibility):

  1. seed a vault with 4 mock Hermes agents + a linked task graph,
  2. warm up: harness runs generate REAL telemetry (instrumentation first),
  3. registry folds telemetry into (agent, category) profiles -> u, w, C,
  4. orchestrator epochs: CBC dispatch + async quantum-path mirror,
  5. compare against the greedy incumbent and print the audit trail.

Run:  .venv\\Scripts\\python.exe scripts\\run_demo.py [--mirror qaoa_sim|sa|off]
Everything lands under demo_run/ (safe to delete between runs).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.experiments.benchmark import greedy_baseline
from src.harness import HarnessLimits, MockModelClient, TelemetryWriter, run_task
from src.orchestrator import build_instance, run_epoch
from src.registry import Registry
from src.solver.types import objective_utility
from src.vault import AgentProfile, TaskCard, Vault

DEMO_ROOT = Path(__file__).resolve().parents[1] / "demo_run"

# four Hermes agents, two large two small (§5.7), with distinct skill shapes
AGENT_SKILLS = {
    "A-01": {"checkpoint": "mock:hermes-large-a", "capacity": 6,
             "skill": {"analysis": 0.95, "writing": 0.85, "extraction": 0.6}},
    "A-02": {"checkpoint": "mock:hermes-large-b", "capacity": 6,
             "skill": {"analysis": 0.9, "writing": 0.9, "extraction": 0.55}},
    "A-03": {"checkpoint": "mock:hermes-small-a", "capacity": 4,
             "skill": {"analysis": 0.45, "writing": 0.5, "extraction": 0.9}},
    "A-04": {"checkpoint": "mock:hermes-small-b", "capacity": 4,
             "skill": {"analysis": 0.4, "writing": 0.55, "extraction": 0.85}},
}

# epoch-1 wave, then a dependent wave that becomes eligible once wave 1 is done
TASK_WAVES = [
    [
        ("T-101", "analysis", 2, [], "Analyse run-batch 12 against [[eval-schema-v3]]."),
        ("T-102", "analysis", 2, [], "Analyse run-batch 13 against [[eval-schema-v3]]."),
        ("T-103", "extraction", 1, [], "Extract tables noted in [[run-batch-11-postmortem]]."),
        ("T-104", "extraction", 1, [], "Extract appendix rows, cf [[run-batch-11-postmortem]]."),
        ("T-105", "writing", 2, [], "Draft methods section from [[eval-schema-v3]]."),
    ],
    [
        ("T-201", "writing", 2, ["T-101", "T-102"],
         "Write the comparison memo from both analyses, see [[eval-schema-v3]]."),
        ("T-202", "extraction", 1, ["T-103"],
         "Normalise the extracted tables per [[eval-schema-v3]]."),
        ("T-203", "analysis", 2, ["T-104"],
         "Sanity-check appendix rows against [[run-batch-11-postmortem]]."),
    ],
]


def seed_vault(root: Path) -> Vault:
    vault = Vault(root / "vault")
    for aid, spec in AGENT_SKILLS.items():
        vault.write_agent(AgentProfile(id=aid, model_checkpoint=spec["checkpoint"],
                                       capacity=spec["capacity"]))
    for wave in TASK_WAVES:
        for tid, cat, effort, deps, body in wave:
            vault.write_task(TaskCard(id=tid, title=tid, category=cat, effort=effort,
                                      status="eligible", depends_on=deps, body=body,
                                      created="2026-07-12"))
    (vault.root / "postmortems" / "eval-schema-v3.md").write_text(
        "Schema v3: columns pass@1, pass@10, seed. Related: [[run-batch-11-postmortem]].",
        encoding="utf-8")
    (vault.root / "postmortems" / "run-batch-11-postmortem.md").write_text(
        "Batch 11 had truncated rows; always re-count before normalising.",
        encoding="utf-8")
    return vault


def make_harnesses(telemetry_path: Path):
    harnesses = {}
    for aid, spec in AGENT_SKILLS.items():
        client = MockModelClient(spec["skill"], seed=hash(aid) % 2**31,
                                 malformed_rate=0.08, checkpoint=spec["checkpoint"])
        writer = TelemetryWriter(telemetry_path, aid, spec["checkpoint"])
        harnesses[aid] = (client, writer)
    return harnesses


def warmup(vault: Vault, harnesses, telemetry_path: Path, rounds: int = 12) -> None:
    """Bootstrap telemetry: every agent attempts every category a few times on
    throwaway warmup tasks, so the registry has real profiles before epoch 1."""
    print(f"-- warm-up: {rounds} rounds x {len(harnesses)} agents ...")
    for r in range(rounds):
        for aid, (client, writer) in harnesses.items():
            for cat in ("analysis", "writing", "extraction"):
                card = TaskCard(id=f"W-{aid}-{cat}-{r}", category=cat,
                                title="warmup", status="assigned",
                                body="Warmup drill, see [[eval-schema-v3]].")
                run_task(vault, card, client, writer,
                         HarnessLimits(max_steps=6, context_budget_tokens=800))
    events_count = sum(1 for _ in telemetry_path.open(encoding="utf-8"))
    print(f"   telemetry events written: {events_count}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mirror", default="sa",
                        choices=["qaoa_sim", "sa", "off"],
                        help="qaoa_sim is exact-statevector and slow above ~16 "
                             "qubits; over budget it falls back classically, "
                             "which is itself the §4.1 contract demonstrated")
    parser.add_argument("--epochs", type=int, default=3)
    args = parser.parse_args()

    if DEMO_ROOT.exists():
        shutil.rmtree(DEMO_ROOT)
    DEMO_ROOT.mkdir(parents=True)
    telemetry_path = DEMO_ROOT / "telemetry" / "events.jsonl"
    mirror_log = DEMO_ROOT / "telemetry" / "quantum_mirror_log.jsonl"

    vault = seed_vault(DEMO_ROOT)
    harnesses = make_harnesses(telemetry_path)
    warmup(vault, harnesses, telemetry_path)

    def dispatch(agent: AgentProfile, task: TaskCard) -> bool:
        client, writer = harnesses[agent.id]
        outcome = run_task(vault, task, client, writer)
        return outcome.success

    total_optimized = total_greedy = 0.0
    mirrors_started = 0
    for epoch in range(1, args.epochs + 1):
        registry = Registry.from_telemetry(telemetry_path)
        registry.sync_to_vault(vault)
        eligible = vault.eligible_tasks()
        if not eligible:
            print(f"\n== epoch {epoch}: idle (no eligible tasks)")
            continue

        inst = build_instance(vault, registry, vault.agents(), eligible)
        _, greedy_util, greedy_ok = greedy_baseline(inst)

        report = run_epoch(
            vault, registry, epoch=epoch, dispatch=dispatch,
            quantum_mirror=args.mirror != "off", mirror_backend=args.mirror,
            mirror_log=mirror_log, mirror_budget_s=120,
        )
        res = report.result
        mirrors_started += 1 if report.mirror_started else 0
        total_optimized += res.objective_utility
        total_greedy += greedy_util if greedy_ok else 0.0
        print(f"\n== epoch {epoch}: {report.num_tasks} tasks, {report.num_agents} agents, "
              f"N={report.num_vars} qubits")
        print(f"   backend={res.backend}  energy={res.energy:+.4f}  "
              f"utility={res.objective_utility:.4f}  wall={res.wall_ms}ms  "
              f"feasible={res.feasible}")
        print(f"   greedy incumbent utility={greedy_util:.4f}  "
              f"(optimizer edge {res.objective_utility - greedy_util:+.4f})")
        print(f"   assignment: { {a: t for a, t in report.dispatched.items()} }")
        print(f"   decision record: {report.decision_path.name}")
        print(f"   quantum mirror: {'started (async)' if report.mirror_started else 'skipped'}")

    # give the last mirror a moment, then report agreement (§5.7)
    if args.mirror != "off" and mirrors_started:
        for _ in range(600):
            done = (mirror_log.exists()
                    and len(mirror_log.read_text(encoding="utf-8").splitlines())
                    >= mirrors_started)
            if done:
                break
            time.sleep(0.5)
        if mirror_log.exists():
            print("\n-- quantum mirror log:")
            for line in mirror_log.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                print(f"   epoch {rec['epoch']}: backend={rec['backend']} "
                      f"utility={rec['objective_utility']:.4f} "
                      f"feasible={rec['feasible']} "
                      f"raw_feas={rec['meta'].get('raw_feasibility', '')}")

    done = sum(1 for c in vault.tasks("done"))
    failed = sum(1 for c in vault.tasks("failed"))
    print(f"\n-- fleet outcome: {done} done, {failed} failed, "
          f"{len(vault.decisions())} decision records in the vault")
    print(f"-- aggregate utility: optimized {total_optimized:.3f} "
          f"vs greedy {total_greedy:.3f}")
    print(f"-- artifacts under {DEMO_ROOT}")


if __name__ == "__main__":
    main()
