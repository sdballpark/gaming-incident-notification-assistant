"""
Draft rendering and validation.

The initial notification is a fixed template. The agent writes one thing in it: the
summary paragraph. Everything else (deadlines, the trigger assessment, the timeline,
the decision line) is rendered from the store by code.

The summary is validated before a draft is saved, and a draft that fails is not
saved at all. The rules:

  1. every sentence cites at least one evidence ID, e.g. [SIG-0003]
  2. every cited evidence ID exists, and is on this case's timeline
  3. every regulation citation, e.g. [Reg 5.260(4)(a)], resolves to the corpus
  4. no deadline may be stated in the summary: hours and days come from the clock
  5. no statement that the incident is or is not notifiable: a person decides that
  6. the text "72 hours" never appears anywhere in the rendered draft

Unknown is never shown as no. A criterion that is unknown or unassessed renders as
"not yet determined".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from . import clock
from .corpus import Corpus, parse_cites
from .store import Store

CRITERIA = {
    "unauthorized_access": "Unauthorized access to an information system",
    "compromise": "Material loss of control or compromise",
    "unauthorized_disclosure": "Unauthorized disclosure of data or information",
    "gaming_operations_disrupted": "Gaming operations disrupted",
    "personal_information_involved": "Patron or employee personal information involved",
    "attacker_still_present": "Unauthorized party still present",
}
TRIGGER_ELEMENTS = ("unauthorized_access", "compromise", "unauthorized_disclosure")
STATUSES = ("supported", "not_supported", "unknown")
STATUS_TEXT = {
    "supported": "Evidence supports",
    "not_supported": "Evidence does not support",
    "unknown": "Not yet determined",
}

_EVIDENCE = re.compile(r"\[((?:SIG|PRC|NET|AUD)-\d{4})\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_DEADLINE = re.compile(r"\b\d+\s*(?:-\s*)?(?:hours?|hrs?|days?)\b", re.I)
_DECISION = re.compile(r"\b(?:is|are|not)\s+(?:not\s+)?(?:notifiable|reportable)\b|"
                       r"\bno\s+(?:notification|report)\s+(?:is\s+)?required\b", re.I)
_SEVENTY_TWO = re.compile(r"\b72\s*-?\s*hours?\b", re.I)

MAX_SUMMARY_CHARS = 1500


@dataclass
class Validation:
    valid: bool
    errors: list[str] = field(default_factory=list)
    evidence_cited: list[str] = field(default_factory=list)
    regulation_cited: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": self.errors,
                "evidence_cited": self.evidence_cited,
                "regulation_cited": self.regulation_cited}


def validate_summary(summary: str, case_id: str, store: Store, corpus: Corpus) -> Validation:
    errors: list[str] = []
    text = summary.strip()
    if not text:
        return Validation(False, ["summary is empty"])
    if len(text) > MAX_SUMMARY_CHARS:
        errors.append(f"summary longer than {MAX_SUMMARY_CHARS} characters")

    for i, sentence in enumerate(_SENTENCE.split(text), start=1):
        if not _EVIDENCE.search(sentence):
            errors.append(f"sentence {i} cites no evidence: {sentence[:80]!r}")

    cited = list(dict.fromkeys(_EVIDENCE.findall(text)))
    on_timeline = {e for entry in store.timeline(case_id) for e in entry["evidence_ids"]}
    for eid in cited:
        if store.evidence(eid) is None:
            errors.append(f"{eid} does not exist")
        elif eid not in on_timeline:
            errors.append(f"{eid} is not on the case timeline; record it there first")

    reg = list(dict.fromkeys(parse_cites(text)))
    for sid in reg:
        if corpus.resolve(sid) is None:
            errors.append(f"regulation citation {sid} does not resolve to the corpus")

    if _DEADLINE.search(text):
        errors.append("summary states a time period; deadlines come from the clock only")
    if _DECISION.search(text):
        errors.append("summary states whether the incident is notifiable; a person decides")

    return Validation(not errors, errors, cited, reg)


def render_initial_notification(case_id: str, summary: str, store: Store,
                                operator: str, now_iso: str | None = None) -> str:
    case = store.case(case_id)
    if case is None:
        raise ValueError(f"unknown case {case_id}")
    from datetime import datetime
    d = clock.compute(datetime.fromisoformat(case["activated_at"]),
                      meeting_held=bool(case["meeting_held"]))
    assessments = store.assessments(case_id)
    decision = store.decision(case_id)

    def line(criterion: str) -> str:
        a = assessments.get(criterion)
        status = a["status"] if a else "unknown"
        ev = " ".join(f"[{e}]" for e in a["evidence_ids"]) if a else ""
        label = STATUS_TEXT[status] + ("" if a else " (not yet assessed)")
        return f"- {CRITERIA[criterion]}: {label}" + (f" {ev}" if ev else "")

    if decision is None:
        decision_line = "PENDING. To be decided and recorded by a named person."
    else:
        verdict = "Notifiable" if decision["notifiable"] else "Not notifiable"
        decision_line = (f"{verdict}. Decided by {decision['decided_by']} at "
                         f"{decision['decided_at']}. {decision['rationale']}")

    timeline_lines = [
        f"- {e['event_time']}  {e['summary']} "
        + " ".join(f"[{x}]" for x in e["evidence_ids"])
        + ("  [flag: possible instructions in attacker-controlled data]"
           if e["injection_flagged"] else "")
        # Shown in event order for the reader. The stored timeline keeps recorded
        # order, which is the order the hash chain covers.
        for e in sorted(store.timeline(case_id), key=lambda x: x["event_time"])
    ]

    personal = assessments.get("personal_information_involved")
    pi_note = ("\nPatron or employee personal information appears to be involved. Any "
               "obligations under NRS 603A are a separate determination for counsel and "
               "are not drafted here.\n"
               if personal and personal["status"] == "supported" else "")

    body = f"""INITIAL CYBERSECURITY INCIDENT NOTIFICATION
To: Chair, Nevada Gaming Control Board [Reg 5.260(4)(a)]
DRAFT FOR HUMAN REVIEW. NOT SENT.

Operator: {operator}
Case: {case_id}
Incident response procedures activated: {d.activated_at.isoformat()} by {case['activated_by']}
Initial notification due no later than: {d.initial_notification_due.isoformat()} [Reg 5.260(4)(a)]
Initial incident response report due: {d.initial_report_due.isoformat()} [Reg 5.260(4)(b)]

SUMMARY
{summary.strip()}

REPORTING TRIGGER [Reg 5.260(4)]
{chr(10).join(line(c) for c in TRIGGER_ELEMENTS)}

QUESTIONS THE REGULATOR WILL ASK
{chr(10).join(line(c) for c in CRITERIA if c not in TRIGGER_ELEMENTS)}
{pi_note}
EVIDENCE TIMELINE
{chr(10).join(timeline_lines) if timeline_lines else "- (empty)"}

NOTIFIABILITY DECISION
{decision_line}
"""
    if _SEVENTY_TWO.search(body):
        raise ValueError("rendered draft contains a 72-hour reference")
    return body
