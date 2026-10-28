# QUBO Agent Orchestration

Companion implementation for the MSc thesis in `docs/` — a QUBO formulation
for quantum-assisted multi-agent AI workforce orchestration. Research prototype with classical baselines, a worked-example oracle, and optional
QAOA simulator / IBM hardware integrations. The default demo uses mock agents;
it does not establish quantum advantage or real-model task performance.

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

## Install, run, and test

Prerequisites: Git, Python 3.11, and pip. Run commands from the repository root.
The default path needs no API keys, GPU, IBM account, or paid services.
PuLP supplies the CBC backend; if CBC cannot execute on your platform, inspect
the returned backend and fallback metadata before interpreting results.

```bash
git clone https://github.com/elikim4k-ai/qubo-agent-orchestration.git
cd qubo-agent-orchestration
python -m venv .venv
```

Activate on macOS/Linux with `source .venv/bin/activate`; on Windows PowerShell
use `.\.venv\Scripts\Activate.ps1`. If activation is unavailable, invoke
`.venv/bin/python` or `.\.venv\Scripts\python.exe` directly.

```bash
python -m pip install -r requirements.txt
python -m pytest tests -q
python -m pytest tests/test_qubo_worked_example.py -q
python scripts/run_demo.py --mirror off
```

The worked-example tests require two degenerate optima at energy -1.9 and
feasible assignments. The demo writes telemetry, vault cards, and decision
records under `demo_run/`, then prints feasibility, optimizer/greedy utility,
and completed/failed task counts. It deletes and recreates `demo_run/` on each
invocation: copy any artifacts you want to retain before rerunning.

For the asynchronous simulated-annealing mirror, run
`python scripts/run_demo.py --mirror sa`. For a QAOA statevector experiment,
use `--mirror qaoa_sim`; this can be expensive and may fall back classically.
The default `sa` mirror is classical simulated annealing, not quantum hardware.
Always inspect the actual backend and fallback metadata.

## Reproduce benchmark artifacts

Start with a small classical smoke run:

```bash
python scripts/run_benchmark.py --per-tier 1 --tiers N14 --backends exact,greedy --restarts 1
```

Then compare all three classical baselines on a larger sample:

```bash
python scripts/run_benchmark.py --per-tier 3 --tiers N14,N24 --backends exact,sa,greedy --restarts 3 --budget-s 60
```

Outputs (overwritten by subsequent benchmark runs):

- `results/table_5_1.csv`: per-run utility, certified optimum, approximation
  ratio, feasibility, repair status, requested/actual backend, and elapsed time.
- `results/table_5_1_summary.csv`: per-tier/backend aggregates.
- `results/skipped.txt`: written when QAOA cases exceed the statevector cap.
  Use a fresh results directory/run copy when inspecting skip records; a prior
  skip file can survive a later run with no skips.

For successful exact-backend runs, expect feasible assignments and an
approximation ratio of 1 within numerical tolerance. Timing depends on the
machine. The generator uses synthetic defaults unless `--telemetry PATH` is
provided; synthetic outputs are not evidence of live agent performance.
The tier labels are names: use the CSV `num_vars` column for actual QUBO size.

Reproducibility limits:

- Requirements use lower bounds, not a lockfile. Record the commit with
  `git rev-parse HEAD` and dependencies with `python -m pip freeze` alongside
  outputs, plus Python version, OS, CPU, command, and any telemetry/checkpoint hash.
- The generator defaults to `seed0=100`; the selected tiers and sample count
  affect subsequent seeds. Preserve the full command.
- The demo seeds mock clients with `hash(agent_id)`. Set `PYTHONHASHSEED=0`
  **before starting Python** (`export PYTHONHASHSEED=0` on macOS/Linux;
  `$env:PYTHONHASHSEED='0'` in PowerShell). Timestamps and timing-dependent
  registry decay still prevent a promise of identical numeric output.
- Benchmark restart indices are recorded, but the SA service currently uses
  its default seed for every call. Repeated SA rows are not independent random
  trials. Do not interpret their standard deviation as seed-to-seed uncertainty.
- Thesis placeholder tables are not measured results. Archive generated CSVs
  and their environment before citing any benchmark claim. No quantum speedup
  is established by the classical smoke run or a fallback result.

To use real model checkpoints, connect `harness.OpenAICompatClient` to an
OpenAI-compatible endpoint and record its checkpoint hash and configuration.

## MCP servers

```powershell
python -m src.vault.mcp_server vault      # vault file server (§4.1 process 1)
python -m src.solver.mcp_server           # solve_qubo tool   (§4.1 process 3)
```

Install the optional dependency with `python -m pip install mcp` in the same
environment. Both require it; the underlying APIs work (and are tested)
without it.

## Invariants

- `tests/test_qubo_worked_example.py` locks the code to thesis §3.7 (two
  degenerate optima at E = −1.9). If it fails, code and thesis diverged.
- The IBM backend appends a row after successful result post-processing to `docs/hardware_run_log.csv` (implemented in
  `solver/backends/qaoa.py` and called by `solver/service.py`). Failed attempts
  need separate provenance; this file is not a complete audit of attempted jobs.
- The orchestrator starts its quantum mirror asynchronously. The solver tries
  budgeted backends and classical fallback, but its thread timeouts do not
  cancel running work or enforce a single end-to-end process deadline.
- Vault content is untrusted model input: allow-list filtering in
  `vault/store.py`, schema+range validation in `harness/telemetry.py` and
  `registry/profiles.py`.
- Placeholder numbers in the thesis docx must never be cited as real; produce
  measured tables with `scripts/run_benchmark.py`.

## License and contributions

See [LICENSE](LICENSE). For a bug report, include the commit, environment,
minimal input, exact command, expected behavior, and actual backend/output.
For numerical changes, run the worked-example oracle and full test suite.
