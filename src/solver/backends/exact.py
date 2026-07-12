"""CBC exact backend (thesis §4.5.1): models the CONSTRAINED problem
(3.1)-(3.4) natively in PuLP — no penalties, no slack bits. Ground-truth
oracle and production fallback.

The quadratic affinity term is linearised with standard product variables
z_ijk <= x_ij, z_ijk <= x_ik; since alpha * a_jk >= 0 the maximiser pushes z
up, so the two upper bounds suffice.
"""
from __future__ import annotations

import time

import pulp

from ...qubo.builder import Instance
from ..types import SolveResult, objective_utility


def solve_exact(inst: Instance, budget_s: float = 60.0) -> SolveResult:
    start = time.monotonic()
    prob = pulp.LpProblem("orchestration_epoch", pulp.LpMaximize)
    x = {(i, j): pulp.LpVariable(f"x_{i}_{j}", cat="Binary")
         for i in range(inst.m) for j in range(inst.n)}
    z = {(i, j, k): pulp.LpVariable(f"z_{i}_{j}_{k}", cat="Binary")
         for (j, k) in inst.affinity for i in range(inst.m)}

    prob += (
        pulp.lpSum(inst.utilities[i][j] * x[i, j] for i in range(inst.m) for j in range(inst.n))
        + pulp.lpSum(inst.alpha * a * z[i, j, k]
                     for (j, k), a in inst.affinity.items() for i in range(inst.m))
    )
    for j in range(inst.n):                                   # (3.2) coverage
        prob += pulp.lpSum(x[i, j] for i in range(inst.m)) == 1
    for i in range(inst.m):                                   # (3.3) capacity
        prob += pulp.lpSum(inst.weights[j] * x[i, j] for j in range(inst.n)) <= inst.capacities[i]
    for (j, k) in inst.exclusions:                            # (3.4) exclusion
        for i in range(inst.m):
            prob += x[i, j] + x[i, k] <= 1
    for (i, j, k), var in z.items():                          # linearisation
        prob += var <= x[i, j]
        prob += var <= x[i, k]

    status = prob.solve(pulp.PULP_CBC_CMD(msg=False, timeLimit=max(1, int(budget_s))))
    wall_ms = int((time.monotonic() - start) * 1000)
    if status != pulp.LpStatusOptimal:
        raise RuntimeError(f"CBC returned {pulp.LpStatus[status]}")

    assignment = {i: [j for j in range(inst.n) if x[i, j].value() > 0.5]
                  for i in range(inst.m)}
    util = objective_utility(inst, assignment)
    return SolveResult(
        backend="exact", energy=-util, bits=None, assignment=assignment,
        feasible=True, repaired=False, objective_utility=util, optimal=True,
        wall_ms=wall_ms, num_vars=inst.m * inst.n,
        meta={"solver": "CBC/PuLP", "status": pulp.LpStatus[status]},
    )
