"""Experiments: generator structure/certification (§5.2) and benchmark
metrics (§5.1) on a small fast suite."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import csv

from src.experiments import (
    FittedParams, generate_instance, generate_suite, greedy_baseline, run_benchmark,
)
from src.solver.repair import is_feasible


def test_generated_instances_are_structured_and_feasible():
    gi = generate_instance("N24", 3, 4, seed=7)
    inst = gi.instance
    assert len(inst.utilities) == 3 and len(inst.weights) == 4
    assert all(0.0 <= u <= 1.0 for row in inst.utilities for u in row)
    assert sum(inst.capacities) >= sum(inst.weights)     # coverage satisfiable
    assert all(a >= 0.2 for a in inst.affinity.values()) # threshold respected


def test_exclusion_rate_one_pair_per_four_tasks():
    gi = generate_instance("N40", 4, 8, seed=3, with_exclusions=True)
    assert len(gi.instance.exclusions) >= 2              # 8 tasks -> >= 2 pairs


def test_suite_certifies_optima_with_oracle_crosscheck():
    suite = generate_suite(per_tier=2, tiers=[("N14", 2, 3)], certify=True)
    assert len(suite) == 2
    for gi in suite:
        assert gi.optimum_utility is not None and gi.optimum_utility > 0
        assert gi.num_vars <= 22                         # brute force ran too


def test_fitted_params_from_registry():
    from src.registry import Registry
    reg = Registry()
    for i in range(15):
        reg.ingest([
            {"ts": "2026-07-12T00:00:00Z", "agent_id": "A-1", "task_id": f"T-{i}",
             "category": "analysis", "event": "task_done", "outcome": "success",
             "tokens_prompt": 500, "tokens_completion": 100, "duration_ms": 900},
        ])
    p = FittedParams.from_registry(reg)
    assert 0.0 < p.u_dominant_mean <= 1.0


def test_greedy_baseline_never_beats_the_optimum():
    suite = generate_suite(per_tier=3, tiers=[("N14", 2, 3), ("N24", 3, 4)],
                           certify=True)
    for gi in suite:
        asg, util, feasible = greedy_baseline(gi.instance)
        if feasible:
            assert util <= gi.optimum_utility + 1e-9


def test_greedy_is_beatable_by_the_optimizer():
    # arrival-order trap: greedy grabs 0.9 for task 0 and forces task 1 to 0.1;
    # the optimizer swaps to 0.5 + 0.85. This gap is the thesis's payoff (§5.1).
    from src.qubo.builder import Instance
    from src.solver import solve_qubo
    inst = Instance(utilities=[[0.9, 0.85], [0.5, 0.1]],
                    weights=[2, 2], capacities=[2, 2])
    asg, util, feasible = greedy_baseline(inst)
    assert feasible and abs(util - 1.0) < 1e-9
    res = solve_qubo(inst, backend="exact", budget_s=30)
    assert abs(res.objective_utility - 1.35) < 1e-9


def test_benchmark_writes_tables(tmp_path):
    suite = generate_suite(per_tier=2, tiers=[("N14", 2, 3)], certify=True)
    detail, summary = run_benchmark(suite, backends=["exact", "sa", "greedy"],
                                    restarts=2, budget_s=30,
                                    results_dir=tmp_path)
    rows = list(csv.DictReader(detail.open(encoding="utf-8")))
    assert {r["backend"] for r in rows} == {"exact", "sa", "greedy"}
    exact_rows = [r for r in rows if r["backend"] == "exact"]
    assert all(abs(float(r["approx_ratio"]) - 1.0) < 1e-6 for r in exact_rows)
    srows = list(csv.DictReader(summary.open(encoding="utf-8")))
    assert any(r["backend"] == "sa" and float(r["mean_r"]) > 0.9 for r in srows)
