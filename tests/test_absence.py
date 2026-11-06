"""
Claims of absence need positive evidence.

The first test replays the first Nemotron run's miss: with the hotel-server activity on
the timeline, it claimed the unauthorized party was gone, citing only the disabling of
the supervisor account. The loyalty service account, whose credentials the attacker
used, was never contained.
"""
from __future__ import annotations

import pytest

from incident_assistant.agent import ScriptedModel, run
from incident_assistant.session import open_session
from incident_assistant.tools import AGENT_ROLE


@pytest.fixture()
def session(tmp_path):
    s = open_session("s01-helpdesk-reset", tmp_path)
    yield s
    s.close()


def call(session, tool, args):
    return session.gateway.call_tool(tool, args, "test", AGENT_ROLE)


def timeline(session, ts, ids, summary="fact"):
    r = call(session, "add_timeline_entry",
             {"event_time": ts, "summary": summary, "evidence_ids": ids})
    assert r["ok"], r


def assess(session, criterion, status, ids):
    return call(session, "set_criterion_assessment",
                {"criterion": criterion, "status": status, "evidence_ids": ids,
                 "rationale": "test"})


def test_replay_of_the_first_nemotron_miss_is_refused(session):
    for ts, ids in [("2026-03-14T02:42:00+00:00", ["PRC-0003"]),
                    ("2026-03-14T03:01:00+00:00", ["PRC-0004"]),
                    ("2026-03-14T03:36:00+00:00", ["PRC-0005"]),
                    ("2026-03-14T03:37:00+00:00", ["NET-0003"])]:
        timeline(session, ts, ids)
    r = assess(session, "attacker_still_present", "not_supported", ["AUD-0003"])
    assert r["error"] == "validation_failed"
    assert "svc_loyalty_sync" in r["reason"]
    assert "attacker_still_present" not in session.store.assessments(session.case_id)


def test_unknown_is_always_accepted(session):
    assert assess(session, "attacker_still_present", "unknown", [])["ok"]
    assert assess(session, "gaming_operations_disrupted", "unknown", [])["ok"]


def test_absence_with_nothing_implicated_is_refused(session):
    r = assess(session, "attacker_still_present", "not_supported", [])
    assert r["error"] == "validation_failed" and "no identities" in r["reason"]


def test_absence_is_accepted_when_every_identity_is_contained_after_its_activity(session):
    session.store.conn.execute(
        "INSERT INTO audit_events VALUES ('AUD-0099','2026-03-14T08:00:00+00:00',"
        "'m.okafor','credentials_rotated','svc_loyalty_sync','Rotated by the IR team')")
    timeline(session, "2026-03-14T02:42:00+00:00", ["PRC-0003"])
    r = assess(session, "attacker_still_present", "not_supported", ["AUD-0003", "AUD-0099"])
    assert r["ok"], r


def test_containment_before_the_last_activity_does_not_count(session):
    timeline(session, "2026-03-14T02:42:00+00:00", ["PRC-0003"])
    timeline(session, "2026-03-14T07:05:00+00:00", ["SIG-0008"])
    session.store.conn.execute(
        "INSERT INTO audit_events VALUES ('AUD-0098','2026-03-14T03:00:00+00:00',"
        "'m.okafor','credentials_rotated','svc_loyalty_sync','Rotated early')")
    r = assess(session, "attacker_still_present", "not_supported", ["AUD-0003", "AUD-0098"])
    assert r["error"] == "validation_failed"
    assert "j.alvarez" in r["reason"]


def test_help_desk_agent_is_not_implicated_by_performing_the_reset(session):
    timeline(session, "2026-03-14T02:10:00+00:00", ["AUD-0001"])
    r = assess(session, "attacker_still_present", "not_supported", ["AUD-0001"])
    assert "hd.kpatel" not in r["reason"]


def test_gaming_disruption_cannot_be_ruled_out_without_looking(session):
    r = assess(session, "gaming_operations_disrupted", "not_supported", ["PRC-0004"])
    assert r["error"] == "validation_failed" and "gaming-critical" in r["reason"]
    assert assess(session, "gaming_operations_disrupted", "not_supported", ["PRC-0006"])["ok"]


def test_duplicate_timeline_entry_is_refused(session):
    timeline(session, "2026-03-14T02:42:00+00:00", ["PRC-0003"])
    r = call(session, "add_timeline_entry", {"event_time": "2026-03-14T02:42:00+00:00",
                                             "summary": "again", "evidence_ids": ["PRC-0003"]})
    assert r["error"] == "validation_failed" and "already on the timeline" in r["reason"]


def test_progress_callback_sees_every_tool_call(session):
    from incident_assistant.scripted import SCRIPTS
    seen = []
    run(session.gateway, ScriptedModel(SCRIPTS["s01-helpdesk-reset"]), on_step=seen.append)
    assert len(seen) == len(SCRIPTS["s01-helpdesk-reset"])
