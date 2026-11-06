"""
Evidence store.

One SQLite database per run holding three kinds of data:

  telemetry   sign-ins, process events, network flows, audit events, plus the asset,
              identity and data inventories. Read-only to the agent. Every telemetry
              row carries an evidence ID such as SIG-0007, and every factual claim in
              a draft must cite one.
  case work   the case, the evidence timeline, criterion assessments and drafts.
              Written by the agent through WRITE-tier tools.
  decisions   the activation time, the notifiability decision and the outbox.
              Written only by people, through functions that are not tools.

The timeline is append-only and hash-chained: each entry stores the hash of the one
before it, so altering or removing an entry breaks every hash after it.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TELEMETRY_TABLES = ("signins", "process_events", "network_flows", "audit_events")

SCHEMA = """
CREATE TABLE IF NOT EXISTS signins (
    evidence_id TEXT PRIMARY KEY, ts TEXT NOT NULL, user TEXT NOT NULL,
    host TEXT, source_ip TEXT, result TEXT, mfa TEXT, user_agent TEXT);
CREATE TABLE IF NOT EXISTS process_events (
    evidence_id TEXT PRIMARY KEY, ts TEXT NOT NULL, host TEXT NOT NULL,
    user TEXT, process TEXT, command_line TEXT);
CREATE TABLE IF NOT EXISTS network_flows (
    evidence_id TEXT PRIMARY KEY, ts TEXT NOT NULL, src_host TEXT NOT NULL,
    dst TEXT NOT NULL, dst_port INTEGER, bytes_out INTEGER, bytes_in INTEGER);
