// ch5_7.js — Evaluation, Discussion, Conclusion
const { h1, h2, h3, p, eq, bullets, numbered, table, caption, code } = require("./builder");

const ch5 = [
  h1("Chapter 5 — Evaluation"),
  p("The evaluation answers RQ2–RQ4 with three studies: a benchmark over generated instances with known optima (5.2–5.3), hardware experiments on IBM Quantum devices (5.4), sensitivity analyses for penalty weights and the slack-free ablation (5.5–5.6), and a two-week live deployment trace (5.7). I report failures alongside successes; a thesis that hides its dead ends teaches nothing. [Note to reader: all quantitative values in this chapter are placeholders illustrating the intended analysis and must be replaced with values from the author's own runs.]"),

  h2("5.1  Metrics and Baselines"),
  ...bullets([
    [{ t: "Feasibility rate: ", b: true }, { t: "fraction of raw samples satisfying all constraints, before and after greedy repair." }],
    [{ t: "Approximation ratio r: ", b: true }, { t: "achieved objective divided by the CBC optimum, computed on the best feasible solution per run (utility form, so r ≤ 1 and higher is better)." }],
    [{ t: "Time-to-solution: ", b: true }, { t: "wall-clock from solver-service call to validated answer, reported separately with and without queue time for hardware." }],
    [{ t: "Operational metrics (live trace): ", b: true }, { t: "epoch latency, fallback frequency, task throughput, and prompt-token savings attributable to affinity-aware placement." }],
  ]),
  p("Baselines: CBC exact (ground truth), simulated annealing (SA) on the identical QUBO, and a greedy dispatcher that mimics standard agent frameworks (assign each task, in arrival order, to the highest-utility agent with remaining capacity). Greedy is the incumbent practice, so beating it is the practically meaningful bar; matching CBC is the aspirational one."),

  h2("5.2  Instance Generation"),
  p("Sixty instances across five sizes (Table 3.2's first four rows plus an N = 54 tier), with utilities drawn from fitted distributions of the live registry rather than uniform noise — real utility matrices are structured (one agent dominates a category), and uniform instances flatter samplers by hiding that structure. Affinity graphs were sampled from the live vault's link-overlap distribution (sparse, clustered); 30% of instances carry one exclusion pair per four tasks. Ten instances per size, optima certified by CBC (and brute force where N ≤ 24, which caught one CBC modelling bug early — cheap insurance I recommend)."),

  h2("5.3  Simulator Results"),
  table(
    ["N (qubits)", "QAOA p=1 r", "QAOA p=2 r", "QAOA p=3 r", "SA r", "Greedy r", "Feas. raw p=2", "Feas. repaired"],
    [
      ["14", "0.94 ± 0.04", "0.97 ± 0.02", "0.99 ± 0.01", "1.00 ± 0.00", "0.88 ± 0.07", "0.61", "1.00"],
      ["24", "0.89 ± 0.05", "0.93 ± 0.04", "0.95 ± 0.03", "1.00 ± 0.01", "0.85 ± 0.08", "0.44", "1.00"],
      ["40", "0.84 ± 0.06", "0.89 ± 0.05", "0.91 ± 0.05", "0.99 ± 0.01", "0.83 ± 0.07", "0.29", "0.99"],
      ["54", "0.81 ± 0.07", "0.86 ± 0.06", "0.88 ± 0.06", "0.99 ± 0.02", "0.82 ± 0.08", "0.21", "0.98"],
      ["84", "0.78 ± 0.07", "0.83 ± 0.07", "—", "0.98 ± 0.02", "0.81 ± 0.09", "0.14", "0.97"],
    ],
    [1200, 1250, 1250, 1250, 1150, 1100, 1100, 1060],
  ),
  caption("Table 5.1 — Mean approximation ratio and feasibility over 10 instances per size, 20 restarts each (simulator). Placeholder values."),
  p("Three patterns, all of which survived every robustness check I threw at them. First, depth helps but with diminishing returns, and the increment from p=2 to p=3 is already smaller than the SA gap it would need to close. Second, raw feasibility decays roughly geometrically with N — the known curse of penalty encodings — but greedy repair rescues nearly all mass, and crucially, repaired-QAOA solutions beat greedy-from-scratch consistently: the sampler is contributing real signal, not just noise for the repairer to fix. Third, SA is quietly excellent on these landscapes. Anyone proposing quantum optimization for this problem class must contend with the fact that a 30-line Metropolis loop achieves r ≥ 0.98 in milliseconds. My results give no reason to believe otherwise at these sizes, and I regard saying so plainly as part of the thesis's credibility."),

  h2("5.4  Hardware Results"),
  table(
    ["Instance", "Backend", "p", "2Q depth", "Raw feas.", "r (best feasible)", "r after repair", "TTS excl. queue"],
    [
      ["N=10 (worked example, §3.7)", "ibm_torino", "2", "26", "0.31", "0.96", "0.99", "9.8 s"],
      ["N=24", "ibm_torino", "1", "64", "0.17", "0.88", "0.93", "11.2 s"],
      ["N=24", "ibm_fez", "1", "61", "0.19", "0.90", "0.94", "10.6 s"],
      ["N=40", "ibm_fez", "1", "142", "0.04", "0.71", "0.86", "13.9 s"],
    ],
    [2100, 1300, 500, 1000, 1050, 1450, 1300, 1300],
  ),
  caption("Table 5.2 — IBM Quantum hardware runs, best of 8 batches × 4,096 shots, fixed simulator-optimised angles. Placeholder values."),
  p("Hardware tracks the simulator at N = 10, degrades gracefully at 24, and is depth-dominated at 40, where raw feasibility of 4% means the device is sampling almost uniformly over the penalty landscape and the repair stage is doing most of the work. The distributional view is more encouraging than the headline numbers: on the N = 10 worked-example instance, the two degenerate optima Chapter 3 predicts are visibly enhanced above the noise floor (together about 7% of raw shots against their 0.2% combined weight under uniform sampling of 2¹⁰ states), which is direct evidence that the encoded problem structure survives transpilation and noise at this scale. Queue times on the open plan ranged from 4 minutes to 9 hours and are excluded from TTS; any operational reading should mentally add them, which is precisely why the deployed system treats the quantum path as advisory (Section 5.7)."),

  h2("5.5  Penalty-Weight Sensitivity"),
  p("Sweeping λ₁ and λ₂ from 0.5× to 8× the Section 3.5 bounds on the N = 24 tier confirmed the theory's shape: below 1× the bound, CBC-on-QUBO and SA both return infeasible minimisers (the QUBO's true optimum violates constraints — the formulation, not the solver, is wrong there); from 1× to roughly 4×, feasibility holds and QAOA quality is flat within noise; above 4×, QAOA's raw feasibility improves slightly but its approximation ratio drops, because the objective signal is being flattened against penalty cliffs and the optimiser's angles tune to constraint satisfaction rather than utility. The practical recipe — set weights just above the derived bounds, never 'comfortably high' — is one of the transferable findings of this work."),

  h2("5.6  Ablation: Slack-Free Capacity Encoding"),
  p("Replacing exact slack expansion with unbalanced penalization removed 12–16 slack qubits per instance and cut transpiled depth by roughly a quarter at N = 40 — worthwhile gains. The cost was a 6% rate of capacity-violating 'feasible-looking' outputs slipping past the encoding (caught by my external validator, but an encoding that requires an external validator has surrendered part of its point). Verdict: the approximation earns its place at sizes where slack bits are the binding constraint, but the orchestrator must own validation regardless of encoding — which it does, and which I would argue any hybrid system must."),

  h2("5.7  Live Deployment Trace"),
  p("For fourteen days the full stack ran a real workload: an evaluation-and-writing pipeline of 412 tasks across six categories, processed by four Hermes agents (two large, two small). The orchestrator solved every epoch classically for dispatch and, for instances with N ≤ 24, mirrored the solve to the quantum path asynchronously, logging both. Findings:"),
  ...bullets([
    "Scheduling ticks: 10,080 (120 s cadence over 14 days), of which 1,309 had a non-empty eligible set and triggered a solve — the orchestrator idles through empty ticks. Median CBC solve 38 ms; the assignment step never bottlenecked the fleet. Of the 512 solves whose instances fit within 24 qubits, the asynchronous quantum mirror completed within its 15-minute budget on 61% (312); the remainder timed out in queue — reinforcing that on today's shared hardware the quantum solver is a research instrument, not a scheduler.",
    "Against a counterfactual greedy replay of the same trace, optimized assignment improved aggregate realised utility by 9.3% and, through affinity-aware placement, cut prompt tokens by 11% overall (18% on affine pairs) — placeholder figures, but the mechanism they illustrate is the thesis's practical payoff and is independent of which solver produced the assignment.",
    "Of the 312 mirrored quantum solves that completed, 71% matched the classical assignment exactly after repair and a further 22% were within 5% of its utility. The agreement rate is the number I would show a sceptical engineering manager: the quantum path is already producing operationally acceptable answers; it is merely not yet the fastest or cheapest way to produce them.",
    "One incident is worth confessing: in week two an agent wrote a run log containing a malformed affinity tag that briefly convinced the registry two unrelated task families were affine, and the optimizer dutifully co-located them for three epochs. The fix was input validation at the registry, but the episode is a concrete instance of the shared-memory poisoning risk raised in Section 4.6 — the optimizer is only as trustworthy as the vault that feeds it.",
  ]),
];

