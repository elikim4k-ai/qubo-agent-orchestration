"""MCP file server over the vault (thesis §4.1 process 1).

Read-mostly surface for worker agents; write tools are intended to be
allow-listed to the orchestrator role only (§4.4). Destructive operations
(card deletion, status rollback) are deliberately NOT exposed as tools.

Run:  python -m src.vault.mcp_server [vault_root]
Requires the `mcp` package; the underlying operations live in store.Vault and
are fully usable (and tested) without it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .store import DecisionRecord, TaskCard, Vault

ROLE_TOOLS = {
    # per-role allow-list (§4.4); enforcement belongs to whoever wires agents up
    "worker": {"read_note", "get_task", "search_tasks"},
    "orchestrator": {
        "read_note", "get_task", "search_tasks", "eligible_tasks",
        "create_task", "set_task_status", "write_decision",
    },
}


def build_server(vault_root: str | Path):
    from mcp.server.fastmcp import FastMCP  # lazy: optional dependency

    vault = Vault(vault_root)
    server = FastMCP("qubo-vault")

    @server.tool()
    def get_task(task_id: str) -> str:
        """Read one task card (front-matter + body) by id."""
        card = vault.get_task(task_id)
        return card.render()

    @server.tool()
    def search_tasks(status: str = "", category: str = "") -> str:
        """Search task cards by front-matter fields; returns JSON summaries."""
        cards = vault.tasks(status or None)
        if category:
            cards = [c for c in cards if c.category == category]
        return json.dumps([
            {"id": c.id, "title": c.title, "category": c.category,
             "effort": c.effort, "status": c.status}
            for c in cards
        ])

    @server.tool()
    def eligible_tasks() -> str:
        """Task ids whose dependencies are complete (orchestrator only)."""
        return json.dumps([c.id for c in vault.eligible_tasks()])

    @server.tool()
    def read_note(name: str) -> str:
        """Resolve a wiki-link target to note text; empty string if absent."""
        return vault.read_note(name) or ""

    @server.tool()
    def create_task(card_markdown: str) -> str:
        """Create/update a task card from full Markdown (validated on parse)."""
        card = TaskCard.parse(card_markdown)
        return str(vault.write_task(card))

    @server.tool()
    def set_task_status(task_id: str, status: str) -> str:
        """Advance a task's status (draft|eligible|assigned|done|failed)."""
        vault.set_task_status(task_id, status)
        return "ok"

    @server.tool()
    def write_decision(epoch: int, backend: str, energy: float,
                       assignment_json: str, calibration_snapshot: str = "") -> str:
        """Append an epoch decision record (audit trail, thesis §4.2)."""
        record = DecisionRecord(
            epoch=epoch, backend=backend, energy=energy,
            assignment=json.loads(assignment_json),
            calibration_snapshot=calibration_snapshot,
        )
        return str(vault.write_decision(record))

    return server


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "vault"
    build_server(root).run()
