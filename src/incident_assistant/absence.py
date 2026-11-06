"""
Claims of absence need positive evidence.

"The attacker is gone" and "gaming operations were not affected" are the claims that
end an investigation early, and they are the easiest for a model to make on thin
evidence. In the first Nemotron run the model reported the unauthorized party as no
longer present when one of the two compromised accounts had never been contained.

So a not_supported assessment on these criteria is checked by code before it is
recorded, and refused if the evidence does not establish the absence. The refusal says
what is missing, and "unknown" is always accepted: not knowing is a legitimate answer,
an unsupported "no" is not.

  attacker_still_present = not_supported
      For every identity implicated in the case evidence, the assessment must cite a
      containment event for that identity, dated after its last recorded activity.

  gaming_operations_disrupted = not_supported
      The assessment must cite evidence from at least one gaming-critical host.

Implicated identities are found by matching known account names against every field
of the evidence on the case timeline and the evidence the assessment cites, including
command lines (an attacker using a service account's credentials shows up there). For
audit events only the target counts: the help-desk agent who performed a reset is not
thereby compromised.
"""
from __future__ import annotations

from typing import Any

from .store import Store

CONTAINMENT_ACTIONS = frozenset({
    "account_disabled", "credentials_rotated", "sessions_revoked", "account_locked",
})


class AbsenceNotEstablished(ValueError):
    pass


def _identities_in(row: dict[str, Any], known: set[str]) -> set[str]:
    if row["table"] == "audit_events":
        return {row["target"]} & known
    found = set()
    for key, value in row.items():
        if key in ("table", "evidence_id") or not isinstance(value, str):
            continue
        for name in known:
            if name in value:
                found.add(name)
    return found


def implicated_identities(store: Store, case_id: str, extra_ids: list[str]) -> dict[str, str]:
    """Identity -> timestamp of its latest activity in the case evidence."""
    known = {r["user"] for r in store.conn.execute("SELECT user FROM identities")}
    ids = {e for entry in store.timeline(case_id) for e in entry["evidence_ids"]} | set(extra_ids)
    last: dict[str, str] = {}
    for eid in ids:
        row = store.evidence(eid)
        if row is None:
            continue
        if row["table"] == "audit_events" and row["action"] in CONTAINMENT_ACTIONS:
            continue
        for ident in _identities_in(row, known):
            if row["ts"] > last.get(ident, ""):
                last[ident] = row["ts"]
    return last


def check(store: Store, case_id: str, criterion: str, status: str,
          evidence_ids: list[str]) -> None:
    if status != "not_supported":
        return
    if criterion == "attacker_still_present":
        _check_contained(store, case_id, evidence_ids)
    elif criterion == "gaming_operations_disrupted":
        _check_gaming_examined(store, evidence_ids)


def _check_contained(store: Store, case_id: str, evidence_ids: list[str]) -> None:
    implicated = implicated_identities(store, case_id, evidence_ids)
    if not implicated:
        raise AbsenceNotEstablished(
            "no identities are implicated by the evidence recorded so far, so absence "
            "cannot be established. Record the attacker's activity on the timeline first, "
            "or use status 'unknown'.")
    contained: dict[str, str] = {}
    for eid in evidence_ids:
        row = store.evidence(eid)
        if row and row["table"] == "audit_events" and row["action"] in CONTAINMENT_ACTIONS:
            contained[row["target"]] = max(contained.get(row["target"], ""), row["ts"])
    missing = sorted(i for i, ts in implicated.items()
                     if i not in contained or contained[i] < ts)
    if missing:
        raise AbsenceNotEstablished(
            "not_supported claims the unauthorized party is gone, which requires a cited "
            f"containment event for every implicated identity. No containment cited, or "
            f"containment before the last activity, for: {', '.join(missing)}. Use status "
            "'unknown' unless containment evidence exists.")


def _check_gaming_examined(store: Store, evidence_ids: list[str]) -> None:
    critical = {r["host"] for r in
                store.conn.execute("SELECT host FROM assets WHERE gaming_critical = 1")}
    for eid in evidence_ids:
        row = store.evidence(eid)
        if row is None:
            continue
        hosts = {row.get("host"), row.get("src_host"), row.get("dst")}
        if hosts & critical:
            return
    raise AbsenceNotEstablished(
        "not_supported claims gaming operations were not disrupted, which requires citing "
        "evidence from at least one gaming-critical host. Examine one, or use status "
        "'unknown'.")