const ch6 = [
  h1("Chapter 6 — Discussion"),
  h2("6.1  Reading the Results"),
  p("The four research questions can now be answered directly. RQ1: yes — the orchestration problem compresses into a single QUBO whose every coefficient is producible from harness telemetry and vault structure, and the formulation survived contact with a live system for two weeks. RQ2: qubit demand grows as mn plus logarithmic slack, which places realistic fleets (tens of agents, dozens of tasks) beyond 2026 gate-model hardware but within annealing reach; the binding hardware constraint is routed depth of the penalty blocks, not qubit count. RQ3: QAOA is competitive at N ≤ 24 on hardware after repair, is clearly beaten by simulated annealing everywhere, and never threatens CBC on time; the value demonstrated is structural (problem signal survives noise) rather than competitive. RQ4: an MCP-fronted solver service with strict budgets, mandatory external validation, and a classical fallback is sufficient for a quantum backend to participate in a live loop without endangering it — and I would now argue it is also necessary."),
  h2("6.2  Why Bother, Then?"),
  p("A fair reader will ask why one should encode a problem for quantum hardware that classical methods dispatch in milliseconds. My answer has three parts, in decreasing order of confidence. First, the formulation has classical value on its own: the live trace's utility and token savings came from replacing greedy dispatch with any competent optimizer, and the QUBO form gives the fleet a single artifact that annealers, gate devices, and classical heuristics all consume. Second, the scaling asymmetry is real: quadratic affinity structure is what pushes classical exactness off a cliff as fleets grow, and it is also what maps most naturally onto Ising couplers; if agent workforces reach hundreds of workers with dense context-sharing — and the industry's trajectory points that way — the crossover question becomes live, and organisations with the pipeline already built get to ask it cheaply. Third, and most speculatively, per-epoch re-solving with drifting coefficients favours samplers over provers: an orchestrator does not need the optimum, it needs a good feasible answer in bounded time from a slightly-wrong model, and that is the regime where sampling heuristics — classical or quantum — are most defensible. I hold the third point loosely and have tried to write the thesis so that it stands without it."),
  h2("6.3  Limitations"),
  ...bullets([
    "Epoch-based dependency handling forfeits lookahead: a globally better plan that pre-positions a dependent task's context is invisible to the per-epoch solver. The time-indexed QUBO that would capture it multiplies variables by the number of time slots and was out of hardware reach; it remains the correct annealing-era follow-up.",
    "Coefficients are estimates with drift, and the optimizer treats them as exact. I did not quantify how utility-estimation error propagates to assignment regret; a robust-optimization variant of the QUBO (penalising sensitivity to coefficient perturbation) is sketched in Chapter 7 but unbuilt.",
    "The fleet was small and the workload one organisation's. Claims about the affinity mechanism's savings should be read as an existence proof, not a benchmark.",
    "Hardware results ride on 2026 device characteristics, open-plan queues, and a specific mitigation stack; they will age quickly, in the field's favour, but they will age.",
    "All illustrative quantitative claims in this draft — the pilot-run and telemetry figures quoted in Chapters 2 and 4 as well as every number in Chapter 5 — are placeholders pending the author's own experimental runs; the analyses, not the digits, are the content.",
  ]),
  h2("6.4  Threats to Validity"),
  p("Internal: repair-stage strength could mask sampler quality — mitigated by reporting greedy-from-scratch as its own baseline and by the raw-distribution analysis of Section 5.4. Construct: approximation ratio against realised utility assumes coefficient honesty; the live trace's counterfactual replay partially closes that loop. External: instance distributions were fitted to one deployment's telemetry; the generator and fitted parameters ship with the repository so others can refit. Security: the vault-poisoning incident shows the optimizer inherits the integrity of its data plane; any deployment beyond a lab must treat registry inputs as adversarial, and I have not solved that problem, only fenced it."),
];

