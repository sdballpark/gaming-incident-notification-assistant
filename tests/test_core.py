"""
Deterministic core: the clock, the corpus, the evidence store and the draft validator.
None of these involve a model, and each encodes something a model must never be
trusted to get right on its own.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from incident_assistant import clock
from incident_assistant.corpus import DEFAULT_CORPUS, Corpus, cite, parse_cites
from incident_assistant.drafts import validate_summary
from incident_assistant.session import load_scenario
from incident_assistant.store import Store, StoreError

UTC = timezone.utc
T0 = datetime(2026, 3, 14, 17, 15, tzinfo=UTC)


# ------------------------------------------------------------------ clock

def test_initial_notification_is_24_hours_after_activation():
    assert clock.compute(T0).initial_notification_due == T0 + timedelta(hours=24)


def test_initial_report_is_5_days_or_30_with_a_meeting():
    assert clock.compute(T0).initial_report_due == T0 + timedelta(days=5)
    assert clock.compute(T0, meeting_held=True).initial_report_due == T0 + timedelta(days=30)


def test_status_updates_every_30_days_from_initial_notification():
    sent = T0 + timedelta(hours=20)
    due = clock.status_updates(sent, sent + timedelta(days=95))
    assert due == [sent + timedelta(days=30 * n) for n in (1, 2, 3)]


def test_clock_refuses_naive_times():
    with pytest.raises(clock.ClockError):
        clock.compute(datetime(2026, 3, 14, 17, 15))


# ------------------------------------------------------------------ corpus

def test_corpus_has_no_deleted_text_and_no_72_hours():
    c = Corpus.load()
    text = " ".join(s.text for s in c.sections.values())
    assert "[" not in text and "]" not in text
    assert not re.search(r"\b72\b", text)


def test_corpus_4a_is_the_amended_rule():
    a = Corpus.load().resolve("4(a)").text
    assert "24 hours" in a and "activating the response procedures" in a


def test_corpus_records_its_source():
    src = json.loads(Path(DEFAULT_CORPUS).read_text())["source"]
    assert src["adopted"] == "2026-01-29" and len(src["pdf_sha256"]) == 64


def test_regulation_search_finds_the_notification_deadline():
    top = Corpus.load().search("how long to notify the chair after activating response", k=1)
    assert top[0]["id"] == "4(a)" and top[0]["cite"] == "[Reg 5.260(4)(a)]"


def test_cite_round_trip():
    assert parse_cites(cite("4(a)") + " " + cite("6")) == ["4(a)", "6"]


# ------------------------------------------------------------------ store

@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "t.db")
    s.load_scenario(load_scenario("s01-helpdesk-reset"))
    yield s
    s.close()


def _case(store):
    return store.open_case("s01", "2026-03-14T17:15:00+00:00", "m.okafor")


def test_timeline_requires_real_evidence(store):
    cid = _case(store)
    with pytest.raises(StoreError):
        store.append_timeline(cid, "2026-03-14T02:10:00+00:00", "x", [], "a")
    with pytest.raises(StoreError):
        store.append_timeline(cid, "2026-03-14T02:10:00+00:00", "x", ["SIG-9999"], "a")


def test_timeline_tampering_is_detected(store):
    cid = _case(store)
    store.append_timeline(cid, "2026-03-14T02:10:00+00:00", "reset", ["AUD-0001"], "a")
    store.append_timeline(cid, "2026-03-14T02:18:00+00:00", "sign-in", ["SIG-0003"], "a")
    assert store.verify_timeline(cid)
    store.conn.execute("UPDATE timeline SET summary = 'nothing happened' WHERE seq = 1")
    assert not store.verify_timeline(cid)


def test_decision_cannot_be_recorded_by_an_agent_identity(store):
    with pytest.raises(StoreError):
        store.record_decision(_case(store), True, "investigation_agent", "x")


# ------------------------------------------------------------------ draft validator

@pytest.fixture()
def case_with_timeline(store):
    cid = _case(store)
    store.append_timeline(cid, "2026-03-14T02:10:00+00:00", "reset", ["AUD-0001"], "a")
    return store, cid


def _errors(store, cid, text):
    return validate_summary(text, cid, store, Corpus.load()).errors


def test_valid_summary_passes(case_with_timeline):
    store, cid = case_with_timeline
    assert _errors(store, cid, "The help desk reset a password [AUD-0001].") == []


@pytest.mark.parametrize("text, expected", [
    ("The help desk reset a password.", "cites no evidence"),
    ("A sign-in followed [SIG-0003].", "not on the case timeline"),
    ("A record was read [SIG-9999].", "does not exist"),
    ("Notify within 72 hours [AUD-0001].", "time period"),
    ("Notice is due in 24 hours [AUD-0001].", "time period"),
    ("This incident is notifiable [AUD-0001].", "notifiable"),
    ("The reset is not reportable [AUD-0001].", "notifiable"),
    ("See the rule [AUD-0001] [Reg 5.260(9)(z)].", "does not resolve"),
])
def test_invalid_summaries_are_rejected(case_with_timeline, text, expected):
    store, cid = case_with_timeline
    assert any(expected in e for e in _errors(store, cid, text)), _errors(store, cid, text)
