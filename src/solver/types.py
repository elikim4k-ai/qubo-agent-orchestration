"""Shared solver contract (thesis §4.1: 'the quantum solver must be boring
from the outside'). Every backend returns the same SolveResult; the
orchestrator neither knows nor cares which backend answered.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..qubo.builder import Instance, penalty_bounds

# §3.5 recipe: weights just above the derived bounds, never 'comfortably high'
WEIGHT_FACTORS = {"l1": 2.0, "l2": 1.5, "l3": 2.0}


class BackendUnavailable(RuntimeError):
    """Backend cannot run here (missing package, no credentials, over size)."""


def choose_weights(inst: Instance) -> dict[str, float]:
    bounds = penalty_bounds(inst)
    return {k: WEIGHT_FACTORS[k] * max(v, 1e-9) for k, v in bounds.items()}


def objective_utility(inst: Instance, assignment: dict[int, list[int]]) -> float:
    """Utility form of (3.1): sum u + alpha * affinity of co-located pairs."""
    total = 0.0
    for i, tasks in assignment.items():
        for j in tasks:
            total += inst.utilities[i][j]
        on_agent = set(tasks)
        for (j, k), a in inst.affinity.items():
            if j in on_agent and k in on_agent:
                total += inst.alpha * a
    return total


@dataclass
class SolveResult:
    backend: str
    energy: float                      # QUBO energy of the returned bits
    bits: list[int] | None             # full bitstring incl. slack (None = n/a)
    assignment: dict[int, list[int]]   # agent index -> task indices
    feasible: bool
    repaired: bool
    objective_utility: float
    optimal: bool                      # proven optimal (exact backends only)
    wall_ms: int
    num_vars: int
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "backend": self.backend, "energy": self.energy, "bits": self.bits,
            "assignment": {str(k): v for k, v in self.assignment.items()},
            "feasible": self.feasible, "repaired": self.repaired,
            "objective_utility": self.objective_utility, "optimal": self.optimal,
            "wall_ms": self.wall_ms, "num_vars": self.num_vars, "meta": self.meta,
        }
