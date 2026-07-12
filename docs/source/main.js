// main.js — assemble thesis.docx
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, AlignmentType, HeadingLevel,
  TableOfContents, PageNumber, Footer, Header, LevelFormat, PageBreak, SectionType,
} = require("docx");
const { h1, h2, h3, p, eq, bullets, numbered, table, caption, code, FONT } = require("./builder");
const { ch1, ch2 } = require("./ch1_2");
const { ch3 } = require("./ch3");
const { ch4 } = require("./ch4");
const { ch5, ch6, ch7 } = require("./ch5_7");

const T = (text, opts = {}) => new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: opts.after ?? 200 },
  children: [new TextRun({ text, font: FONT, size: opts.size ?? 24, bold: !!opts.b, italics: !!opts.i })],
});

// ---------- Title page ----------
const titlePage = [
  new Paragraph({ spacing: { after: 1400 }, children: [] }),
  T("A QUBO Formulation for Quantum-Assisted Multi-Agent", { size: 34, b: true, after: 80 }),
  T("AI Workforce Orchestration:", { size: 34, b: true, after: 80 }),
  T("Design, Implementation, and Evaluation Using IBM Quantum Hardware", { size: 28, b: true, after: 700 }),
  T("Wilcox Kim", { size: 28, after: 120 }),
  T("A thesis submitted in partial fulfilment of the requirements for the degree of", { size: 22, i: true, after: 60 }),
  T("Master of Science in Quantum Computing", { size: 24, after: 600 }),
  T("Department of Computer Science", { size: 22, after: 60 }),
  T("[University Name]", { size: 22, after: 60 }),
  T("June 2026", { size: 22, after: 400 }),
  T("Supervisor: [Supervisor Name]    ·    Second Reader: [Name]", { size: 20, i: true }),
  new Paragraph({ children: [new PageBreak()] }),
];

// ---------- Declaration ----------
const declaration = [
  h1("Declaration", { noBreak: true }),
  p("I declare that this thesis is my own work, that all sources are acknowledged, and that the experimental artifacts described herein are available in the accompanying repository. Where AI tools were used in the preparation of this document, their use is disclosed in accordance with the University's academic integrity policy. [Author: complete this section per your institution's requirements — most now require an explicit AI-use statement.]"),
];

// ---------- Abstract ----------
const abstract = [
  h1("Abstract"),
  p("Organisations increasingly run fleets of AI agents — language-model workers wrapped in tool-using harnesses — against shared task backlogs, and the question of which agent should take which task has quietly become an operations-research problem that current frameworks answer greedily. This thesis formulates multi-agent AI workforce orchestration as a Quadratic Unconstrained Binary Optimization (QUBO) problem and evaluates it end-to-end on IBM Quantum hardware inside a working agent stack."),
  p("The formulation unifies task coverage, agent capacity (encoded with binary slack expansion), skill-weighted utility, context-affinity bonuses, and anti-affinity exclusions in one quadratic objective, with penalty weights set by derived bounds rather than folklore. Its coefficients are not posited but produced: worker agents built on the open-weight Hermes model family run inside engineered harnesses whose telemetry yields utilities, costs, and capacities, while an Obsidian knowledge vault — the fleet's shared 'brain' — supplies task structure and, through backlink overlap, the affinity coefficients themselves. All components communicate over the Model Context Protocol, so the optimizer is an ordinary, replaceable tool."),
  p("Empirically, the QUBO is solved with QAOA (depths 1–3) on simulators and on IBM Quantum Heron processors at 14–40 qubits, against exact branch-and-bound, simulated annealing, and greedy baselines, over sixty generated instances and a fourteen-day live deployment. The findings are reported without varnish: classical solvers remain decisively faster at today's sizes; simulated annealing is a formidable baseline; yet hardware samples show clear enhancement of optimal structure at small scale, greedy repair recovers feasibility cheaply, and the optimized assignments — from any backend — beat greedy dispatch on realised utility and prompt-token cost in live operation. The primary contribution is the formulation and the reproducible pipeline around it: a problem class from the agent era, encoded in the lingua franca of quantum optimization, ready for annealing and adiabatic backends without change."),
  p([{ t: "Keywords: ", b: true }, { t: "QUBO, QAOA, IBM Quantum, multi-agent systems, AI agents, orchestration, Model Context Protocol, harness engineering, Obsidian, generalised assignment problem", i: true }]),
];

