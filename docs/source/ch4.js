// ch4.js — System design & implementation
const { h1, h2, h3, p, eq, bullets, numbered, table, caption, code } = require("./builder");

const ch4 = [
  h1("Chapter 4 — System Design and Implementation"),
  p("This chapter describes the system I built to host the formulation: the Obsidian vault schema, the harness, the MCP surface, and the solver service with its Qiskit internals. I have tried to write it at the level of detail I wish existing papers had — concrete enough to rebuild from, short of a code walkthrough. The repository accompanying the thesis contains the rest."),

  h2("4.1  Architecture Overview"),
  p("The system is five processes connected almost entirely through MCP:"),
  ...numbered([
    [{ t: "The vault server ", b: true }, { t: "exposes the Obsidian vault over MCP: resources for reading notes, tools for creating and updating task cards, and a search tool over front-matter fields. Worker agents mount it read-mostly; only the orchestrator and the harness telemetry writer hold write scopes beyond each agent's own run-log folder." }],
    [{ t: "The orchestrator ", b: true }, { t: "wakes each epoch, queries the vault for eligible tasks, queries the harness registry for agent state, builds the QUBO of Chapter 3, calls the solver service, validates and repairs the returned assignment, writes a decision record to the vault, and dispatches tasks to harnesses." }],
    [{ t: "The solver service ", b: true }, { t: "is an MCP server with one significant tool, solve_qubo(Q, backend, budget), and three backends behind it: exact (CBC branch-and-bound via PuLP, plus brute force below 24 variables), simulated annealing (a straightforward Metropolis schedule, 10⁴ sweeps), and quantum (QAOA through Qiskit Runtime). The orchestrator neither knows nor cares which backend answered; the response schema is identical." }],
    [{ t: "Agent harnesses ", b: true }, { t: "(one per agent) run the Hermes models, own the tool loop, and stream telemetry — per-step tokens, tool-call validity, task outcomes — to the registry that produces the u, w and C coefficients." }],
    [{ t: "The registry ", b: true }, { t: "aggregates telemetry into per-(agent, category) profiles with exponential decay and serves them to the orchestrator." }],
  ], "arch"),
  p("The design rule throughout was that the quantum solver must be boring from the outside. It sits behind the same tool schema as CBC, it can time out, and when it does the orchestrator falls back classically and the fleet never stalls. A research system that can wedge production on a queued quantum job is a research system that gets turned off."),

  h2("4.2  The Vault: Schema and Conventions"),
  p("Task cards are Markdown files with typed front-matter. A representative card:"),
  ...code([
    "---",
    "type: task",
    "id: T-0147",
    "title: Extract eval tables from run-batch 12",
    "category: extraction",
    "effort: 2",
    "status: eligible",
    "depends_on: [T-0141]",
    "conflicts_with: [T-0148]      # anti-affinity: same output file",
    "affinity_group: eval-report",
    "created: 2026-05-11",
    "---",
    "Pull the pass@1 tables out of the batch-12 logs and normalise",
    "them against the schema in [[eval-schema-v3]]. Watch for the",
    "truncated rows problem noted in [[run-batch-11-postmortem]].",
  ]),
  p("The front-matter feeds the optimizer mechanically (effort → wⱼ, conflicts_with → Eₓ, dependency filtering → eligibility). The body, with its wiki-links, feeds two things: the assigned agent's context, and the affinity coefficients — a(j,k) is the Jaccard overlap of the cards' outgoing link sets, computed by the vault server at query time. Decision records are cards too: each epoch the orchestrator writes a note listing the instance, the backend used, the energy achieved, and the assignment, with backlinks to every task involved. Six weeks in, the vault's graph view had become an unplanned but genuinely useful visualisation of the fleet's history — clusters of tasks around design notes, decision records threading them together. The 'AI brain' framing stopped feeling like a metaphor."),

  h2("4.3  Harness Engineering"),
  p("Each harness wraps one Hermes model behind a fixed contract: assemble context (task card, linked notes up to a token budget, tool schemas), loop on model tool-calls with schema validation, enforce ceilings (steps, tokens, wall-clock), and report an outcome object. Three engineering decisions mattered enough to record."),
  ...bullets([
    [{ t: "Validated tool calls with one-shot repair. ", b: true }, { t: "Malformed JSON gets a single repair prompt containing the validator error; a second failure fails the step. This kept Hermes tool-call acceptance above 97% in the live trace while bounding the cost of a confused model." }],
    [{ t: "Context assembly follows the vault graph. ", b: true }, { t: "Linked notes are pulled breadth-first from the task card under the token budget, which is what makes the affinity bonus real: co-assigned tasks genuinely share warm context, and I could measure the saving (about 18% fewer prompt tokens on the second task of an affine pair in the live trace)." }],
    [{ t: "Telemetry is the product. ", b: true }, { t: "Every step emits a structured event; the registry folds events into the (agent, category) profiles that become uᵢⱼ. I resisted the urge to hand-tune any coefficient. If a number looked wrong, the fix had to be upstream — better category labels, better effort calibration — because a model whose inputs are hand-massaged proves nothing about the pipeline." }],
  ]),

  h2("4.4  MCP Surface and Security Posture"),
  p("All five processes speak MCP over stdio (local) with JSON-RPC. The tool registry is allow-listed per agent role: worker agents see vault read tools, their own log-write tool, and task-completion tools; only the orchestrator sees solve_qubo and vault write tools; nothing sees shell execution. Resource contents from the vault are treated as untrusted model input — cards are rendered into agent context with a delimiter discipline and the harness strips any instruction-shaped front-matter fields it does not recognise. This is a mitigation, not a solution, to prompt injection through shared memory; Section 6.4 discusses the residual risk of an agent poisoning the vault (and thereby, through the affinity coefficients, the optimizer). Destructive vault operations (card deletion, status rollback) require a human confirmation flag that I never automated, on principle."),

  h2("4.5  The Solver Service"),
  h3("4.5.1  Classical Backends"),
  p("The exact backend rewrites the constrained problem (3.1)–(3.4) directly for CBC via PuLP — the solver sees constraints natively, not the penalty QUBO — which makes it both the ground-truth oracle and the production fallback. Median solve time across all evaluation instances was 41 ms; the largest (m=6, n=10) took 3.2 s. The simulated-annealing backend operates on the QUBO itself with a geometric temperature schedule tuned once on a held-out instance set; it exists to answer the fair question 'what does a dumb sampler on the same energy landscape achieve?' and, as Chapter 5 shows, the answer is 'quite a lot.'"),
  h3("4.5.2  QAOA on IBM Quantum"),
  p("The quantum backend follows a fixed protocol, chosen after false starts that Section 5.7 recounts:"),
  ...numbered([
    "Build the Ising Hamiltonian from Q; drop zero terms; record the interaction graph.",
    "Optimise QAOA angles at depth p ∈ {1, 2, 3} on a noiseless MPS simulator with COBYLA (120 evaluations of a 4,096-shot Sampler), warm-started at p from the optimum at p−1.",
    "Transpile the fixed-angle circuit for the target backend at optimisation level 3, letting SABRE handle layout and routing on the heavy-hex lattice; record depth and two-qubit gate count.",
    "Execute on hardware through SamplerV2 in a session: 8 batches × 4,096 shots, with dynamical decoupling (XpXm) and measurement twirling enabled.",
    "Post-process every sample: discard slack bits, check coverage/capacity/exclusion, apply greedy repair to infeasible samples (unassign over-capacity tasks by worst marginal utility, then reassign one-hot violations greedily), and report the best feasible solution plus the full distribution.",
  ], "proto"),
  p("Hardware runs used ibm_torino and ibm_fez (Heron r1/r2, 133 and 156 qubits) between February and May 2026, on the open plan — which is to say, with queue times that taught me to design experiments in batches and to hold the angle optimisation off-device. Every run's backend, calibration snapshot ID, transpiled depth, and shot counts are logged in the decision record; Appendix C tabulates them."),
  p("One implementation note that cost me a week: penalty terms make Q dense enough that a 24-variable instance transpiled to a two-qubit depth near 190 on heavy-hex connectivity at p = 2 — deep enough that raw fidelity collapsed. Thresholding affinity terms (Section 3.1), exploiting the bipartite block structure of coverage penalties in layout seeding, and accepting p = 1 for hardware at N = 24 brought depth to a workable 60–70. The lesson generalises: for penalty-QUBOs on superconducting devices, the fight is with the routed depth of the densest penalty block, and formulation choices upstream (thresholds, slack encoding width) are the effective knobs."),
];

module.exports = { ch4 };
