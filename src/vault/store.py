"""Obsidian-vault store (thesis §4.2): typed front-matter cards over plain
Markdown, wiki-link affinity, and the validation discipline of §4.4 — vault
content is untrusted model input, so every card passes an allow-list filter
before anything downstream sees it. Fields the schema does not recognise are
stripped (and reported), never forwarded into agent context or the registry.

Schemas mirror vault/templates/*.md exactly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

WIKILINK_RE = re.compile(r"\[\[([^\]\|#]+)(?:[\|#][^\]]*)?\]\]")
AFFINITY_THRESHOLD = 0.2  # thesis §3.1: keeps Q sparse / circuit depth sane

TASK_STATUSES = {"draft", "eligible", "assigned", "done", "failed"}
TASK_FIELDS = {
    "type", "id", "title", "category", "effort", "status",
    "depends_on", "conflicts_with", "affinity_group", "created",
}
AGENT_FIELDS = {"type", "id", "model_checkpoint", "capacity", "categories"}
DECISION_FIELDS = {
    "type", "epoch", "backend", "energy", "calibration_snapshot", "assignment",
}
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class VaultValidationError(ValueError):
    """A card failed the untrusted-input checks."""


def outgoing_links(body: str) -> set[str]:
    """Normalised outgoing wiki-link targets of a note body."""
    return {m.group(1).strip().casefold() for m in WIKILINK_RE.finditer(body)}


def jaccard_affinity(link_sets: list[set[str]],
                     threshold: float = AFFINITY_THRESHOLD) -> dict[tuple[int, int], float]:
    """a_jk = Jaccard overlap of outgoing link sets, thresholded (thesis §3.1)."""
    aff: dict[tuple[int, int], float] = {}
    for j in range(len(link_sets)):
        for k in range(j + 1, len(link_sets)):
            union = link_sets[j] | link_sets[k]
            if not union:
                continue
            a = len(link_sets[j] & link_sets[k]) / len(union)
            if a >= threshold:
                aff[(j, k)] = a
    return aff


def _parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise VaultValidationError("card has no front-matter block")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise VaultValidationError("unterminated front-matter block")
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as e:
        raise VaultValidationError(f"front-matter is not valid YAML: {e}") from e
    if not isinstance(fm, dict):
        raise VaultValidationError("front-matter must be a mapping")
    return fm, parts[2].lstrip("\n")


def _filter_fields(fm: dict, allowed: set[str]) -> tuple[dict, list[str]]:
    """Allow-list filter (§4.4): unknown, possibly instruction-shaped fields
    are dropped and reported to the caller, never propagated."""
    kept = {k: v for k, v in fm.items() if k in allowed}
    stripped = sorted(k for k in fm if k not in allowed)
    return kept, stripped


def _require_id(value, kind: str) -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise VaultValidationError(f"{kind} id {value!r} is not a safe identifier")
    return value


def _string_list(value, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise VaultValidationError(f"{field_name} must be a list of ids")
    return [_require_id(v, field_name) for v in value]


@dataclass
class TaskCard:
    id: str
    title: str = ""
    category: str = ""
    effort: int = 1
    status: str = "draft"
    depends_on: list[str] = field(default_factory=list)
    conflicts_with: list[str] = field(default_factory=list)
    affinity_group: str = ""
    created: str = ""
    body: str = ""
    stripped_fields: list[str] = field(default_factory=list)

    @property
    def links(self) -> set[str]:
        return outgoing_links(self.body)

    @classmethod
    def parse(cls, text: str) -> "TaskCard":
        fm, body = _parse_front_matter(text)
        fm, stripped = _filter_fields(fm, TASK_FIELDS)
        if fm.get("type") != "task":
            raise VaultValidationError(f"not a task card (type={fm.get('type')!r})")
        card = cls(
            id=_require_id(fm.get("id"), "task"),
            title=str(fm.get("title") or ""),
            category=str(fm.get("category") or ""),
            effort=fm.get("effort", 1),
            status=str(fm.get("status") or "draft"),
            depends_on=_string_list(fm.get("depends_on"), "depends_on"),
            conflicts_with=_string_list(fm.get("conflicts_with"), "conflicts_with"),
            affinity_group=str(fm.get("affinity_group") or ""),
            created=str(fm.get("created") or ""),
            body=body,
            stripped_fields=stripped,
        )
        if not isinstance(card.effort, int) or isinstance(card.effort, bool) or card.effort < 1:
            raise VaultValidationError(f"task {card.id}: effort must be a positive integer")
        if card.status not in TASK_STATUSES:
            raise VaultValidationError(f"task {card.id}: unknown status {card.status!r}")
        return card

    def render(self) -> str:
        fm = {
            "type": "task", "id": self.id, "title": self.title,
            "category": self.category, "effort": self.effort, "status": self.status,
            "depends_on": self.depends_on, "conflicts_with": self.conflicts_with,
            "affinity_group": self.affinity_group, "created": self.created,
        }
        return f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n{self.body}"


@dataclass
class AgentProfile:
    id: str
    model_checkpoint: str = ""
    capacity: int = 8
    categories: dict = field(default_factory=dict)  # registry-owned, do not hand-edit

    @classmethod
    def parse(cls, text: str) -> "AgentProfile":
        fm, _ = _parse_front_matter(text)
        fm, _stripped = _filter_fields(fm, AGENT_FIELDS)
        if fm.get("type") != "agent-profile":
            raise VaultValidationError(f"not an agent profile (type={fm.get('type')!r})")
        profile = cls(
            id=_require_id(fm.get("id"), "agent"),
            model_checkpoint=str(fm.get("model_checkpoint") or ""),
            capacity=fm.get("capacity", 8),
            categories=fm.get("categories") or {},
        )
        if (not isinstance(profile.capacity, int) or isinstance(profile.capacity, bool)
                or profile.capacity < 1):
            raise VaultValidationError(f"agent {profile.id}: capacity must be a positive integer")
        if not isinstance(profile.categories, dict):
            raise VaultValidationError(f"agent {profile.id}: categories must be a mapping")
        return profile

    def render(self) -> str:
        fm = {
            "type": "agent-profile", "id": self.id,
            "model_checkpoint": self.model_checkpoint, "capacity": self.capacity,
            "categories": self.categories,
        }
        return f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n"


@dataclass
class DecisionRecord:
    epoch: int
    backend: str
    energy: float
    assignment: dict[str, list[str]]              # agent id -> task ids
    calibration_snapshot: str = ""
    body: str = ""

    def render(self) -> str:
        fm = {
            "type": "decision-record", "epoch": self.epoch, "backend": self.backend,
            "energy": self.energy, "calibration_snapshot": self.calibration_snapshot,
            "assignment": self.assignment,
        }
        links = "\n".join(
            f"- [[{tid}]] -> agent [[{aid}]]"
            for aid, tids in sorted(self.assignment.items()) for tid in tids
        )
        body = self.body or f"Epoch {self.epoch} assignment (audit trail, thesis §4.2).\n{links}\n"
        return f"---\n{yaml.safe_dump(fm, sort_keys=False)}---\n{body}"


class Vault:
    """Filesystem-backed vault rooted at a directory with tasks/, agents/,
    decisions/, postmortems/, templates/ (see vault/)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        for sub in ("tasks", "agents", "decisions", "postmortems", "templates"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    # -- tasks ------------------------------------------------------------
    def _task_path(self, task_id: str) -> Path:
        return self.root / "tasks" / f"{_require_id(task_id, 'task')}.md"

    def write_task(self, card: TaskCard) -> Path:
        path = self._task_path(card.id)
        path.write_text(card.render(), encoding="utf-8")
        return path

    def get_task(self, task_id: str) -> TaskCard:
        return TaskCard.parse(self._task_path(task_id).read_text(encoding="utf-8"))

    def tasks(self, status: str | None = None) -> list[TaskCard]:
        out = []
        for p in sorted((self.root / "tasks").glob("*.md")):
            try:
                card = TaskCard.parse(p.read_text(encoding="utf-8"))
            except VaultValidationError:
                continue  # quarantined: malformed cards never reach the optimizer
            if status is None or card.status == status:
                out.append(card)
        return out

    def eligible_tasks(self) -> list[TaskCard]:
        """Tasks whose status is 'eligible' and whose dependencies are all done
        (thesis §3.1: dependency handling via eligibility, not optimization)."""
        by_id = {c.id: c for c in self.tasks()}
        return [
            c for c in by_id.values()
            if c.status == "eligible"
            and all(d in by_id and by_id[d].status == "done" for d in c.depends_on)
        ]

    def set_task_status(self, task_id: str, status: str) -> None:
        if status not in TASK_STATUSES:
            raise VaultValidationError(f"unknown status {status!r}")
        card = self.get_task(task_id)
        card.status = status
        self.write_task(card)

    def affinity(self, cards: list[TaskCard],
                 threshold: float = AFFINITY_THRESHOLD) -> dict[tuple[int, int], float]:
        return jaccard_affinity([c.links for c in cards], threshold)

    def exclusions(self, cards: list[TaskCard]) -> set[tuple[int, int]]:
        """Anti-affinity pairs among `cards`, as index pairs j<k (thesis Eₓ)."""
        index = {c.id: j for j, c in enumerate(cards)}
        out = set()
        for j, c in enumerate(cards):
            for other in c.conflicts_with:
                if other in index and index[other] != j:
                    a, b = sorted((j, index[other]))
                    out.add((a, b))
        return out

    # -- agents -----------------------------------------------------------
    def write_agent(self, profile: AgentProfile) -> Path:
        path = self.root / "agents" / f"{profile.id}.md"
        path.write_text(profile.render(), encoding="utf-8")
        return path

    def agents(self) -> list[AgentProfile]:
        out = []
        for p in sorted((self.root / "agents").glob("*.md")):
            try:
                out.append(AgentProfile.parse(p.read_text(encoding="utf-8")))
            except VaultValidationError:
                continue
        return out

    # -- notes / links ----------------------------------------------------
    def read_note(self, name: str) -> str | None:
        """Resolve a wiki-link target to note text anywhere in the vault."""
        want = name.strip().casefold()
        for p in self.root.rglob("*.md"):
            if p.stem.casefold() == want:
                return p.read_text(encoding="utf-8")
        return None

    # -- decisions ----------------------------------------------------------
    def write_decision(self, record: DecisionRecord) -> Path:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = self.root / "decisions" / f"epoch-{record.epoch:05d}-{stamp}.md"
        path.write_text(record.render(), encoding="utf-8")
        return path

    def decisions(self) -> list[Path]:
        return sorted((self.root / "decisions").glob("epoch-*.md"))
