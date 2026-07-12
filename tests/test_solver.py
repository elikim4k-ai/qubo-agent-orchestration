"""Solver service: identical schema across backends, exact agrees with the
brute-force oracle on the worked example, SA finds the optimum, repair fixes
infeasible samples, and the fallback contract holds (thesis §4.5, §4.1)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pytest

from src.qubo.builder import Instance, build_qubo, brute_force
from src.solver import (
    choose_weights, greedy_repair, is_feasible, objective_utility, solve_qubo,
    violations,
)
from src.solver.types import BackendUnavailable
from tests.test_qubo_worked_example import make_worked_example


def test_choose_weights_sit_just_above_bounds():
    from src.qubo.builder import penalty_bounds
    inst = make_worked_example()
    w = choose_weights(inst)
    b = penalty_bounds(inst)
    for key in ("l1", "l2", "l3"):
        assert b[key] < w[key] <= 4 * max(b[key], 1e-9)  # inside the safe band (§5.5)


def test_exact_matches_brute_force_oracle():
    inst = make_worked_example()
    res = solve_qubo(inst, backend="exact", budget_s=30)
    assert res.backend == "exact" and res.optimal and res.feasible
    assert abs(res.objective_utility - 1.9) < 1e-6      # thesis §3.7 optimum
    # QUBO energy of the returned bits equals -utility (penalties vanish)
    assert abs(res.energy - (-1.9)) < 1e-6
    Q, off, nvars, _ = build_qubo(inst, l1=3.0, l2=2.0, l3=4.0)
    e_star, _ = brute_force(Q, off, nvars)
    assert abs(e_star - (-1.9)) < 1e-9                  # oracle agrees


def test_brute_backend_reports_degeneracy():
    inst = make_worked_example()
    res = solve_qubo(inst, backend="brute", budget_s=30)
    assert res.optimal and res.feasible
    assert res.meta["degenerate_optima"] == 2           # the two §3.7 optima
    assert abs(res.objective_utility - 1.9) < 1e-9


def test_sa_reaches_the_optimum_on_worked_example():
    inst = make_worked_example()
    res = solve_qubo(inst, backend="sa", budget_s=30)
    assert res.backend == "sa" and res.feasible
    assert abs(res.objective_utility - 1.9) < 1e-9      # SA is quietly excellent (§5.3)


def test_identical_response_schema_across_backends():
    inst = make_worked_example()
    dicts = [solve_qubo(inst, backend=b, budget_s=30).to_dict()
             for b in ("exact", "sa", "brute")]
    keys = {frozenset(d) for d in dicts}
    assert len(keys) == 1                               # §4.1: boring from the outside


def test_greedy_repair_fixes_all_three_violation_kinds():
    inst = Instance(
        utilities=[[0.9, 0.8, 0.5], [0.4, 0.3, 0.7]],
        weights=[2, 2, 1], capacities=[3, 3],
        exclusions={(1, 2)},
    )
    broken = {0: [0, 1, 2], 1: [0]}   # over-capacity, double-assign, exclusion
    v = violations(inst, broken)
    assert v["coverage"] and v["capacity"] and v["exclusion"]
    fixed, changed = greedy_repair(inst, broken)
    assert changed and is_feasible(inst, fixed)


def test_unknown_backend_falls_back_classically_and_never_raises():
    inst = make_worked_example()
    res = solve_qubo(inst, backend="nonexistent", budget_s=10)
    assert res.feasible and res.backend in ("exact", "sa", "greedy_fallback")
    assert any("nonexistent" in e for e in res.meta["fallback_from"])


def test_qaoa_sim_on_worked_example():
    pytest.importorskip("qiskit")
    inst = make_worked_example()
    res = solve_qubo(inst, backend="qaoa_sim", budget_s=600,
                     meta={"p": 1})
    assert res.backend == "qaoa_sim" and res.feasible
    assert 0.0 <= res.meta["raw_feasibility"] <= 1.0
    # repaired-QAOA must at least beat doing nothing; typically hits 1.9
    assert res.objective_utility >= 1.7


def test_qaoa_sim_size_cap_triggers_backend_unavailable():
    pytest.importorskip("qiskit")
    from src.solver.backends.qaoa import solve_qaoa_sim
    with pytest.raises(BackendUnavailable):
        solve_qaoa_sim({}, 0.0, 40)


def test_ising_conversion_preserves_energies():
    pytest.importorskip("qiskit")
    from src.solver.backends.qaoa import to_ising
    from src.qubo.builder import energy
    import itertools
    Q = {(0, 0): -1.0, (0, 1): 2.0, (1, 1): 0.5, (1, 2): -0.7}
    h, J, const = to_ising(Q, offset=0.3)
    for bits in itertools.product((0, 1), repeat=3):
        z = [1 - 2 * b for b in bits]
        e_ising = const + sum(h.get(v, 0.0) * z[v] for v in range(3)) \
            + sum(jab * z[a] * z[b] for (a, b), jab in J.items())
        assert abs(e_ising - energy(Q, 0.3, bits)) < 1e-9
