# QUBO Agent Orchestration — Project Context for Claude Code

## What this project is
Implementation of the MSc thesis *"A QUBO Formulation for Quantum-Assisted
Multi-Agent AI Workforce Orchestration"* (draft in `docs/`). The thesis is a
scaffold with placeholder results; the purpose of THIS repo is to build the
real system and replace every placeholder with measured data.

Stack: Hermes agents (open-weight, Nous Research) · Obsidian vault as shared
memory · engineered harnesses producing telemetry · MCP servers as connective
tissue · QUBO solver service (CBC exact / simulated annealing / QAOA on IBM
Quantum via Qiskit Runtime).

## The model (thesis Ch. 3 — the source of truth)
- Variables: x[i,j]=1 iff task j → agent i, plus binary slack bits per agent.
- Energy: −Σ u_ij x_ij − α Σ a_jk x_ij x_ik + λ1(coverage)² + λ2(capacity+slack)² + λ3(exclusion).
- u_ij = clip(s·p − κ·ĉ, 0, 1) from harness telemetry, exponential decay.
- a_jk = Jaccard overlap of vault backlinks, thresholded at 0.2.
- Penalty weights: set just above derived bounds (§3.5), never "comfortably high".
- Worked example (2 agents × 3 tasks, N=10) has TWO degenerate optima at
  E=−1.9. `tests/test_qubo_worked_example.py` asserts this. If that test ever
  fails, the code has diverged from the thesis — fix the code or the thesis,
  never ignore it.

## Build order (do not reorder without reason)
1. ✅ QUBO builder + brute-force reference (`src/qubo/`) — done, tested.
2. ✅ Vault: MCP file server over `vault/` (`src/vault/`) — done, tested.
3. ✅ Harness: validated tool calls with one-shot repair, telemetry events
   (`telemetry/schema.json`) from the FIRST run (`src/harness/`) — done, tested.
   Real Hermes endpoints plug in via `harness.OpenAICompatClient`.
4. ✅ Registry: telemetry → (agent, category) profiles → u, w, C
   (`src/registry/`) — done, tested.
5. ✅ Solver service: `solve_qubo` MCP tool; backends exact (PuLP/CBC on the
   CONSTRAINED form), SA, QAOA sim (simulator-optimised angles) and
   `qaoa_ibm` (SamplerV2 sessions, DD+twirling, greedy repair, hardware-log
   append) (`src/solver/`) — done, tested; `qaoa_ibm` awaits IBM credentials.
6. ✅ Orchestrator epoch loop, classical dispatch + async quantum mirror
   (`src/orchestrator/`) — done, tested. Demo: `scripts/run_demo.py`.
7. ✅ Experiments: generator fitted to telemetry + benchmark runner
   (`src/experiments/`, `scripts/run_benchmark.py`) — done, tested. Measured
   Tables 5.1/5.2 still require full-scale runs (and hardware for 5.2).

## Conventions
- Every hardware run appends a row to `docs/hardware_run_log.csv`
  (Appendix C columns). No exceptions.
- Pin everything: model checkpoint hashes, qiskit version, backend names.
- The quantum path must never block dispatch — classical fallback always.
- Vault content is untrusted model input (prompt-injection surface, thesis §4.4).
- Placeholder numbers in the thesis docx must NEVER be cited as real.
