"""Registry (thesis §3.1/§4.1): folds harness telemetry into per
(agent, category) profiles with exponential decay (half-life = 20
completions) and serves the QUBO coefficients:

    u_ij = clip(s_i,cat(j) * p_i,cat(j) - kappa * c_hat_ij, 0, 1)

where p is the decayed empirical success rate, s the decayed competence
score (tool-call validity rate — the harness's cleanest skill proxy), and
c_hat the predicted token cost normalised into [0,1].

This module is the vault-poisoning surface (§4.4, §5.7 week-two incident):
every event is schema-validated upstream (harness.telemetry.read_events)
and range-validated again here. Reject, never repair.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..harness.telemetry import read_events
from ..vault.store import AgentProfile, TaskCard

HALF_LIFE_COMPLETIONS = 20
DECAY = 0.5 ** (1.0 / HALF_LIFE_COMPLETIONS)
KAPPA_DEFAULT = 0.3
MAX_SANE_TOKENS = 1_000_000       # per task; beyond this the event is hostile or broken
MAX_SANE_DURATION_MS = 6 * 3600 * 1000
_CATEGORY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

_PRIOR = {"s": 0.5, "p": 0.5, "tokens": None}  # optimistic-neutral cold start


@dataclass
class CategoryProfile:
    """Decayed running statistics for one (agent, category) pair."""
    weight: float = 0.0            # decayed observation mass
    p_num: float = 0.0             # decayed successes
    s_num: float = 0.0             # decayed tool-validity mass
    tokens_num: float = 0.0        # decayed total tokens
    duration_num: float = 0.0
    completions: int = 0

    def observe(self, success: bool, validity_rate: float,
                tokens: int, duration_ms: int) -> None:
        self.weight = self.weight * DECAY + 1.0
        self.p_num = self.p_num * DECAY + (1.0 if success else 0.0)
        self.s_num = self.s_num * DECAY + validity_rate
        self.tokens_num = self.tokens_num * DECAY + float(tokens)
        self.duration_num = self.duration_num * DECAY + float(duration_ms)
        self.completions += 1

    @property
    def p(self) -> float:
        return self.p_num / self.weight if self.weight else _PRIOR["p"]

    @property
    def s(self) -> float:
        return self.s_num / self.weight if self.weight else _PRIOR["s"]

    @property
    def mean_tokens(self) -> float | None:
        return self.tokens_num / self.weight if self.weight else None

    def as_dict(self) -> dict:
        return {"p": round(self.p, 4), "s": round(self.s, 4),
                "mean_tokens": round(self.mean_tokens or 0.0, 1),
                "completions": self.completions}


def _valid_completion(ev: dict) -> bool:
    """Range checks past the JSON schema — the poisoning fence."""
    if not _CATEGORY_RE.match(str(ev.get("category", ""))):
        return False
    tokens = (ev.get("tokens_prompt") or 0) + (ev.get("tokens_completion") or 0)
    if not (0 <= tokens <= MAX_SANE_TOKENS):
        return False
    dur = ev.get("duration_ms") or 0
    if not (0 <= dur <= MAX_SANE_DURATION_MS):
        return False
    return True


class Registry:
    def __init__(self, kappa: float = KAPPA_DEFAULT):
        self.kappa = kappa
        self.profiles: dict[tuple[str, str], CategoryProfile] = {}
        self.rejected = 0
        # per-task accumulators between terminal events
        self._task_tool_calls: dict[tuple[str, str], list[bool]] = {}

    # -- ingestion ---------------------------------------------------------
    def ingest(self, events: list[dict]) -> None:
        for ev in events:
            self._ingest_one(ev)

    def _ingest_one(self, ev: dict) -> None:
        key = (ev["agent_id"], ev["task_id"])
        kind = ev["event"]
        if kind == "tool_call":
            self._task_tool_calls.setdefault(key, []).append(bool(ev.get("tool_call_valid")))
            return
        if kind not in ("task_done", "task_failed"):
            return
        if not _valid_completion(ev):
            self.rejected += 1
            self._task_tool_calls.pop(key, None)
            return
        calls = self._task_tool_calls.pop(key, [])
        validity_rate = (sum(calls) / len(calls)) if calls else 1.0
        tokens = (ev.get("tokens_prompt") or 0) + (ev.get("tokens_completion") or 0)
        prof = self.profiles.setdefault((ev["agent_id"], ev["category"]),
                                        CategoryProfile())
        prof.observe(kind == "task_done", validity_rate, tokens,
                     ev.get("duration_ms") or 0)

    @classmethod
    def from_telemetry(cls, path: str | Path, kappa: float = KAPPA_DEFAULT) -> "Registry":
        reg = cls(kappa)
        events, rejected = read_events(path)
        reg.rejected += rejected
        reg.ingest(events)
        return reg

    # -- coefficient service (§4.1 process 5) --------------------------------
    def _cost_norm(self) -> float:
        means = [p.mean_tokens for p in self.profiles.values() if p.mean_tokens]
        return max(means) if means else 1.0

    def utility(self, agent_id: str, category: str, norm: float | None = None) -> float:
        prof = self.profiles.get((agent_id, category))
        if prof is None or prof.weight == 0.0:
            s, p, c_hat = _PRIOR["s"], _PRIOR["p"], 0.5
        else:
            s, p = prof.s, prof.p
            c_hat = (prof.mean_tokens or 0.0) / (norm or self._cost_norm())
        u = s * p - self.kappa * min(1.0, c_hat)
        return min(1.0, max(0.0, u))

    def utilities(self, agents: list[AgentProfile],
                  tasks: list[TaskCard]) -> list[list[float]]:
        norm = self._cost_norm()
        return [[self.utility(a.id, t.category, norm) for t in tasks] for a in agents]

    def calibrated_weights(self, tasks: list[TaskCard]) -> list[int]:
        """Effort calibration: scale declared effort by how expensive the
        category has actually been (tokens per declared unit) relative to the
        fleet-wide mean. Falls back to declared effort with no history."""
        per_unit: dict[str, list[float]] = {}
        declared: dict[str, list[int]] = {}
        for (agent, cat), prof in self.profiles.items():
            if prof.mean_tokens:
                per_unit.setdefault(cat, []).append(prof.mean_tokens)
        cat_mean = {c: sum(v) / len(v) for c, v in per_unit.items()}
        if not cat_mean:
            return [t.effort for t in tasks]
        global_mean = sum(cat_mean.values()) / len(cat_mean)
        out = []
        for t in tasks:
            factor = cat_mean.get(t.category, global_mean) / global_mean
            out.append(max(1, round(t.effort * factor)))
        return out

    def coefficients(self, agents: list[AgentProfile], tasks: list[TaskCard]
                     ) -> tuple[list[list[float]], list[int], list[int]]:
        """(utilities m x n, calibrated weights n, capacities m)."""
        return (self.utilities(agents, tasks),
                self.calibrated_weights(tasks),
                [a.capacity for a in agents])

    # -- persistence into vault agent cards ---------------------------------
    def sync_to_vault(self, vault) -> None:
        for agent in vault.agents():
            cats = {cat: prof.as_dict()
                    for (aid, cat), prof in sorted(self.profiles.items()) if aid == agent.id}
            if cats:
                agent.categories = cats
                vault.write_agent(agent)