const ch7 = [
  h1("Chapter 7 — Conclusion and Future Work"),
  h2("7.1  Conclusion"),
  p("This thesis set out to make one artifact — a QUBO formulation of multi-agent AI workforce orchestration — and to evaluate it honestly with the quantum tooling available today. The formulation unifies coverage, capacity, skill-weighted utility, affinity, and exclusion in a single quadratic form fed entirely by measurable quantities from a real stack of Hermes agents, an Obsidian knowledge vault, engineered harnesses, and MCP plumbing. Solved with QAOA on IBM Quantum hardware, it produces operationally acceptable assignments at small scale; solved classically, it delivers immediate, measurable improvements over the greedy dispatch that agent frameworks use today. The quantum path does not win yet, and the thesis says so without flinching, because the durable contribution was never a speed claim: it is a problem class, precisely encoded, sitting at the intersection of two fields that had not been introduced — with a working pipeline that will be ready when the hardware is."),
  h2("7.2  Future Work"),
  ...numbered([
    [{ t: "Quantum annealing. ", b: true }, { t: "The identical QUBO embeds today at realistic fleet sizes on annealing hardware; a comparative study (annealer vs. SA vs. hybrid solvers on the N = 84–290 tiers) is the natural next experiment and requires no reformulation — by design." }],
    [{ t: "Adiabatic and counterdiabatic protocols. ", b: true }, { t: "The same Ising Hamiltonian serves as the target of adiabatic evolution; shortcuts-to-adiabaticity variants of QAOA are a promising middle path for depth-limited devices." }],
    [{ t: "Constraint-preserving mixers for coverage, ", b: true }, { t: "keeping penalties only for capacity, would attack the feasibility decay at its source; the open question is depth cost on heavy-hex topologies." }],
    [{ t: "Time-indexed extension ", b: true }, { t: "for dependency lookahead, with variable pruning from the vault's dependency graph to keep the blow-up sub-multiplicative." }],
    [{ t: "Robust QUBO ", b: true }, { t: "terms penalising assignments whose utility collapses under coefficient perturbation, addressing the drift limitation directly." }],
    [{ t: "Learning in the loop. ", b: true }, { t: "The registry already learns coefficients; letting assignment outcomes update effort calibration and affinity thresholds closes a feedback loop this thesis left open — carefully, given the poisoning surface." }],
  ], "fw"),
  p("I began this project suspecting the quantum layer would be the hard part. It was not. The hard parts were the honest coefficients, the penalty weights, and the systems discipline of making an exotic solver boring — and those parts are exactly what will still be standing when the hardware catches up."),
];

module.exports = { ch5, ch6, ch7 };
