"""QUBO builder for multi-agent workforce orchestration.

Implements thesis Chapter 3 exactly (Eq. 3.1-3.8):
  minimise  E(x,y) = -sum u_ij x_ij  - alpha * sum_i sum_{j<k} a_jk x_ij x_ik
                     + l1 * sum_j (1 - sum_i x_ij)^2
                     + l2 * sum_i (C_i - sum_j w_j x_ij - slack_i)^2
                     + l3 * sum_i sum_{(j,k) in excl} x_ij x_ik

Variable layout: x[i,j] -> index i*n + j, then slack bits per agent in order.
Slack expansion (thesis 3.4): coefficients 2^0..2^(R-1) plus residual
rho = C - (2^R - 1), with R = floor(log2(C)), covering exactly {0..C}.
"""
from __future__ import annotations
import itertools
import math
from dataclasses import dataclass, field


@dataclass
class Instance:
    utilities: list[list[float]]           # m x n, already clipped to [0,1]
    weights: list[int]                     # n
    capacities: list[int]                  # m
    affinity: dict[tuple[int, int], float] = field(default_factory=dict)  # (j,k) j<k
    exclusions: set[tuple[int, int]] = field(default_factory=set)          # (j,k) j<k
    alpha: float = 0.5

    @property
    def m(self) -> int: return len(self.capacities)
    @property
    def n(self) -> int: return len(self.weights)


def slack_coeffs(C: int) -> list[int]:
    """Binary expansion coefficients whose subset sums cover exactly {0..C}."""
    if C <= 0:
        return []
    R = int(math.floor(math.log2(C)))
    coeffs = [2 ** r for r in range(R)]
    coeffs.append(C - (2 ** R - 1))
    return coeffs


def penalty_bounds(inst: Instance) -> dict[str, float]:
    """Sufficient lower bounds for penalty weights (thesis 3.5).
    Use values just ABOVE these; never 'comfortably high'."""
    u_max = max(max(row) for row in inst.utilities)
    aff_max_per_task = {}
    for (j, k), a in inst.affinity.items():
        aff_max_per_task[j] = aff_max_per_task.get(j, 0.0) + inst.alpha * a
        aff_max_per_task[k] = aff_max_per_task.get(k, 0.0) + inst.alpha * a
    delta = max(
        (max(inst.utilities[i][j] for i in range(inst.m)) + aff_max_per_task.get(j, 0.0))
        for j in range(inst.n)
    )
    w_min = min(inst.weights)
    a_max = max(inst.affinity.values()) if inst.affinity else 0.0
    return {
        "l1": delta,                                   # coverage
        "l2": u_max / w_min,                           # capacity, per unit violation
        "l3": 2 * u_max + inst.alpha * a_max,          # exclusion
    }


def _add(Q: dict, i: int, j: int, v: float) -> None:
    if v == 0.0:
        return
    key = (i, j) if i <= j else (j, i)
    Q[key] = Q.get(key, 0.0) + v


def _add_squared_linear(Q: dict, terms: list[tuple[int, float]], const: float) -> float:
    """Add (const + sum c_v * x_v)^2 to Q; returns the constant offset."""
    for (v, c) in terms:
        _add(Q, v, v, c * c + 2 * const * c)   # x^2 = x for binaries
    for (v1, c1), (v2, c2) in itertools.combinations(terms, 2):
        _add(Q, v1, v2, 2 * c1 * c2)
    return const * const


def build_qubo(inst: Instance, l1: float, l2: float, l3: float):
    """Returns (Q, offset, num_vars, slack_layout).
    Q is a sparse dict {(a,b): coeff} with a<=b; total energy = x^T Q x + offset.
    """
    m, n = inst.m, inst.n
    x = lambda i, j: i * n + j
    Q: dict[tuple[int, int], float] = {}
    offset = 0.0

    # objective: -utility (diagonal)
    for i in range(m):
        for j in range(n):
            _add(Q, x(i, j), x(i, j), -inst.utilities[i][j])

    # objective: -alpha * affinity for co-located pairs
    for (j, k), a in inst.affinity.items():
        for i in range(m):
            _add(Q, x(i, j), x(i, k), -inst.alpha * a)

    # coverage: l1 * (1 - sum_i x_ij)^2
    for j in range(n):
        terms = [(x(i, j), -1.0) for i in range(m)]
        offset += l1 * _add_squared_linear({}, [], 0)  # no-op, keep structure clear
        # expand with weight l1:
        scaled = [(v, c) for v, c in terms]
        # (1 + sum(-x))^2 with overall factor l1:
        tmp: dict = {}
        c0 = _add_squared_linear(tmp, scaled, 1.0)
        for k_, v_ in tmp.items():
            _add(Q, k_[0], k_[1], l1 * v_)
        offset += l1 * c0

    # capacity: l2 * (C_i - sum_j w_j x_ij - sum_r s_r y_ir)^2
    slack_layout = {}
    next_var = m * n
    for i in range(m):
        coeffs = slack_coeffs(inst.capacities[i])
        slack_vars = list(range(next_var, next_var + len(coeffs)))
        slack_layout[i] = list(zip(slack_vars, coeffs))
        next_var += len(coeffs)
        terms = [(x(i, j), -float(inst.weights[j])) for j in range(n)]
        terms += [(v, -float(c)) for v, c in slack_layout[i]]
        tmp = {}
        c0 = _add_squared_linear(tmp, terms, float(inst.capacities[i]))
        for k_, v_ in tmp.items():
            _add(Q, k_[0], k_[1], l2 * v_)
        offset += l2 * c0

    # exclusion: l3 * x_ij x_ik
    for (j, k) in inst.exclusions:
        for i in range(m):
            _add(Q, x(i, j), x(i, k), l3)

    return Q, offset, next_var, slack_layout


def energy(Q: dict, offset: float, bits: tuple[int, ...]) -> float:
    e = offset
    for (a, b), c in Q.items():
        e += c * bits[a] * bits[b]
    return e


def brute_force(Q: dict, offset: float, num_vars: int):
    """Exact minimisation by enumeration. Reference oracle for N <= ~22.
    Returns (min_energy, list_of_all_minimising_bitstrings)."""
    if num_vars > 22:
        raise ValueError("brute_force limited to 22 vars; use CBC backend instead")
    best_e, best = math.inf, []
    for bits in itertools.product((0, 1), repeat=num_vars):
        e = energy(Q, offset, bits)
        if e < best_e - 1e-9:
            best_e, best = e, [bits]
        elif abs(e - best_e) <= 1e-9:
            best.append(bits)
    return best_e, best


def decode(bits: tuple[int, ...], m: int, n: int) -> dict[int, list[int]]:
    """Assignment view: agent -> [tasks], ignoring slack bits."""
    return {i: [j for j in range(n) if bits[i * n + j] == 1] for i in range(m)}
