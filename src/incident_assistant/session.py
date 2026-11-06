"""
A case session: one store, one case, one gateway enforcing the assistant's policy.

open_session() performs the person's first step, recording when the incident response
procedures were activated. Everything after that is the agent's, through the gateway,
until a person records the notifiability decision and approves a send.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from itops_mcp_gateway import Gateway

from .corpus import Corpus
from .store import Store
from .tools import Context, build_policy

SCENARIOS = Path(__file__).parent / "data" / "scenarios"


def load_scenario(name: str) -> dict[str, Any]:
    path = SCENARIOS / f"{name}.json"
    if not path.exists():
        known = sorted(p.stem for p in SCENARIOS.glob("*.json"))
        raise FileNotFoundError(f"unknown scenario {name!r}; known: {known}")
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class Session:
    scenario: dict[str, Any]
    store: Store
    corpus: Corpus
    case_id: str
    gateway: Gateway

    # ---- the person's actions. None of these are tools. ----

    def record_decision(self, notifiable: bool, decided_by: str, rationale: str) -> None:
        self.store.record_decision(self.case_id, notifiable, decided_by, rationale)

    def approve(self, approval_id: str, approver: str, approved: bool = True) -> dict[str, Any]:
        return self.gateway.approve(approval_id, approver, approved)

    def close(self) -> None:
        self.gateway.close()
        self.store.close()


def open_session(scenario_name: str, workdir: str | Path,
                 activated_by: str | None = None) -> Session:
    scenario = load_scenario(scenario_name)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    db = workdir / f"{scenario_name}.db"
    gw_db = workdir / f"{scenario_name}.gateway.db"
    # Each run starts a fresh case. Earlier runs' files are replaced, not merged.
    for f in (db, gw_db):
        if f.exists():
            f.unlink()
    store = Store(db)
    store.load_scenario(scenario)
    act = scenario["activation"]
    case_id = store.open_case(scenario["scenario"], act["activated_at"],
                              activated_by or act["activated_by"])
    corpus = Corpus.load()
    ctx = Context(store=store, corpus=corpus, case_id=case_id, operator=scenario["operator"],
                  alert=scenario.get("alert"))
    gw = Gateway(backend=ctx, db_path=str(gw_db),
                 policy=build_policy())
    return Session(scenario, store, corpus, case_id, gw)
