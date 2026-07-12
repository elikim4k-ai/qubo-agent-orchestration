"""MCP wrapper for the solver service (thesis §4.1 process 3, Appendix B).

Exposes exactly one significant tool: solve_qubo. Only the orchestrator role
should see this tool (§4.4 allow-listing).

Run:  python -m src.solver.mcp_server
"""
from __future__ import annotations

import json


def build_server():
    from mcp.server.fastmcp import FastMCP  # lazy: optional dependency

    from ..qubo.builder import Instance
    from .service import solve_qubo as _solve

    server = FastMCP("qubo-solver")

    @server.tool()
    def solve_qubo(instance_json: str, backend: str = "exact",
                   budget_s: float = 30.0, meta_json: str = "{}") -> str:
        """Solve one epoch assignment instance.

        instance_json: {"utilities": [[...]], "weights": [...],
                        "capacities": [...], "affinity": {"j,k": a, ...},
                        "exclusions": [[j,k], ...], "alpha": 0.5}
        backend: exact | brute | sa | qaoa_sim | qaoa_ibm
        Returns the SolveResult schema (identical for every backend).
        """
        raw = json.loads(instance_json)
        inst = Instance(
            utilities=raw["utilities"],
            weights=raw["weights"],
            capacities=raw["capacities"],
            affinity={tuple(int(x) for x in k.split(",")): float(v)
                      for k, v in (raw.get("affinity") or {}).items()},
            exclusions={tuple(sorted((int(j), int(k))))
                        for j, k in (raw.get("exclusions") or [])},
            alpha=float(raw.get("alpha", 0.5)),
        )
        result = _solve(inst, backend=backend, budget_s=budget_s,
                        meta=json.loads(meta_json))
        return json.dumps(result.to_dict())

    return server


if __name__ == "__main__":
    build_server().run()
