"""Benchmark runner (thesis §5.1/§5.3): produces the measured replacements
for the placeholder Tables 5.1/5.2.

Baselines: CBC exact (ground truth), SA on the identical QUBO, and a greedy
dispatcher that mimics standard agent frameworks — assign each task, in
arrival order, to the highest-utility agent with remaining capacity. Greedy
is the incumbent practice; beating it is the practically meaningful bar.

Metrics per run: feasibility (raw and repaired), approximation ratio
r = utility / CBC optimum (r <= 1, higher is better), and time-to-solution.
Output: results/table_5_1.csv (per-run rows) + results/table_5_1_summary.csv.
"""
from __future__ import annotations

import csv
import statistics
import time
from pathlib import Path

from ..qubo.builder import Instance
from ..solver.repair import is_feasible
from ..solver.service import solve_qubo
from ..solver.types import objective_utility
from .generator import GeneratedInstance

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"


def greedy_baseline(inst: Instance) -> tuple[dict[int, list[int]], float, bool]:
    """The incumbent: arrival order, best available agent (§5.1)."""
    asg: dict[int, list[int]] = {i: [] for i in range(inst.m)}
    load = [0] * inst.m
    for j in range(inst.n):
        candidates = [
            i for i in range(inst.m)
            if load[i] + inst.weights[j] <= inst.capacities[i]
            and not any((a == j and b in asg[i]) or (b == j and a in asg[i])
                        for (a, b) in inst.exclusions)
        ]
        if not candidates:
            continue
        best = max(candidates, key=lambda i: inst.utilities[i][j])
        asg[best].append(j)
        load[best] += inst.weights[j]
    return asg, objective_utility(inst, asg), is_feasible(inst, asg)


def _run_one(gi: GeneratedInstance, backend: str, budget_s: float,
             qaoa_p: int, restart: int) -> dict:
    start = time.monotonic()
    if backend == "greedy":
        asg, util, feasible = greedy_baseline(gi.instance)
        row = {"feasible": feasible, "repaired": False, "raw_feasibility": "",
               "utility": util, "backend_used": "greedy"}
    else:
        res = solve_qubo(gi.instance, backend=backend, budget_s=budget_s,
                         meta={"p": qaoa_p, "instance_id": gi.name,
                               "restart": restart})
        row = {"feasible": res.feasible, "repaired": res.repaired,
               "raw_feasibility": res.meta.get("raw_feasibility", ""),
               "utility": res.objective_utility, "backend_used": res.backend}
    wall_ms = int((time.monotonic() - start) * 1000)
    r = (row["utility"] / gi.optimum_utility) if gi.optimum_utility else ""
    return {
        "instance": gi.name, "tier": gi.tier, "num_vars": gi.num_vars,
        "backend": backend, "restart": restart,
        "optimum_utility": gi.optimum_utility, "approx_ratio": r,
        "tts_ms": wall_ms, **row,
    }


def run_benchmark(instances: list[GeneratedInstance],
                  backends: list[str] = ("exact", "sa", "greedy"),
                  restarts: int = 3, budget_s: float = 60.0, qaoa_p: int = 2,
                  results_dir: Path | None = None,
                  qaoa_var_cap: int = 24) -> tuple[Path, Path]:
    """Every instance x backend x restart; deterministic backends run once.
    QAOA backends are skipped (and recorded as skipped) above qaoa_var_cap —
    a bounded sweep is reported, never silently truncated."""
    results_dir = results_dir or RESULTS_DIR
    results_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    skipped: list[str] = []
    for gi in instances:
        for backend in backends:
            if backend.startswith("qaoa") and gi.num_vars > qaoa_var_cap:
                skipped.append(f"{gi.name}:{backend}")
                continue
            n_runs = restarts if backend in ("sa", "qaoa_sim", "qaoa_ibm") else 1
            for restart in range(n_runs):
                rows.append(_run_one(gi, backend, budget_s, qaoa_p, restart))

    detail = results_dir / "table_5_1.csv"
    with detail.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # aggregate: mean +/- std approximation ratio and feasibility per tier
    summary_rows = []
    tiers = sorted({r["tier"] for r in rows}, key=lambda t: int(t[1:]))
    for tier in tiers:
        for backend in backends:
            sel = [r for r in rows if r["tier"] == tier and r["backend"] == backend]
            if not sel:
                continue
            ratios = [r["approx_ratio"] for r in sel if r["approx_ratio"] != ""]
            raw = [r["raw_feasibility"] for r in sel if r["raw_feasibility"] != ""]
            summary_rows.append({
                "tier": tier, "backend": backend, "runs": len(sel),
                "mean_r": round(statistics.mean(ratios), 4) if ratios else "",
                "std_r": round(statistics.stdev(ratios), 4) if len(ratios) > 1 else 0.0,
                "feasible_rate": round(sum(1 for r in sel if r["feasible"]) / len(sel), 4),
                "mean_raw_feasibility": round(statistics.mean(raw), 4) if raw else "",
                "median_tts_ms": statistics.median(r["tts_ms"] for r in sel),
            })
    summary = results_dir / "table_5_1_summary.csv"
    with summary.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)
    if skipped:
        (results_dir / "skipped.txt").write_text(
            "\n".join(skipped) + "\n", encoding="utf-8")
    return detail, summary
