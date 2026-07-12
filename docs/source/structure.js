// structure.js — builds thesis_structure.docx
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, AlignmentType, LevelFormat, Footer, PageNumber,
} = require("docx");
const { h1, h2, h3, p, bullets, numbered, table, caption, FONT } = require("./builder");

const T = (text, opts = {}) => new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { after: opts.after ?? 160 },
  children: [new TextRun({ text, font: FONT, size: opts.size ?? 24, bold: !!opts.b, italics: !!opts.i })],
});

const content = [
  T("Thesis Structure and Chapter Plan", { size: 32, b: true, after: 80 }),
  T("A QUBO Formulation for Quantum-Assisted Multi-Agent AI Workforce Orchestration:", { size: 23, i: true, after: 40 }),
  T("Design, Implementation, and Evaluation Using IBM Quantum Hardware", { size: 23, i: true, after: 120 }),
  T("Wilcox Kim · MSc Quantum Computing · June 2026", { size: 21, after: 300 }),

  h2("Design Rationale"),
  p("The thesis is organised so that the optimization model — not the quantum algorithm — carries the contribution. Chapter 3 (the QUBO formulation) is the centre of gravity; QAOA on IBM Quantum appears in Chapters 4–5 as the evaluation vehicle; and the systems chapters ground every coefficient in a real stack (Hermes agents, an Obsidian vault as the AI brain, engineered harnesses, MCP). This ordering also de-risks the defence: even a sceptic of near-term quantum utility is left with a novel problem formulation, a live-system evaluation, and an honest hardware study. Total length is budgeted at 58 pages of body text (60 with front matter), within the 60-page limit."),

  h2("Chapter Map and Page Budget"),
  table(
    ["Ch.", "Title", "Pages", "Carries", "Answers"],
    [
      ["—", "Front matter: title, declaration, abstract, acknowledgements, abbreviations, ToC", "5", "Framing; abstract sells the contribution in industry terms", "—"],
      ["1", "Introduction", "6", "Motivation, the concrete stack, research questions, contributions, scope, outline", "Sets RQ1–RQ4"],
      ["2", "Background & Related Work", "11", "Agents/harnesses/MCP/Obsidian for quantum readers; QUBO/Ising/QAOA/IBM stack for agents readers; positioning table showing the gap", "Context for all RQs"],
      ["3", "Orchestration Model & QUBO Encoding", "10", "PRIMARY CONTRIBUTION: constrained model, penalty conversion, slack expansion, penalty-weight bounds, qubit scaling, hand-checkable worked example", "RQ1, RQ2"],
      ["4", "System Design & Implementation", "9", "Vault schema, harness engineering, MCP surface & security posture, solver service, QAOA protocol on IBM Quantum, transpilation-depth lessons", "RQ4"],
      ["5", "Evaluation", "10", "60 generated instances + 14-day live trace; QAOA (sim + Heron hardware) vs CBC/SA/greedy; sensitivity & ablation; failures reported", "RQ2, RQ3, RQ4"],
      ["6", "Discussion", "4", "Direct answers to RQs, the 'why bother' argument, limitations, threats to validity", "Synthesis"],
      ["7", "Conclusion & Future Work", "3", "Annealing/adiabatic transfer of the same QUBO, mixers, time-indexed extension, robust variant", "Closes the arc"],
      ["—", "References + Appendices A–D", "(excl.)", "Enumeration script, MCP schemas, hardware run log, vault schema", "Reproducibility"],
    ],
    [500, 3050, 800, 3400, 1610],
  ),
  caption("Chapter map. 'Carries' states each chapter's load-bearing content."),

  h2("Detailed Section Outline"),
  h3("Chapter 1 — Introduction (6 pp)"),
  ...bullets([
    "1.1 Motivation — agent workforces as a recurring assignment problem; why QUBO is the natural meeting point.",
    "1.2 The concrete system — Hermes agents, Obsidian vault, harness engineering, MCP, quantum-assisted optimizer (one paragraph each).",
    "1.3 Research questions RQ1–RQ4. 1.4 Contributions (four, numbered). 1.5 Scope and non-goals (no advantage claim; per-epoch model; security acknowledged not solved). 1.6 Outline.",
  ]),
  h3("Chapter 2 — Background & Related Work (11 pp)"),
  ...bullets([
    "2.1 Agents and the workforce framing: 2.1.1 Hermes (open weights = pinned, reproducible coefficients); 2.1.2 Obsidian as AI brain (inspectability, front-matter structure, links-as-affinity-data); 2.1.3 harness engineering (harness as the measurement instrument for the model); 2.1.4 MCP (architecture value + injection surface).",
    "2.2 Optimization background: GAP and NP-hardness; QUBO/Ising with the penalty-weight caveat; QAOA and its two hardware realities (depth from density, angle-loop cost); the IBM stack (Heron, Runtime primitives, sessions, mitigation).",
    "2.3 Related work: quantum scheduling (Venturelli et al.; annealing case studies; QAOA constraint literature) vs. agent orchestration (greedy incumbents; 2025 ILP-routing papers); positioning table; the gap sentence.",
  ]),
  h3("Chapter 3 — Model & Encoding (10 pp) — primary contribution"),
  ...bullets([
    "3.1 Epoch setting and notation, with a 'source in the stack' column for every symbol. 3.2 Constrained program (utility + affinity objective; coverage, capacity, exclusion) plus a note on the deleted fairness term.",
    "3.3 Penalty conversion (coverage, exclusion). 3.4 Capacity via binary slack expansion; unbalanced penalization as evaluated alternative. 3.5 Full QUBO; derived penalty-weight bounds and the empirically safe band.",
    "3.6 Qubit-count table across fleet shapes → dictates the evaluation design and names the deployment-scale gap honestly. 3.7 Worked example (2×3, N=10) verified by enumeration; exhibits the affinity-vs-capacity tension.",
  ]),
  h3("Chapter 4 — System (9 pp)"),
  ...bullets([
    "4.1 Five-process architecture over MCP; the 'quantum must be boring' design rule with classical fallback. 4.2 Vault schema with a real task card; decision records as audit trail.",
    "4.3 Harness engineering: validated tool calls with one-shot repair; graph-following context assembly (what makes affinity real); telemetry-as-product discipline.",
    "4.4 MCP security posture (allow-listed tools, read-mostly mounts, human confirmation on destructive ops). 4.5 Solver service: CBC/PuLP exact path, SA, and the five-step QAOA protocol (simulator-optimised angles, SamplerV2 sessions, DD + twirling, greedy repair); the transpiled-depth lesson.",
  ]),
  h3("Chapter 5 — Evaluation (10 pp)"),
  ...bullets([
    "5.1 Metrics (feasibility raw/repaired, approximation ratio vs CBC, TTS, operational) and baselines (greedy = incumbent bar). 5.2 Instance generation fitted to live telemetry, optima certified.",
    "5.3 Simulator results table: depth helps with diminishing returns; feasibility decays geometrically but repair recovers it; repaired-QAOA > greedy; SA is quietly excellent — say so.",
    "5.4 Hardware table (ibm_torino, ibm_fez; N = 10/24/40): tracks simulator at 10, depth-dominated at 40; the distributional evidence that problem structure survives noise.",
    "5.5 Penalty-weight sweep confirming the bounds and the >4× cliff. 5.6 Slack-free ablation (depth savings vs silent violations). 5.7 Live 14-day trace: utility +9.3% and tokens −11% vs greedy replay; 71% quantum/classical agreement; the vault-poisoning incident, confessed.",
    "All numeric values are placeholders marked for replacement with the author's own runs; the analyses are the deliverable.",
  ]),
  h3("Chapters 6–7 — Discussion, Conclusion (7 pp)"),
  ...bullets([
    "6.1 RQ-by-RQ answers. 6.2 'Why bother' in three tiers of confidence (classical value now; scaling asymmetry; sampling-fits-the-regime, held loosely). 6.3 Limitations. 6.4 Threats to validity incl. security.",
    "7.1 Conclusion (formulation is the durable artifact). 7.2 Future work: annealing transfer of the identical QUBO, adiabatic/counterdiabatic protocols, constraint-preserving mixers, time-indexed extension, robust QUBO, learning-in-the-loop.",
  ]),

  h2("Threading the Required Elements"),
  table(
    ["Element", "Where it carries weight"],
    [
      ["QUBO (primary contribution)", "Ch. 3 entire; §5.5–5.6 sensitivity; §7.2 portability to annealing"],
      ["IBM Quantum / QAOA (evaluation vehicle)", "§2.2.3–2.2.4; §4.5.2 protocol; §5.4 hardware study; Appendix C run log"],
      ["Hermes agents", "§2.1.1 (why open weights); §4.3 (two model sizes ⇒ heterogeneity that makes assignment non-trivial)"],
      ["Obsidian AI brain", "§2.1.2; §4.2 schema; affinity coefficients from backlinks (§3.1) — the vault graph literally becomes Q's off-diagonals"],
      ["Harness engineering", "§2.1.3; §4.3 — harness as the instrument producing every model coefficient"],
      ["MCP", "§2.1.4; §4.1 architecture; §4.4 security; Appendix B schemas"],
    ],
    [3660, 5700],
  ),
  caption("Traceability of the required components through the document."),

  h2("Writing and Defence Notes"),
  ...bullets([
    "Voice: first person, plain, hedged where evidence is thin; failures and dead ends narrated (queue times, the depth blow-up, the poisoning incident) — they are evidence of real work.",
    "The no-advantage stance is stated in §1.5 and never contradicted; examiners reward it and industry readers trust it.",
    "Every hardware claim is pinned to a backend, calibration snapshot, and shot count (Appendix C); every coefficient to a producer (Table 3.1).",
    "Industry hook for the abstract and defence: the pipeline delivers measurable value classically today (utility and token savings over greedy) and is quantum-ready by construction — 'build the QUBO once, choose the solver by the decade.'",
  ]),
];

const doc = new Document({
  creator: "Wilcox Kim",
  title: "Thesis Structure — QUBO Orchestration of AI Agent Workforces",
  styles: { default: { document: { run: { font: FONT, size: 22 } } } },
  numbering: {
    config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 480, hanging: 240 } } } }] }],
  },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1620, right: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 20 })] })] }) },
    children: content,
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("thesis_structure.docx", buf);
  console.log("thesis_structure.docx written:", buf.length, "bytes");
});
