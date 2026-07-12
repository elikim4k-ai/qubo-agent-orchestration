"""QAOA backend (thesis §4.5.2, the 5-step protocol):

1. Ising Hamiltonian from Q; zero terms dropped; interaction graph recorded.
2. Angles optimised at depth p on a noiseless simulator with COBYLA
   (120 evaluations of a 4096-shot sampler), warm-started at p from p-1.
3. Transpile the fixed-angle circuit at optimisation level 3 (SABRE);
   record two-qubit depth.
4. Hardware: SamplerV2 in a session, 8 x 4096 shots, dynamical decoupling
   (XpXm) and measurement twirling.
5. Post-processing (validation + greedy repair) happens in the service
   layer, shared with SA.

Every hardware run appends a row to docs/hardware_run_log.csv. No exceptions.
Imports are guarded: without qiskit this module raises BackendUnavailable and
the service falls back classically — the quantum path never blocks dispatch.
"""
from __future__ import annotations

import csv
import time
from datetime import date
from pathlib import Path

from ..types import BackendUnavailable

HARDWARE_LOG = Path(__file__).resolve().parents[3] / "docs" / "hardware_run_log.csv"
SHOTS = 4096
BATCHES = 8
COBYLA_EVALS = 120


def to_ising(Q: dict, offset: float) -> tuple[dict[int, float], dict[tuple[int, int], float], float]:
    """QUBO -> Ising via x = (1 - z)/2. Returns (h, J, const); zeros dropped."""
    h: dict[int, float] = {}
    J: dict[tuple[int, int], float] = {}
    const = offset
    for (a, b), c in Q.items():
        if a == b:
            const += c / 2.0
            h[a] = h.get(a, 0.0) - c / 2.0
        else:
            const += c / 4.0
            h[a] = h.get(a, 0.0) - c / 4.0
            h[b] = h.get(b, 0.0) - c / 4.0
            J[(a, b)] = J.get((a, b), 0.0) + c / 4.0
    h = {k: v for k, v in h.items() if abs(v) > 1e-12}
    J = {k: v for k, v in J.items() if abs(v) > 1e-12}
    return h, J, const


def _require_qiskit():
    try:
        import qiskit  # noqa: F401
        from qiskit import QuantumCircuit  # noqa: F401
        from qiskit.primitives import StatevectorSampler  # noqa: F401
    except ImportError as e:
        raise BackendUnavailable(f"qiskit not installed: {e}") from e


def _qaoa_circuit(num_vars: int, h: dict, J: dict, gammas: list[float],
                  betas: list[float]):
    from qiskit import QuantumCircuit
    qc = QuantumCircuit(num_vars)
    qc.h(range(num_vars))
    for gamma, beta in zip(gammas, betas):
        for v, hv in h.items():
            qc.rz(2.0 * gamma * hv, v)
        for (a, b), jab in J.items():
            qc.rzz(2.0 * gamma * jab, a, b)
        qc.rx(2.0 * beta, range(num_vars))
    qc.measure_all()
    return qc


def _sample(qc, shots: int) -> dict[str, int]:
    from qiskit.primitives import StatevectorSampler
    result = StatevectorSampler(seed=7).run([qc], shots=shots).result()[0]
    return result.data.meas.get_counts()


def _counts_energy(counts: dict[str, int], Q: dict, offset: float) -> float:
    from ...qubo.builder import energy
    total = shots = 0.0
    for bitstr, c in counts.items():
        bits = tuple(int(b) for b in reversed(bitstr))  # qiskit is little-endian
        total += c * energy(Q, offset, bits)
        shots += c
    return total / shots


def optimise_angles(Q: dict, offset: float, num_vars: int, p: int,
                    shots: int = SHOTS, evals: int = COBYLA_EVALS
                    ) -> tuple[list[float], list[float], float]:
    """Step 2: COBYLA on the noiseless simulator, warm-started from p-1."""
    _require_qiskit()
    from scipy.optimize import minimize

    h, J, _ = to_ising(Q, offset)

    def make_objective(depth: int):
        def obj(theta):
            gammas, betas = list(theta[:depth]), list(theta[depth:])
            counts = _sample(_qaoa_circuit(num_vars, h, J, gammas, betas), shots)
            return _counts_energy(counts, Q, offset)
        return obj

    theta = [0.1, 0.1]                       # p = 1 start
    best_val = float("inf")
    for depth in range(1, p + 1):
        if depth > 1:                        # warm start: reuse p-1 optimum
            theta = list(theta[:depth - 1]) + [0.05] + list(theta[depth - 1:]) + [0.05]
        res = minimize(make_objective(depth), theta, method="COBYLA",
                       options={"maxiter": evals, "rhobeg": 0.3})
        theta = list(res.x)
        best_val = float(res.fun)
    return theta[:p], theta[p:], best_val


