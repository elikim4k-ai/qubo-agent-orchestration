"""Solver service (thesis §4.5 / Appendix B).

One entry point, solve_qubo(instance, backend, budget_s, meta), and four
backends behind it: exact (CBC on the constrained form), sa (Metropolis on
the QUBO), qaoa_sim, qaoa_ibm. The contract:

  * identical SolveResult schema from every backend,
  * hard wall-clock budget per call,
  * NEVER raise, NEVER block dispatch — on timeout or backend failure the
    service falls back classically and records the chain in meta.

Post-processing is shared: decode, validate against the constrained problem,
greedy-repair infeasible answers, report both raw and repaired feasibility.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from ..qubo.builder import Instance, build_qubo, brute_force, energy as qubo_energy
from .backends.exact import solve_exact
from .backends.sa import solve_sa
from .repair import (
    assignment_to_bits, decode_assignment, greedy_repair, is_feasible,
)
from .types import BackendUnavailable, SolveResult, choose_weights, objective_utility

BACKENDS = ("exact", "brute", "sa", "qaoa_sim", "qaoa_ibm")
FALLBACK_CHAIN = ("exact", "sa")


def _postprocess(backend: str, inst: Instance, Q: dict, offset: float,
                 num_vars: int, slack_layout: dict, bits_or_samples,
                 wall_ms: int, meta: dict) -> SolveResult:
    """Shared step 5: validate, repair, pick best feasible, report honestly."""
    samples = (bits_or_samples if bits_or_samples and isinstance(bits_or_samples[0], list)
               else [list(bits_or_samples)])
    feasible_raw = 0
    best = None  # (utility, assignment, repaired)
    for bits in samples:
        asg = decode_assignment(bits, inst)
        if is_feasible(inst, asg):
            feasible_raw += 1
            cand = (objective_utility(inst, asg), asg, False)
        else:
            fixed, _ = greedy_repair(inst, asg)
            if not is_feasible(inst, fixed):
                continue
            cand = (objective_utility(inst, fixed), fixed, True)
        if best is None or cand[0] > best[0]:
            best = cand

    meta = {**meta, "raw_feasibility": feasible_raw / max(1, len(samples)),
            "samples_seen": len(samples)}
    if best is None:
        # nothing repairable — degenerate, but the schema still holds
        empty = {i: [] for i in range(inst.m)}
        bits = assignment_to_bits(inst, empty, num_vars, slack_layout)
        return SolveResult(backend=backend, energy=qubo_energy(Q, offset, tuple(bits)),
                           bits=bits, assignment=empty, feasible=False, repaired=True,
                           objective_utility=0.0, optimal=False, wall_ms=wall_ms,
                           num_vars=num_vars, meta=meta)
    util, asg, repaired = best
    bits = assignment_to_bits(inst, asg, num_vars, slack_layout)
    return SolveResult(
        backend=backend, energy=qubo_energy(Q, offset, tuple(bits)), bits=bits,
        assignment=asg, feasible=True, repaired=repaired,
        objective_utility=util, optimal=False, wall_ms=wall_ms,
        num_vars=num_vars, meta=meta,
    )


def _run_backend(backend: str, inst: Instance, Q: dict, offset: float,
                 num_vars: int, slack_layout: dict, budget_s: float,
                 meta: dict) -> SolveResult:
    start = time.monotonic()
    if backend == "exact":
        result = solve_exact(inst, budget_s)
        bits = assignment_to_bits(inst, result.assignment, num_vars, slack_layout)
        result.bits = bits
        result.energy = qubo_energy(Q, offset, tuple(bits))
        result.num_vars = num_vars
        result.meta = {**result.meta, **meta}
        return result
    if backend == "brute":
        if num_vars > 22:
            raise BackendUnavailable("brute force capped at 22 variables")
        e, minimisers = brute_force(Q, offset, num_vars)
        wall_ms = int((time.monotonic() - start) * 1000)
        res = _postprocess("brute", inst, Q, offset, num_vars, slack_layout,
                           [list(b) for b in minimisers], wall_ms,
                           {**meta, "degenerate_optima": len(minimisers)})
        res.optimal = True
        return res
    if backend == "sa":
        bits, _, sa_meta = solve_sa(Q, offset, num_vars, budget_s=budget_s)
        wall_ms = int((time.monotonic() - start) * 1000)
        return _postprocess("sa", inst, Q, offset, num_vars, slack_layout,
                            bits, wall_ms, {**meta, **sa_meta})
    if backend == "qaoa_sim":
        from .backends.qaoa import solve_qaoa_sim
        samples, q_meta = solve_qaoa_sim(Q, offset, num_vars,
                                         p=meta.get("p", 2), budget_s=budget_s)
        wall_ms = int((time.monotonic() - start) * 1000)
        return _postprocess("qaoa_sim", inst, Q, offset, num_vars, slack_layout,
                            samples, wall_ms, {**meta, **q_meta})
    if backend == "qaoa_ibm":
        from .backends.qaoa import append_hardware_log, solve_qaoa_ibm
        samples, q_meta = solve_qaoa_ibm(Q, offset, num_vars,
                                         p=meta.get("p", 1),
                                         backend_name=meta.get("backend_name"),
                                         instance_id=str(meta.get("instance_id", "")),
                                         budget_s=budget_s)
        wall_ms = int((time.monotonic() - start) * 1000)
        res = _postprocess("qaoa_ibm", inst, Q, offset, num_vars, slack_layout,
                           samples, wall_ms, {**meta, **q_meta})
        append_hardware_log(res.meta, num_vars, res.meta["raw_feasibility"],
                            res.energy)  # Appendix C: every hardware run, no exceptions
        return res
    raise BackendUnavailable(f"unknown backend {backend!r}")


def solve_qubo(inst: Instance, backend: str = "exact", budget_s: float = 30.0,
               meta: dict | None = None,
               weights: dict[str, float] | None = None) -> SolveResult:
    """The MCP-visible tool. Returns a SolveResult from `backend` if it
    answers within budget, else from the classical fallback chain. Never
    raises; never blocks beyond ~budget_s per attempt."""
    meta = dict(meta or {})
    w = weights or choose_weights(inst)
    Q, offset, num_vars, slack_layout = build_qubo(inst, w["l1"], w["l2"], w["l3"])
    meta["penalty_weights"] = w

    attempts = [backend] + [b for b in FALLBACK_CHAIN if b != backend]
    errors: list[str] = []
    for attempt in attempts:
        pool = ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(_run_backend, attempt, inst, Q, offset,
                                 num_vars, slack_layout, budget_s, dict(meta))
            result = future.result(timeout=budget_s + 5.0)
            if errors:
                result.meta["fallback_from"] = errors
            return result
        except FuturesTimeout:
            errors.append(f"{attempt}: exceeded {budget_s}s budget")
        except (BackendUnavailable, Exception) as e:  # noqa: BLE001 — contract: never raise
            errors.append(f"{attempt}: {type(e).__name__}: {e}")
        finally:
            pool.shutdown(wait=False)

    # last resort: greedy repair from the empty assignment (pure classical)
    asg, _ = greedy_repair(inst, {i: [] for i in range(inst.m)})
    bits = assignment_to_bits(inst, asg, num_vars, slack_layout)
    return SolveResult(
        backend="greedy_fallback", energy=qubo_energy(Q, offset, tuple(bits)),
        bits=bits, assignment=asg, feasible=is_feasible(inst, asg), repaired=True,
        objective_utility=objective_utility(inst, asg), optimal=False,
        wall_ms=0, num_vars=num_vars, meta={**meta, "fallback_from": errors},
    )
