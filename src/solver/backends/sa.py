"""Simulated annealing on the QUBO (thesis §4.5.1): single-spin Metropolis
with a geometric temperature schedule, ~1e4 sweeps. The honest classical
baseline — 'a 30-line Metropolis loop achieves r >= 0.98 in milliseconds'
(§5.3) — so it must operate on the identical energy landscape the quantum
backend sees.
"""
from __future__ import annotations

import math
import random
import time

from ...qubo.builder import energy as qubo_energy


def solve_sa(Q: dict, offset: float, num_vars: int, sweeps: int = 10_000,
             seed: int = 0, t_factor: float = 0.999, budget_s: float = 30.0,
             restarts: int = 1) -> tuple[list[int], float, dict]:
    """Returns (best_bits, best_energy, meta). Pure QUBO — no repair here;
    the service layer validates and repairs like it does for QAOA samples."""
    rng = random.Random(seed)
    # adjacency for O(deg) delta-E: diag h[v], neighbours adj[v] = [(u, c)]
    h = [0.0] * num_vars
    adj: list[list[tuple[int, float]]] = [[] for _ in range(num_vars)]
    for (a, b), c in Q.items():
        if a == b:
            h[a] += c
        else:
            adj[a].append((b, c))
            adj[b].append((a, c))

    scale = max((abs(c) for c in Q.values()), default=1.0)
    t_start, t_end = 2.0 * scale, 1e-3 * scale
    start = time.monotonic()
    best_bits: list[int] = [0] * num_vars
    best_e = math.inf

    for r in range(max(1, restarts)):
        bits = [rng.randint(0, 1) for _ in range(num_vars)]
        e = qubo_energy(Q, offset, tuple(bits))
        if e < best_e:
            best_e, best_bits = e, bits[:]
        t = t_start
        ratio = (t_end / t_start) ** (1.0 / max(1, sweeps))
        for _ in range(sweeps):
            if time.monotonic() - start > budget_s:
                break
            for v in range(num_vars):
                local = h[v] + sum(c * bits[u] for u, c in adj[v])
                delta = (1 - 2 * bits[v]) * local
                if delta <= 0 or rng.random() < math.exp(-delta / t):
                    bits[v] ^= 1
                    e += delta
                    if e < best_e - 1e-12:
                        best_e, best_bits = e, bits[:]
            t *= ratio
        if time.monotonic() - start > budget_s:
            break

    meta = {"sweeps": sweeps, "restarts": restarts, "seed": seed,
            "t_start": t_start, "t_end": t_end}
    return best_bits, best_e, meta