def solve_qaoa_sim(Q: dict, offset: float, num_vars: int, p: int = 2,
                   shots: int = SHOTS, budget_s: float = 300.0
                   ) -> tuple[list[list[int]], dict]:
    """Steps 1-2 + noiseless sampling. Returns (samples, meta); the service
    layer validates/repairs and picks the best feasible sample."""
    _require_qiskit()
    start = time.monotonic()
    if num_vars > 24:
        raise BackendUnavailable(
            f"qaoa_sim capped at 24 vars for statevector simulation, got {num_vars}")
    h, J, _ = to_ising(Q, offset)
    gammas, betas, expected = optimise_angles(Q, offset, num_vars, p, shots)
    counts = _sample(_qaoa_circuit(num_vars, h, J, gammas, betas), shots)
    samples = [[int(b) for b in reversed(bitstr)]
               for bitstr, c in counts.items() for _ in range(min(c, 64))]
    meta = {
        "p": p, "shots": shots, "gammas": gammas, "betas": betas,
        "expected_energy": expected, "num_edges": len(J),
        "wall_ms": int((time.monotonic() - start) * 1000),
    }
    return samples, meta


def solve_qaoa_ibm(Q: dict, offset: float, num_vars: int, p: int = 1,
                   backend_name: str | None = None, instance_id: str = "",
                   budget_s: float = 900.0) -> tuple[list[list[int]], dict]:
    """Steps 3-4 on IBM Quantum. Requires qiskit-ibm-runtime + saved account.
    Angles come from the simulator (step 2) — never optimised on-device."""
    _require_qiskit()
    try:
        from qiskit_ibm_runtime import QiskitRuntimeService, Session, SamplerV2
    except ImportError as e:
        raise BackendUnavailable(f"qiskit-ibm-runtime not installed: {e}") from e
    from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager

    h, J, _ = to_ising(Q, offset)
    gammas, betas, _ = optimise_angles(Q, offset, num_vars, p)
    qc = _qaoa_circuit(num_vars, h, J, gammas, betas)

    service = QiskitRuntimeService()
    backend = (service.backend(backend_name) if backend_name
               else service.least_busy(operational=True, simulator=False,
                                       min_num_qubits=num_vars))
    pm = generate_preset_pass_manager(optimization_level=3, backend=backend)
    isa = pm.run(qc)
    twoq_depth = isa.depth(lambda inst: inst.operation.num_qubits == 2)

    calibration_id = ""
    try:
        props = backend.properties()
        calibration_id = str(getattr(props, "last_update_date", "") or "")
    except Exception:
        pass

    samples: list[list[int]] = []
    session_id = ""
    with Session(backend=backend) as session:
        sampler = SamplerV2(mode=session)
        sampler.options.dynamical_decoupling.enable = True
        sampler.options.dynamical_decoupling.sequence_type = "XpXm"
        sampler.options.twirling.enable_measure = True
        session_id = session.session_id or ""
        for _ in range(BATCHES):
            result = sampler.run([isa], shots=SHOTS).result()[0]
            counts = result.data.meas.get_counts()
            samples.extend([int(b) for b in reversed(s)]
                           for s, c in counts.items() for _ in range(min(c, 64)))

    meta = {
        "p": p, "shots": SHOTS, "batches": BATCHES, "backend_name": backend.name,
        "calibration_snapshot": calibration_id, "twoq_depth": twoq_depth,
        "session_id": session_id, "gammas": gammas, "betas": betas,
        "instance_id": instance_id,
    }
    return samples, meta


def append_hardware_log(meta: dict, num_vars: int, raw_feasibility: float,
                        best_energy: float, notes: str = "") -> None:
    """Appendix C discipline: one row per hardware run, no exceptions."""
    with HARDWARE_LOG.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            date.today().isoformat(), meta.get("backend_name", ""),
            meta.get("calibration_snapshot", ""), meta.get("instance_id", ""),
            num_vars, meta.get("p", ""), meta.get("twoq_depth", ""),
            meta.get("shots", ""), meta.get("session_id", ""),
            f"{raw_feasibility:.4f}", f"{best_energy:.6f}", notes,
        ])