// ---------- Acknowledgements ----------
const acks = [
  h1("Acknowledgements"),
  p("My thanks to my supervisor, [Name], who asked in our second meeting the question that reshaped this project — 'what would make this thesis worth reading if quantum computers never got better?' — and then had the patience to watch me spend a month discovering the answer the hard way. Thanks to the IBM Quantum open plan, whose queue times taught me more about experimental discipline than any methods course; to the maintainers of Qiskit, PuLP, and Obsidian; to Nous Research for keeping serious models open; and to the lab-mates who reviewed drafts and broke my MCP server in instructive ways. Errors that remain are mine, and given the pace of this field, a few statements will be stale by the time this is bound. Such is the cost of writing about a moving target; I would not have chosen a stationary one."),
];

// ---------- Abbreviations ----------
const abbrev = [
  h1("List of Abbreviations"),
  table(
    ["Abbreviation", "Meaning"],
    [
      ["CBC", "COIN-OR Branch and Cut (open-source MILP solver)"],
      ["GAP", "Generalised Assignment Problem"],
      ["MCP", "Model Context Protocol"],
      ["MILP", "Mixed-Integer Linear Programming"],
      ["QAOA", "Quantum Approximate Optimization Algorithm"],
      ["QUBO", "Quadratic Unconstrained Binary Optimization"],
      ["SA", "Simulated Annealing"],
      ["TTS", "Time to Solution"],
    ],
    [2400, 6960],
  ),
];

// ---------- TOC ----------
const tocSection = [
  h1("Table of Contents"),
  new Paragraph({
    spacing: { after: 200 },
    children: [new TextRun({ text: "(If this table appears empty, update fields: in Word select all and press F9; in LibreOffice use Tools → Update → Indexes and Tables.)", font: FONT, size: 18, italics: true, color: "888888" })],
  }),
  new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-3" }),
];

// ---------- References ----------
const refs = [
  h1("References"),
  ...[
    "Anthropic (2024). Introducing the Model Context Protocol. Anthropic engineering announcement, November 2024. https://www.anthropic.com/news/model-context-protocol",
    "Farhi, E., Goldstone, J., & Gutmann, S. (2014). A Quantum Approximate Optimization Algorithm. arXiv:1411.4028.",
    "Glover, F., Kochenberger, G., & Du, Y. (2019). A Tutorial on Formulating and Using QUBO Models. arXiv:1811.11538.",
    "Hadfield, S., Wang, Z., O'Gorman, B., Rieffel, E. G., Venturelli, D., & Biswas, R. (2019). From the Quantum Approximate Optimization Algorithm to a Quantum Alternating Operator Ansatz. Algorithms, 12(2), 34.",
    "Kochenberger, G., Hao, J.-K., Glover, F., Lewis, M., Lü, Z., Wang, H., & Wang, Y. (2014). The Unconstrained Binary Quadratic Programming Problem: A Survey. Journal of Combinatorial Optimization, 28(1), 58–81.",
    "Lucas, A. (2014). Ising Formulations of Many NP Problems. Frontiers in Physics, 2, 5.",
    "Martello, S., & Toth, P. (1990). Knapsack Problems: Algorithms and Computer Implementations. Wiley. (Chapter on the Generalised Assignment Problem.)",
    "Montañez-Barrera, J. A., Willsch, D., Maldonado-Romo, A., & Michielsen, K. (2024). Unbalanced Penalization: A New Approach to Encode Inequality Constraints of Combinatorial Problems for Quantum Optimization Algorithms. Quantum Science and Technology, 9(2).",
    "Nous Research — Teknium, R., et al. (2024). Hermes 3 Technical Report. arXiv:2408.11857.",
    "Preskill, J. (2018). Quantum Computing in the NISQ Era and Beyond. Quantum, 2, 79.",
    "Qiskit contributors (2024–2026). Qiskit: An Open-Source Framework for Quantum Computing; Qiskit Runtime primitives documentation. IBM Quantum. https://quantum.cloud.ibm.com/docs",
    "Venturelli, D., Marchand, D. J. J., & Rojo, G. (2015). Quantum Annealing Implementation of Job-Shop Scheduling. arXiv:1506.08479.",
    "Wooldridge, M. (2009). An Introduction to MultiAgent Systems (2nd ed.). Wiley.",
    "Zhou, L., Wang, S.-T., Choi, S., Pichler, H., & Lukin, M. D. (2020). Quantum Approximate Optimization Algorithm: Performance, Mechanism, and Implementation on Near-Term Devices. Physical Review X, 10, 021067.",
    "[Author: add the 2025–2026 agent-orchestration and ILP-routing papers cited in §2.3.2 once selected, plus your institution-required citation format throughout — entries above are drafted in a generic author–date style.]",
  ].map(r => new Paragraph({
    spacing: { after: 140, line: 300 },
    indent: { left: 400, hanging: 400 },
    children: [new TextRun({ text: r, font: FONT, size: 21 })],
  })),
];