CREATE TABLE IF NOT EXISTS audit_events (
    evidence_id TEXT PRIMARY KEY, ts TEXT NOT NULL, actor TEXT NOT NULL,
    action TEXT NOT NULL, target TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS assets (
    host TEXT PRIMARY KEY, role TEXT NOT NULL, gaming_critical INTEGER NOT NULL,
    notes TEXT);
CREATE TABLE IF NOT EXISTS identities (
    user TEXT PRIMARY KEY, kind TEXT NOT NULL, department TEXT, usual_hosts TEXT);
CREATE TABLE IF NOT EXISTS data_inventory (
    host TEXT NOT NULL, data_class TEXT NOT NULL, personal_information INTEGER NOT NULL,
    description TEXT, PRIMARY KEY (host, data_class));

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY, scenario TEXT NOT NULL, activated_at TEXT NOT NULL,
    activated_by TEXT NOT NULL, meeting_held INTEGER NOT NULL DEFAULT 0,
    opened_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS timeline (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
    event_time TEXT NOT NULL, summary TEXT NOT NULL, evidence_ids TEXT NOT NULL,
    injection_flagged INTEGER NOT NULL DEFAULT 0, recorded_at TEXT NOT NULL,
    recorded_by TEXT NOT NULL, prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS assessments (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
    criterion TEXT NOT NULL, status TEXT NOT NULL, evidence_ids TEXT NOT NULL,
    rationale TEXT NOT NULL, set_at TEXT NOT NULL, set_by TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY, case_id TEXT NOT NULL, kind TEXT NOT NULL,
    body TEXT NOT NULL, validation TEXT NOT NULL, created_at TEXT NOT NULL,
    created_by TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
    notifiable INTEGER NOT NULL, decided_by TEXT NOT NULL, decided_at TEXT NOT NULL,
    rationale TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS outbox (
    seq INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
    draft_id TEXT NOT NULL, kind TEXT NOT NULL, queued_at TEXT NOT NULL);
"""

GENESIS = "0" * 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _entry_hash(prev_hash: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


class StoreError(ValueError):
    pass


class Store:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    # ---------------------------------------------------------------- loading

    def load_scenario(self, scenario: dict[str, Any]) -> None:
        """Load telemetry and inventories. Refuses duplicate evidence IDs across tables,
        because a citation must resolve to exactly one record."""
        seen: set[str] = set()
        for table in TELEMETRY_TABLES:
            for row in scenario.get(table, []):
                eid = row["evidence_id"]
                if eid in seen:
                    raise StoreError(f"duplicate evidence_id {eid}")
                seen.add(eid)
                cols = ",".join(row)
                marks = ",".join("?" for _ in row)
                self.conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})",
                                  tuple(row.values()))
        for row in scenario.get("assets", []):
            self.conn.execute("INSERT INTO assets VALUES (?,?,?,?)",
                              (row["host"], row["role"], int(row["gaming_critical"]),
                               row.get("notes", "")))
        for row in scenario.get("identities", []):
            self.conn.execute("INSERT INTO identities VALUES (?,?,?,?)",
                              (row["user"], row["kind"], row.get("department", ""),
                               ",".join(row.get("usual_hosts", []))))
        for row in scenario.get("data_inventory", []):
            self.conn.execute("INSERT INTO data_inventory VALUES (?,?,?,?)",
                              (row["host"], row["data_class"],
                               int(row["personal_information"]), row.get("description", "")))
        self.conn.commit()

    # ---------------------------------------------------------------- evidence

    def evidence(self, evidence_id: str) -> dict[str, Any] | None:
        for table in TELEMETRY_TABLES:
            row = self.conn.execute(f"SELECT * FROM {table} WHERE evidence_id = ?",
                                    (evidence_id,)).fetchone()
            if row is not None:
                return {"table": table, **dict(row)}
        return None

    def query(self, table: str, filters: dict[str, Any], since: str | None = None,
              until: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if table not in TELEMETRY_TABLES:
            raise StoreError(f"unknown table {table}")
        clauses, params = [], []
        for col, val in filters.items():
            if val is None:
                continue
            if col == "min_bytes_out":
                clauses.append("bytes_out >= ?")
            else:
                clauses.append(f"{col} = ?")
            params.append(val)
        if since:
            clauses.append("ts >= ?")
            params.append(since)
        if until:
            clauses.append("ts <= ?")
            params.append(until)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.conn.execute(
            f"SELECT * FROM {table} {where} ORDER BY ts LIMIT ?", (*params, int(limit))
        ).fetchall()
        return [dict(r) for r in rows]

    def one(self, table: str, key: str, value: str) -> dict[str, Any] | None:
        row = self.conn.execute(f"SELECT * FROM {table} WHERE {key} = ?", (value,)).fetchone()
        return dict(row) if row else None

    def many(self, table: str, key: str, value: str) -> list[dict[str, Any]]:
        return [dict(r) for r in
                self.conn.execute(f"SELECT * FROM {table} WHERE {key} = ?", (value,))]

    # ---------------------------------------------------------------- people only

    def open_case(self, scenario: str, activated_at: str, activated_by: str,
                  meeting_held: bool = False) -> str:
        """Called by a person. The agent has no tool that reaches this."""
        datetime.fromisoformat(activated_at)  # refuse a malformed timestamp
        case_id = f"CASE-{uuid.uuid4().hex[:8].upper()}"
        self.conn.execute("INSERT INTO cases VALUES (?,?,?,?,?,?)",
                          (case_id, scenario, activated_at, activated_by,
                           int(meeting_held), _now()))
        self.conn.commit()
        return case_id

    def record_decision(self, case_id: str, notifiable: bool, decided_by: str,
                        rationale: str) -> None:
        """The notifiability decision. Called by a person, never by a tool."""
        if not decided_by or decided_by.lower().endswith("_agent"):
            raise StoreError("the notifiability decision must be recorded by a person")
        self.conn.execute(
            "INSERT INTO decisions (case_id, notifiable, decided_by, decided_at, rationale)"
            " VALUES (?,?,?,?,?)", (case_id, int(notifiable), decided_by, _now(), rationale))
        self.conn.commit()

    def decision(self, case_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT * FROM decisions WHERE case_id = ? ORDER BY seq DESC",
                                (case_id,)).fetchone()
        return dict(row) if row else None

    # ---------------------------------------------------------------- case work

    def case(self, case_id: str) -> dict[str, Any] | None:
        return self.one("cases", "case_id", case_id)

    def append_timeline(self, case_id: str, event_time: str, summary: str,
                        evidence_ids: list[str], recorded_by: str,
                        injection_flagged: bool = False) -> dict[str, Any]:
        if not evidence_ids:
            raise StoreError("a timeline entry must cite at least one evidence ID")
        missing = [e for e in evidence_ids if self.evidence(e) is None]
        if missing:
            raise StoreError(f"unknown evidence IDs: {missing}")
        for e in self.timeline(case_id):
            if set(e["evidence_ids"]) == set(evidence_ids):
                raise StoreError(f"this evidence is already on the timeline as entry {e['seq']}; "
                                 "record a new fact or cite different evidence")
        last = self.conn.execute("SELECT entry_hash FROM timeline WHERE case_id = ? "
                                 "ORDER BY seq DESC LIMIT 1", (case_id,)).fetchone()
        prev = last["entry_hash"] if last else GENESIS
        recorded_at = _now()
        payload = {"case_id": case_id, "event_time": event_time, "summary": summary,
                   "evidence_ids": evidence_ids, "injection_flagged": bool(injection_flagged),
                   "recorded_at": recorded_at, "recorded_by": recorded_by}
        h = _entry_hash(prev, payload)
        self.conn.execute(
            "INSERT INTO timeline (case_id, event_time, summary, evidence_ids,"
            " injection_flagged, recorded_at, recorded_by, prev_hash, entry_hash)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (case_id, event_time, summary, json.dumps(evidence_ids), int(injection_flagged),
             recorded_at, recorded_by, prev, h))
        self.conn.commit()
        return {"entry_hash": h, "prev_hash": prev}

    def timeline(self, case_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT * FROM timeline WHERE case_id = ? ORDER BY seq",
                                 (case_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["evidence_ids"] = json.loads(d["evidence_ids"])
            out.append(d)
        return out

    def verify_timeline(self, case_id: str) -> bool:
        prev = GENESIS
        for e in self.timeline(case_id):
            payload = {"case_id": e["case_id"], "event_time": e["event_time"],
                       "summary": e["summary"], "evidence_ids": e["evidence_ids"],
                       "injection_flagged": bool(e["injection_flagged"]),
                       "recorded_at": e["recorded_at"], "recorded_by": e["recorded_by"]}
            if e["prev_hash"] != prev or _entry_hash(prev, payload) != e["entry_hash"]:
                return False
            prev = e["entry_hash"]
        return True

    def set_assessment(self, case_id: str, criterion: str, status: str,
                       evidence_ids: list[str], rationale: str, set_by: str) -> None:
        missing = [e for e in evidence_ids if self.evidence(e) is None]
        if missing:
            raise StoreError(f"unknown evidence IDs: {missing}")
        self.conn.execute(
            "INSERT INTO assessments (case_id, criterion, status, evidence_ids, rationale,"
            " set_at, set_by) VALUES (?,?,?,?,?,?,?)",
            (case_id, criterion, status, json.dumps(evidence_ids), rationale, _now(), set_by))
        self.conn.commit()

    def assessments(self, case_id: str) -> dict[str, dict[str, Any]]:
        """Latest assessment per criterion. Earlier ones stay in the table as history."""
        out: dict[str, dict[str, Any]] = {}
        for r in self.conn.execute("SELECT * FROM assessments WHERE case_id = ? ORDER BY seq",
                                   (case_id,)):
            d = dict(r)
            d["evidence_ids"] = json.loads(d["evidence_ids"])
            out[d["criterion"]] = d
        return out

    def save_draft(self, case_id: str, kind: str, body: str, validation: dict[str, Any],
                   created_by: str) -> str:
        draft_id = f"DRAFT-{uuid.uuid4().hex[:8].upper()}"
        self.conn.execute("INSERT INTO drafts VALUES (?,?,?,?,?,?,?)",
                          (draft_id, case_id, kind, body, json.dumps(validation), _now(),
                           created_by))
        self.conn.commit()
        return draft_id

    def draft(self, draft_id: str) -> dict[str, Any] | None:
        d = self.one("drafts", "draft_id", draft_id)
        if d:
            d["validation"] = json.loads(d["validation"])
        return d

    def queue_outbound(self, case_id: str, draft_id: str, kind: str) -> None:
        self.conn.execute("INSERT INTO outbox (case_id, draft_id, kind, queued_at)"
                          " VALUES (?,?,?,?)", (case_id, draft_id, kind, _now()))
        self.conn.commit()

    def outbox(self, case_id: str) -> list[dict[str, Any]]:
        return self.many("outbox", "case_id", case_id)

    def close(self) -> None:
        self.conn.close()
