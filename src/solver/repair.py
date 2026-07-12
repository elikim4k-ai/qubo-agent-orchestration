"""Validation and greedy repair (thesis §4.5.2 step 5).

The orchestrator must own validation regardless of encoding (§5.6), so the
checks here are on the CONSTRAINED problem (3.2)-(3.4), never on penalty
energies. Repair: resolve one-hot violations by keeping the best-marginal
copy, evict over-capacity tasks by worst marginal utility, then greedily
place every unassigned task where it fits best. Deterministic.
"""
from __future__ import annotations

from ..qubo.builder import Instance


def decode_assignment(bits: list[int] | tuple[int, ...], inst: Instance
                      ) -> dict[int, list[int]]:
    """Assignment view of a raw bitstring; slack bits are discarded."""
    return {i: [j for j in range(inst.n) if bits[i * inst.n + j]]
            for i in range(inst.m)}


def violations(inst: Instance, assignment: dict[int, list[int]]) -> dict[str, list]:
    """Constraint violations of (3.2)-(3.4); all-empty means feasible."""
    counts = [0] * inst.n
    for tasks in assignment.values():
        for j in tasks:
            counts[j] += 1
    coverage = [j for j, c in enumerate(counts) if c != 1]
    capacity = [i for i, tasks in assignment.items()
                if sum(inst.weights[j] for j in tasks) > inst.capacities[i]]
    exclusion = [(i, j, k) for i, tasks in assignment.items()
                 for (j, k) in inst.exclusions
                 if j in tasks and k in tasks]
    return {"coverage": coverage, "capacity": capacity, "exclusion": exclusion}


def is_feasible(inst: Instance, assignment: dict[int, list[int]]) -> bool:
    return not any(violations(inst, assignment).values())


def _marginal(inst: Instance, assignment: dict[int, list[int]], i: int, j: int) -> float:
    """Marginal utility of task j on agent i given the rest of i's load."""
    gain = inst.utilities[i][j]
    on_agent = set(assignment[i]) - {j}
    for (a, b), v in inst.affinity.items():
        if (a == j and b in on_agent) or (b == j and a in on_agent):
            gain += inst.alpha * v
    return gain


def _fits(inst: Instance, assignment: dict[int, list[int]], i: int, j: int) -> bool:
    load = sum(inst.weights[t] for t in assignment[i])
    if load + inst.weights[j] > inst.capacities[i]:
        return False
    on_agent = set(assignment[i])
    return not any((a == j and b in on_agent) or (b == j and a in on_agent)
                   for (a, b) in inst.exclusions)


def greedy_repair(inst: Instance, assignment: dict[int, list[int]]
                  ) -> tuple[dict[int, list[int]], bool]:
    """Returns (repaired_assignment, changed). May still be infeasible if no
    agent can host a task; the caller reports that honestly."""
    asg = {i: list(tasks) for i, tasks in assignment.items()}
    for i in range(inst.m):
        asg.setdefault(i, [])
    changed = False

    # 1. one-hot violations: keep the copy with the best marginal utility
    owners: dict[int, list[int]] = {}
    for i, tasks in asg.items():
        for j in tasks:
            owners.setdefault(j, []).append(i)
    for j, agents in owners.items():
        if len(agents) > 1:
            best = max(agents, key=lambda i: _marginal(inst, asg, i, j))
            for i in agents:
                if i != best:
                    asg[i].remove(j)
                    changed = True

    # 2. exclusion violations: evict the worse-marginal member of the pair
    for (j, k) in sorted(inst.exclusions):
        for i in range(inst.m):
            if j in asg[i] and k in asg[i]:
                drop = min((j, k), key=lambda t: _marginal(inst, asg, i, t))
                asg[i].remove(drop)
                changed = True

    # 3. capacity: evict worst-marginal tasks until each agent fits
    for i in range(inst.m):
        while sum(inst.weights[t] for t in asg[i]) > inst.capacities[i]:
            drop = min(asg[i], key=lambda t: _marginal(inst, asg, i, t))
            asg[i].remove(drop)
            changed = True

    # 4. place unassigned tasks greedily (heaviest first) where they fit best
    assigned = {j for tasks in asg.values() for j in tasks}
    missing = sorted((j for j in range(inst.n) if j not in assigned),
                     key=lambda j: -inst.weights[j])
    for j in missing:
        candidates = [i for i in range(inst.m) if _fits(inst, asg, i, j)]
        if not candidates:
            continue  # genuinely unplaceable this epoch
        best = max(candidates, key=lambda i: _marginal(inst, asg, i, j))
        asg[best].append(j)
        changed = True

    return {i: sorted(t) for i, t in asg.items()}, changed


def assignment_to_bits(inst: Instance, assignment: dict[int, list[int]],
                       num_vars: int, slack_layout: dict) -> list[int]:
    """Bitstring for an assignment, with slack bits set to the residual
    capacity so the capacity penalty is exactly zero when feasible."""
    bits = [0] * num_vars
    for i, tasks in assignment.items():
        for j in tasks:
            bits[i * inst.n + j] = 1
    for i in range(inst.m):
        residual = inst.capacities[i] - sum(inst.weights[j] for j in assignment.get(i, []))
        residual = max(0, residual)
        # greedy fill over the slack coefficients (they cover {0..C} exactly)
        for var, coeff in sorted(slack_layout[i], key=lambda vc: -vc[1]):
            if coeff <= residual:
                bits[var] = 1
                residual -= coeff
    return bits
