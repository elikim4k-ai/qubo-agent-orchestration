"""Locks the codebase to thesis §3.7: the worked example must yield exactly
two degenerate optima at E = -1.9. If this fails, code and thesis diverged."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from src.qubo.builder import Instance, build_qubo, brute_force, decode, penalty_bounds


def make_worked_example():
    return Instance(
        utilities=[[0.9, 0.8, 0.5], [0.4, 0.3, 0.7]],
        weights=[2, 2, 1],
        capacities=[3, 3],
        affinity={(0, 1): 0.6},
        alpha=0.5,
    )


def test_worked_example_degenerate_optima():
    inst = make_worked_example()
    Q, off, nvars, _ = build_qubo(inst, l1=3.0, l2=2.0, l3=4.0)
    assert nvars == 10  # 6 assignment + two 2-bit slacks (thesis §3.7)
    e, minimisers = brute_force(Q, off, nvars)
    assert abs(e - (-1.9)) < 1e-9
    assignments = {frozenset((i, tuple(t)) for i, t in decode(b, 2, 3).items())
                   for b in minimisers}
    expected = {
        frozenset({(0, (0,)), (1, (1, 2))}),   # agent1:{T1}, agent2:{T2,T3}
        frozenset({(0, (1,)), (1, (0, 2))}),   # agent1:{T2}, agent2:{T1,T3}
    }
    assert assignments == expected


def test_minimisers_are_feasible():
    inst = make_worked_example()
    Q, off, nvars, _ = build_qubo(inst, l1=3.0, l2=2.0, l3=4.0)
    _, minimisers = brute_force(Q, off, nvars)
    for b in minimisers:
        asg = decode(b, 2, 3)
        assigned = sorted(j for ts in asg.values() for j in ts)
        assert assigned == [0, 1, 2]                       # coverage
        for i, ts in asg.items():
            assert sum(inst.weights[j] for j in ts) <= inst.capacities[i]  # capacity


def test_penalty_bounds_sane():
    b = penalty_bounds(make_worked_example())
    # thesis §3.5: weights used (3.0, 2.0) must exceed the derived bounds
    assert 3.0 > b["l1"] and 2.0 > b["l2"]
