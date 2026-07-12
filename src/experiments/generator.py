"""Instance generator (thesis §5.2): sixty instances across five size tiers,
utilities drawn from distributions FITTED to the live registry rather than
uniform noise — real utility matrices are structured (one agent dominates a
category) and uniform instances flatter samplers. Affinity graphs are sampled
from the vault's link-overlap distribution (sparse, clustered); 30% of
instances carry one exclusion pair per four tasks. Optima are certified by
CBC, and by brute force where N <= 22 ('cheap insurance').
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..qubo.builder import Instance, slack_coeffs
from ..registry.profiles import Registry

# (name, m agents, n tasks) — Table 3.2 rows 1-4 plus the N=54 tier
SIZE_TIERS = [
    ("N14", 2, 3),
    ("N24", 3, 4),
    ("N40", 4, 6),
    ("N54", 5, 8),
    ("N84", 6, 10),
]
EXCLUSION_INSTANCE_RATE = 0.30
AFFINITY_THRESHOLD = 0.2


@dataclass
class FittedParams:
    """Distribution parameters, refittable from a live deployment (§6.4:
    'the generator and fitted parameters ship with the repository')."""
    u_dominant_mean: float = 0.78     # dominant (agent, category) utility
    u_dominant_spread: float = 0.10
    u_other_mean: float = 0.35
    u_other_spread: float = 0.15
    n_categories: int = 3
    affinity_values: list[float] = field(default_factory=lambda: [0.25, 0.33, 0.5, 0.6])
    affinity_pair_rate: float = 0.25  # fraction of same-group pairs that link
    capacity_range: tuple[int, int] = (4, 12)   # §3.4 deployment capacities
    effort_range: tuple[int, int] = (1, 3)

    @classmethod
    def from_registry(cls, registry: Registry, vault=None) -> "FittedParams":
        """Refit utility structure from real profiles and, when a vault is
        given, the affinity value distribution from real link overlaps."""
        params = cls()
        by_cat: dict[str, list[float]] = {}
        norm = registry._cost_norm()
        for (agent, cat) in registry.profiles:
            by_cat.setdefault(cat, []).append(registry.utility(agent, cat, norm))
        if by_cat:
            dominants = [max(v) for v in by_cat.values() if v]
            others = [u for v in by_cat.values() for u in sorted(v)[:-1]]
            if dominants:
                params.u_dominant_mean = sum(dominants) / len(dominants)
            if others:
                params.u_other_mean = sum(others) / len(others)
            params.n_categories = max(2, len(by_cat))
        if vault is not None:
            tasks = vault.tasks()
            aff = vault.affinity(tasks, threshold=AFFINITY_THRESHOLD)
            if aff:
                params.affinity_values = sorted(aff.values())
        return params


@dataclass
class GeneratedInstance:
    name: str
    tier: str
    instance: Instance
    num_vars: int
    optimum_utility: float | None = None   # certified by CBC after generation
    seed: int = 0


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def generate_instance(tier: str, m: int, n: int, seed: int,
                      params: FittedParams | None = None,
                      with_exclusions: bool = False) -> GeneratedInstance:
    p = params or FittedParams()
    rng = random.Random(seed)

    categories = [rng.randrange(p.n_categories) for _ in range(n)]
    dominant = {c: rng.randrange(m) for c in range(p.n_categories)}
    utilities = [[0.0] * n for _ in range(m)]
    for i in range(m):
        for j in range(n):
            if dominant[categories[j]] == i:
                u = rng.gauss(p.u_dominant_mean, p.u_dominant_spread)
            else:
                u = rng.gauss(p.u_other_mean, p.u_other_spread)
            utilities[i][j] = round(_clip01(u), 3)

    weights = [rng.randint(*p.effort_range) for _ in range(n)]
    # capacities with headroom so coverage is satisfiable but tight-ish
    total = sum(weights)
    capacities = []
    for i in range(m):
        base = max(p.capacity_range[0],
                   min(p.capacity_range[1], round(total / m * rng.uniform(1.1, 1.6))))
        capacities.append(base)
    while sum(capacities) < total + max(weights):   # guarantee feasibility
        capacities[capacities.index(min(capacities))] += 1

    # clustered affinity: same-category pairs link with fitted values
    affinity: dict[tuple[int, int], float] = {}
    for j in range(n):
        for k in range(j + 1, n):
            if categories[j] == categories[k] and rng.random() < p.affinity_pair_rate:
                a = rng.choice(p.affinity_values)
                if a >= AFFINITY_THRESHOLD:
                    affinity[(j, k)] = a

    exclusions: set[tuple[int, int]] = set()
    if with_exclusions:
        for _ in range(max(1, n // 4)):             # one pair per four tasks
            j, k = sorted(rng.sample(range(n), 2))
            if (j, k) not in affinity:
                exclusions.add((j, k))

    inst = Instance(utilities=utilities, weights=weights, capacities=capacities,
                    affinity=affinity, exclusions=exclusions, alpha=0.5)
    num_vars = m * n + sum(len(slack_coeffs(c)) for c in capacities)
    return GeneratedInstance(name=f"{tier}-s{seed}", tier=tier,
                             instance=inst, num_vars=num_vars, seed=seed)


def generate_suite(per_tier: int = 10, params: FittedParams | None = None,
                   tiers: list[tuple[str, int, int]] | None = None,
                   certify: bool = True, seed0: int = 100) -> list[GeneratedInstance]:
    """The §5.2 suite. When certify=True each instance's optimum is certified
    by CBC (raises if CBC and brute force ever disagree on N <= 22)."""
    from ..solver.service import solve_qubo
    from ..qubo.builder import build_qubo, brute_force
    from ..solver.types import choose_weights

    out = []
    for (tier, m, n) in (tiers or SIZE_TIERS):
        for r in range(per_tier):
            seed = seed0 + 1000 * len(out) + r
            gi = generate_instance(tier, m, n, seed, params,
                                   with_exclusions=(r / per_tier) < EXCLUSION_INSTANCE_RATE)
            if certify:
                res = solve_qubo(gi.instance, backend="exact", budget_s=120)
                if not (res.optimal and res.feasible):
                    raise RuntimeError(f"CBC failed to certify {gi.name}")
                gi.optimum_utility = res.objective_utility
                if gi.num_vars <= 22:                # brute-force cross-check
                    w = choose_weights(gi.instance)
                    Q, off, nv, _ = build_qubo(gi.instance, w["l1"], w["l2"], w["l3"])
                    e_star, _ = brute_force(Q, off, nv)
                    if abs(e_star - (-res.objective_utility)) > 1e-6:
                        raise RuntimeError(
                            f"oracle disagreement on {gi.name}: "
                            f"brute {e_star} vs CBC {-res.objective_utility}")
            out.append(gi)
    return out