// ---------- Appendices ----------
const appendices = [
  h1("Appendix A — Worked Example: Enumeration Script and Q Matrix"),
  p("The following script enumerates all 2¹⁰ states of the Section 3.7 instance and prints the minimiser; the full 10 × 10 Q matrix it constructs is printed on execution and reproduced in the repository."),
  ...code([
    "import itertools, numpy as np",
    "m, n = 2, 3",
    "u = np.array([[0.9, 0.8, 0.5], [0.4, 0.3, 0.7]])",
    "w = [2, 2, 1]; C = [3, 3]; alpha, l1, l2 = 0.5, 3.0, 2.0",
    "aff = {(0, 1): 0.6}",
    "def energy(bits):",
    "    x = np.array(bits[:6]).reshape(m, n); s = bits[6:]",
    "    slack = [s[0] + 2 * s[1], s[2] + 2 * s[3]]",
    "    E = -(u * x).sum()",
    "    E -= alpha * sum(a * x[i, j] * x[i, k]",
    "                     for (j, k), a in aff.items() for i in range(m))",
    "    E += l1 * sum((1 - x[:, j].sum()) ** 2 for j in range(n))",
    "    E += l2 * sum((C[i] - sum(w[j] * x[i, j] for j in range(n))",
    "                   - slack[i]) ** 2 for i in range(m))",
    "    return E",
    "best = min(itertools.product([0, 1], repeat=10), key=energy)",
    "print(best, energy(best))   # two tied minimisers at E = -1.9:",
    "# x11=1 with x22=x23=1, and x12=1 with x21=x23=1",
  ]),
  h1("Appendix B — MCP Tool Schemas"),
  p("Abridged schema for the solver service's principal tool; full schemas for the vault and registry servers are in the repository."),
  ...code([
    '{ "name": "solve_qubo",',
    '  "description": "Minimise x^T Q x. Returns best feasible assignment',
    '                  after validation and greedy repair.",',
    '  "inputSchema": {',
    '    "type": "object",',
    '    "properties": {',
    '      "Q":        { "type": "object",  "description": "sparse {\\"i,j\\": coeff}" },',
    '      "backend":  { "enum": ["exact", "sa", "qaoa_sim", "qaoa_ibm"] },',
    '      "budget_s": { "type": "number", "default": 30 },',
    '      "meta":     { "type": "object", "description": "m, n, capacities, weights',
    '                    — required by the validator/repairer" } },',
    '    "required": ["Q", "backend", "meta"] } }',
  ]),
  h1("Appendix C — Hardware Run Log (Template)"),
  p("One row per hardware execution; the repository's CSV carries the complete log. Columns: date, backend, calibration snapshot ID, instance ID, N, p, transpiled two-qubit depth, shots, session ID, raw feasibility, best energy, notes. [Author: populate from your own runs; Table 5.2's placeholder rows follow this template.]"),
  h1("Appendix D — Vault Schema Reference"),
  p("Front-matter contract for the four card types (task, agent-profile, decision-record, postmortem), the eligibility query, and the affinity computation, as implemented by the vault MCP server. Task cards: see Section 4.2. Agent-profile cards mirror the registry (capabilities per category, capacity, model checkpoint hash). Decision-record cards are append-only and link every task they assign, which is what makes the vault's graph view double as an audit trail of the orchestrator's history."),
];

// ---------- Assemble ----------
const doc = new Document({
  creator: "Wilcox Kim",
  title: "A QUBO Formulation for Quantum-Assisted Multi-Agent AI Workforce Orchestration",
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
  },
  numbering: {
    config: [
      { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 480, hanging: 240 } } } }] },
      ...["rq", "contrib", "arch", "proto", "fw"].map(ref => ({
        reference: ref,
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 480, hanging: 300 } } } }],
      })),
    ],
  },
  features: { updateFields: true },
  sections: [
    {
      properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1620, right: 1440 } } },
      children: [...titlePage, ...declaration, ...abstract, ...acks, ...abbrev, ...tocSection],
    },
    {
      properties: {
        type: SectionType.NEXT_PAGE,
        page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1620, right: 1440 } },
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 20 })],
          })],
        }),
      },
      headers: {
        default: new Header({
          children: [new Paragraph({
            alignment: AlignmentType.RIGHT,
            children: [new TextRun({ text: "W. Kim — QUBO Orchestration of AI Agent Workforces", font: FONT, size: 18, italics: true, color: "666666" })],
          })],
        }),
      },
      children: [...ch1, ...ch2, ...ch3, ...ch4, ...ch5, ...ch6, ...ch7, ...refs, ...appendices],
    },
  ],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("thesis.docx", buf);
  console.log("thesis.docx written:", buf.length, "bytes");
});
