# QUBO Agent Orchestration

Companion implementation for the MSc thesis in `docs/` — a QUBO formulation
for quantum-assisted multi-agent AI workforce orchestration. Every build-order
phase from CLAUDE.md is implemented and tested.

## Layout

| Path | Thesis | What it is |
|---|---|---|
| `src/qubo/` | Ch. 3 | QUBO builder, penalty bounds, brute-force oracle |
| `src/vault/` | §4.2/§4.4 | Obsidian-vault store: typed cards, Jaccard affinity, untrusted-input validation, MCP file server |
| `src/harness/` | §4.3 | Agent harness: BFS context assembly, one-shot tool repair, ceilings, telemetry-first instrumentation |
| `src/registry/` | §3.1/§4.1 | Telemetry → decayed (agent, category) profiles → u, w, C coefficients |
| `src/solver/` | §4.5 | `solve_qubo` service: CBC exact (constrained form), SA, QAOA sim/IBM, greedy repair, classical fallback, MCP tool |
| `src/orchestrator/` | §3.1/§4.1 | Epoch loop: classical dispatch + async quantum mirror, decision records |
| `src/experiments/` | §5.1–5.3 | Instance generator (fitted to telemetry) and benchmark runner for Tables 5.1/5.2 |

## Quick start

```powershell
uv venv .venv --python 3.11
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
.venv\Scripts\python.exe -m pytest tests -q          # full suite
.venv\Scripts\python.exe scripts\run_demo.py         # end-to-end pipeline
.venv\Scripts\python.exe scripts\run_benchmark.py --per-tier 3 --tiers N14,N24
```

The demo seeds a vault with four mock Hermes agents, generates real telemetry
through the harness, folds it into registry coefficients, runs orchestrator
epochs (CBC dispatch + async quantum-path mirror), and prints the optimizer's
edge over the greedy incumbent.

To drive a real Hermes checkpoint, use `harness.OpenAICompatClient` against any
OpenAI-compatible endpoint and pin the checkpoint hash.

## MCP servers

```powershell
python -m src.vault.mcp_server vault      # vault file server (§4.1 process 1)
python -m src.solver.mcp_server           # solve_qubo tool   (§4.1 process 3)
```

Both require `pip install mcp`; the underlying APIs work (and are tested)
without it.

## Invariants

- `tests/test_qubo_worked_example.py` locks the code to thesis §3.7 (two
  degenerate optima at E = −1.9). If it fails, code and thesis diverged.
- Every hardware run appends a row to `docs/hardware_run_log.csv` (enforced in
  `solver/backends/qaoa.py`). No exceptions.
- The quantum path never blocks dispatch: budgets + classical fallback in
  `solver/service.py`, async mirror in `orchestrator/epoch.py`.
- Vault content is untrusted model input: allow-list filtering in
  `vault/store.py`, schema+range validation in `harness/telemetry.py` and
  `registry/profiles.py`.
- Placeholder numbers in the thesis docx must never be cited as real; produce
  measured tables with `scripts/run_benchmark.py`.
