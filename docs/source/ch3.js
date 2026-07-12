// ch3.js — Problem formulation
const { h1, h2, h3, p, eq, bullets, numbered, table, caption, code } = require("./builder");

const ch3 = [
  h1("Chapter 3 — An Orchestration Model and Its QUBO Encoding"),
  p("This chapter is the core of the thesis. I first pin down the orchestration problem as a constrained quadratic program over binary assignment variables (Section 3.2), then convert it to an unconstrained QUBO via penalty terms and binary slack expansion (Sections 3.3–3.4), derive workable bounds for the penalty weights (Section 3.5), count variables to understand hardware feasibility (Section 3.6), and close with an example small enough to verify by exhaustive enumeration (Section 3.7). Throughout, I flag where a modelling choice was forced by hardware realism rather than mathematical taste — those seams are, I think, part of the contribution."),

  h2("3.1  Setting and Notation"),
  p("The orchestrator operates in epochs. At the start of epoch t it observes the set of eligible tasks — tasks whose dependencies have all completed — and the current state of the fleet, solves an assignment problem, dispatches, and sleeps until the next tick (in my deployment, 120 seconds, or earlier on agent failure). Handling dependencies through eligibility rather than inside the optimization is a deliberate compression: it keeps the per-epoch problem a pure assignment problem, at the cost of some lookahead. Section 6.3 examines what that costs. Within one epoch, notation is as follows."),
  table(
    ["Symbol", "Meaning", "Source in the stack"],
    [
      ["A, indexed by i", "Agents available this epoch (|A| = m)", "Harness registry"],
      ["T, indexed by j", "Eligible tasks (|T| = n)", "Vault task cards, dependency-filtered"],
      ["wⱼ ∈ ℤ⁺", "Effort estimate of task j (work units)", "Task card front-matter; calibrated by harness history"],
      ["Cᵢ ∈ ℤ⁺", "Capacity of agent i this epoch (work units)", "Harness: context budget, rate limits, concurrency"],
      ["uᵢⱼ ∈ [0,1]", "Utility of assigning j to i (skill × success − normalised cost)", "Harness telemetry per (agent, category), decayed"],
      ["aⱼₖ ≥ 0", "Affinity between tasks j, k (context overlap)", "Obsidian backlink/tag overlap (Jaccard on link sets)"],
      ["Eₓ", "Anti-affinity pairs: {j,k} that must not share an agent", "Task card front-matter (resource conflicts)"],
      ["xᵢⱼ ∈ {0,1}", "Decision: 1 iff task j is assigned to agent i", "—"],
    ],
    [1500, 4000, 3860],
  ),
  caption("Table 3.1 — Notation, and where each quantity actually comes from."),
  p("The last column is the part I want to defend. Formulations in the scheduling literature routinely posit coefficients; here every coefficient has a producer. Utility uᵢⱼ, for instance, is computed as uᵢⱼ = sᵢ,cat(j) · pᵢ,cat(j) − κ · ĉᵢⱼ, where s is a competence score and p an empirical success rate for agent i on task j's category, both maintained by the harness with exponential decay (half-life of twenty completions), and ĉᵢⱼ is the predicted token cost normalised into [0,1]; the result is clipped into [0,1] so that a hopeless pairing floors at zero rather than going negative and fighting the penalty terms. The affinity aⱼₖ is the Jaccard similarity of the outgoing link sets of the two task cards in the Obsidian vault, thresholded at 0.2 to keep the Q matrix from densifying — a threshold I chose after watching transpiled circuit depth blow up without it (Section 4.5.2)."),

  h2("3.2  The Constrained Problem"),
  p("The epoch problem, in its natural constrained form, is:"),
  eq([{ t: "maximise   Σᵢⱼ uᵢⱼ xᵢⱼ  +  α Σᵢ Σⱼ<ₖ aⱼₖ xᵢⱼ xᵢₖ" }], "3.1"),
  eq([{ t: "subject to   Σᵢ xᵢⱼ = 1   ∀ j ∈ T" }], "3.2"),
  eq([{ t: "Σⱼ wⱼ xᵢⱼ ≤ Cᵢ   ∀ i ∈ A" }], "3.3"),
  eq([{ t: "xᵢⱼ + xᵢₖ ≤ 1   ∀ {j,k} ∈ Eₓ, ∀ i ∈ A" }], "3.4"),
  p("Constraint (3.2) says every eligible task is assigned to exactly one agent. (3.3) is the knapsack-style capacity constraint that makes this a Generalised Assignment Problem. (3.4) forbids co-locating conflicting tasks. The quadratic term in (3.1), weighted by a tunable α ≥ 0, is the departure from textbook GAP: it pays a bonus when two context-related tasks land on the same agent, capturing the very real saving that the second task starts with the relevant notes already in the worker's context window. With α = 0 the problem is GAP (NP-hard); with α > 0 it acquires quadratic-assignment character. Either way, exact scalability is not to be expected, which is the honest motivation for heuristic and quantum solvers."),
  p("A remark on what is not in the model. I experimented with a fairness term penalising load variance across agents and dropped it: in an agent fleet, unlike a human one, an idle worker is a feature (it is capacity headroom), and the term fought the utility signal for no operational benefit. I mention this because deleted terms are as informative as retained ones, and because the QUBO template below accepts such terms trivially should a deployment want them."),

  h2("3.3  Penalty Conversion"),
  p("Following the standard recipe, each constraint becomes a squared (or product) penalty added to a minimisation objective. Writing the objective as energy (negating the utility terms), the three penalty blocks are:"),
  eq([{ t: "P_cover = λ₁ Σⱼ ( 1 − Σᵢ xᵢⱼ )²" }], "3.5"),
  eq([{ t: "P_excl = λ₃ Σᵢ Σ_{j,k}∈Eₓ xᵢⱼ xᵢₖ" }], "3.6"),
  p("Coverage (3.5) expands into linear and quadratic terms in x and is exact: it is zero iff each task has exactly one agent. Exclusion (3.6) is already a product form and needs no slack. The inequality (3.3) is the awkward one and gets its own section."),

  h2("3.4  Capacity via Binary Slack Expansion"),
  p("An inequality Σⱼ wⱼxᵢⱼ ≤ Cᵢ becomes an equality by adding a non-negative slack variable σᵢ = Cᵢ − Σⱼ wⱼxᵢⱼ, which must itself be encoded in binaries. I use the standard mixed-radix expansion σᵢ = Σᵣ 2ʳ yᵢᵣ + ρᵢ yᵢ,R, with R = ⌊log₂ Cᵢ⌋ bits plus a residual coefficient ρᵢ = Cᵢ − (2ᴿ − 1) so that σᵢ ranges over exactly {0,…,Cᵢ}. The capacity penalty is then"),
  eq([{ t: "P_cap = λ₂ Σᵢ ( Cᵢ − Σⱼ wⱼ xᵢⱼ − Σᵣ 2ʳ yᵢᵣ − ρᵢ yᵢ,R )²" }], "3.7"),
  p("Slack bits are pure overhead — they carry no information the schedule needs — and they are the price of insisting on QUBO form. Per agent, the cost is ⌈log₂(Cᵢ+1)⌉ ancilla bits; for my deployment capacities (Cᵢ ∈ [4, 12] work units) that is 3–4 bits per agent. Two alternatives deserve mention. Unbalanced penalization (Montañez-Barrera et al., 2024) approximates the inequality with exponential-free linear-plus-quadratic terms and no slack bits at all, at the cost of an approximation whose failure mode is silent capacity violation; I evaluate it as an ablation in Section 5.6 and found it attractive at the largest sizes but keep exact slack in the main line. Constraint-preserving mixers eliminate the coverage penalty instead by confining QAOA's evolution to the feasible one-hot subspace; they do not compose easily with the capacity constraint, so I left them for future work."),

  h2("3.5  The Full QUBO and Penalty Weights"),
  p("Assembling (3.1)–(3.7), the energy to minimise is"),
  eq([{ t: "E(x, y) = −Σᵢⱼ uᵢⱼ xᵢⱼ − α Σᵢ Σⱼ<ₖ aⱼₖ xᵢⱼ xᵢₖ + P_cover + P_cap + P_excl" }], "3.8"),
  p("which is a quadratic form over N = mn + Σᵢ⌈log₂(Cᵢ+1)⌉ binaries and hence a QUBO after collecting terms into a symmetric matrix Q. The implementation builds Q sparsely as a dictionary of index pairs; Appendix A prints the full matrix for the worked example."),
  p("Penalty weights are where naive QUBO practice goes to die, so I want to be explicit about the reasoning. A sufficient condition for penalties to dominate is that violating any constraint by the smallest possible amount must cost more energy than the largest possible objective gain from that violation. For coverage: leaving a task unassigned saves at most maxᵢ uᵢⱼ + α·(affinity it participates in) — call it Δⱼ — so λ₁ > maxⱼ Δⱼ suffices; assigning a task twice is penalised automatically since (1−2)² = 1. For capacity, the smallest violation is one work unit and the largest gain from over-packing an agent is bounded by the best marginal utility per unit, giving λ₂ > maxᵢⱼ uᵢⱼ / minⱼ wⱼ after normalisation. For exclusion, λ₃ > 2·maxᵢⱼ uᵢⱼ + α·max affinity. In practice I set λ₁ = 2Δ̄, λ₂ = 1.5× its bound, λ₃ = 2× its bound, then verified by a sweep (Section 5.5) that solution feasibility on the exact solver was insensitive across a factor-of-four band while QAOA sample feasibility degraded sharply above roughly 4× the bounds — the cliff-face effect predicted in Section 2.2.2, and the empirical justification for choosing weights near the lower end of the safe band."),

  h2("3.6  Size and Hardware Feasibility"),
  p("Variable count is the whole game for near-term hardware, so Table 3.2 works it out for representative fleet shapes, assuming Cᵢ ≤ 12 (4 slack bits per agent)."),
  table(
    ["Agents m", "Tasks n", "Assignment vars mn", "Slack bits", "Total qubits N", "Regime"],
    [
      ["2", "3", "6", "8", "14", "Hardware, comfortably"],
      ["3", "4", "12", "12", "24", "Hardware, workable"],
      ["4", "6", "24", "16", "40", "Hardware, depth-limited"],
      ["6", "10", "60", "24", "84", "Simulator only (this thesis)"],
      ["10", "25", "250", "40", "290", "Beyond current devices"],
    ],
    [1200, 1000, 2200, 1400, 1800, 1760],
  ),
  caption("Table 3.2 — Qubit requirements as fleets scale. Quadratic growth in mn dominates."),
  p("The table explains the shape of the evaluation: exhaustive ground truth to N ≈ 24, exact ILP ground truth throughout, hardware experiments on the N = 10 worked example and the N = 24 tier with a depth-limited attempt at 40, and simulator studies above that. It also quantifies the honest gap between this thesis and deployment scale — a 10-agent, 25-task epoch needs roughly 290 well-behaved qubits with dense connectivity, which no 2026 gate-model device offers, though it sits comfortably inside quantum-annealing embeddings today. That asymmetry is exactly why Chapter 7 points the formulation at annealers next."),

  h2("3.7  A Worked Example"),
  p("To make the encoding concrete — and checkable — take m = 2 agents and n = 3 tasks. Agent 1 is a large Hermes instance, strong at analysis (category of tasks 1 and 2); agent 2 is the small model, cheap and adequate for extraction (task 3). Capacities C₁ = C₂ = 3; efforts w = (2, 2, 1). Utilities, from a real telemetry snapshot rounded to one decimal:"),
  ...code([
    "u =  [ 0.9  0.8  0.5 ]     (agent 1 over tasks 1..3)",
    "     [ 0.4  0.3  0.7 ]     (agent 2 over tasks 1..3)",
    "affinity: a(1,2) = 0.6 (tasks 1 and 2 share three vault links); others 0",
    "exclusion: none.   alpha = 0.5,  lambda1 = 3.0, lambda2 = 2.0",
  ]),
  p("Six assignment bits plus two 2-bit slacks give N = 10. Is the tempting move — both heavy tasks to agent 1, collecting the affinity bonus — available? No: w₁ + w₂ = 4 > C₁ = 3, so capacity forbids it. The optimum must therefore split the affine pair, and enumeration of all 2¹⁰ = 1024 states (a twelve-line script, Appendix A) finds two degenerate minimisers at energy −1.9: x₁₁ = 1 with x₂₂ = x₂₃ = 1 (agent 1 takes its best-matched task 1; agent 2 takes tasks 2 and 3, load exactly at capacity), and the mirror x₁₂ = 1 with x₂₁ = x₂₃ = 1, whose utilities happen to tie at 1.9. Both sacrifice the 0.5·0.6 affinity bonus because capacity makes the bonus unreachable; the greedy-looking alternatives that keep task 3 with agent 1 reach only 1.7. I like this example because it is small enough to hand-check yet already exhibits the defining tension of the model: affinity pulls related tasks together, capacity pushes them apart, and the optimizer earns its keep by arbitrating. The accidental degeneracy is a bonus rather than a blemish — real telemetry-derived instances have near-ties constantly, and when I later inspect QAOA sample distributions (Section 5.4), this instance is the lens: a good sampler should place visible probability mass on both degenerate optima, and hardware runs do — just with a lot of noise around them."),
];

module.exports = { ch3 };
