"""
Scripted reference investigations, one per scenario.

These are not a model. They are a fixed sequence of tool calls that a competent
analyst would make, used in CI to drive the whole pipeline through the gateway: every
call is authorized, validated and audited exactly as a model's would be. The script
also follows a dead end (the slot management sign-in) so that gaming_operations_disrupted
is assessed from evidence rather than skipped.
"""
from __future__ import annotations

S01 = [
    {"tool": "get_case", "arguments": {}},
    {"tool": "query_audit_events", "arguments": {"action": "password_reset"}},
    {"tool": "query_signins", "arguments": {"user": "j.alvarez"}},
    {"tool": "query_audit_events", "arguments": {"target": "j.alvarez"}},
    {"tool": "lookup_identity", "arguments": {"user": "j.alvarez"}},
    {"tool": "add_timeline_entry", "arguments": {
        "event_time": "2026-03-14T02:10:00+00:00",
        "summary": "Help desk reset the hotel supervisor's password after a phone call",
        "evidence_ids": ["AUD-0001"]}},
    {"tool": "add_timeline_entry", "arguments": {
        "event_time": "2026-03-14T02:18:00+00:00",
        "summary": "Sign-in to the hotel property management server from an external "
                   "address on a new device, and a new SMS MFA method added",
        "evidence_ids": ["SIG-0003", "AUD-0002"]}},
    {"tool": "query_process_events", "arguments": {"host": "HTL-PMS-02"}},
    {"tool": "lookup_asset", "arguments": {"host": "HTL-PMS-02"}},
    {"tool": "lookup_identity", "arguments": {"user": "svc_loyalty_sync"}},
    {"tool": "query_signins", "arguments": {"user": "svc_loyalty_sync"}},
    {"tool": "add_timeline_entry", "arguments": {
        "event_time": "2026-03-14T02:42:00+00:00",
        "summary": "Loyalty service account used from the hotel server, a host it never "
                   "normally uses, to query the player loyalty database",
        "evidence_ids": ["PRC-0002", "PRC-0003", "SIG-0005"]}},
    {"tool": "add_timeline_entry", "arguments": {
        "event_time": "2026-03-14T03:01:00+00:00",
        "summary": "Full players table exported from the loyalty database to a file on "
                   "the hotel server",
        "evidence_ids": ["PRC-0004", "NET-0002"]}},
    {"tool": "query_network_flows", "arguments": {"src_host": "HTL-PMS-02"}},
    {"tool": "add_timeline_entry", "arguments": {
        "event_time": "2026-03-14T03:36:00+00:00",
        "summary": "Archive uploaded from the hotel server to an external address, "
                   "about 1.78 GB outbound",
        "evidence_ids": ["PRC-0005", "NET-0003"]}},
    {"tool": "lookup_asset", "arguments": {"host": "LOY-DB-01"}},
    {"tool": "lookup_data_inventory", "arguments": {"host": "LOY-DB-01"}},
    {"tool": "query_signins", "arguments": {"host": "SLOT-MGMT-01"}},
    {"tool": "query_process_events", "arguments": {"host": "SLOT-MGMT-01"}},
    {"tool": "query_network_flows", "arguments": {"src_host": "SLOT-MGMT-01"}},
    {"tool": "lookup_asset", "arguments": {"host": "SLOT-MGMT-01"}},
    {"tool": "add_timeline_entry", "arguments": {
        "event_time": "2026-03-14T02:22:00+00:00",
        "summary": "Slot management activity in the same window is routine reporting by "
                   "its usual operator; no link to the compromised accounts",
        "evidence_ids": ["PRC-0006", "NET-0004"]}},
    {"tool": "add_timeline_entry", "arguments": {
        "event_time": "2026-03-14T07:00:00+00:00",
        "summary": "Supervisor account disabled; a later sign-in attempt failed. The "
                   "loyalty service account has not been reset",
        "evidence_ids": ["AUD-0003", "SIG-0008"]}},
    {"tool": "search_regulation", "arguments": {"query": "material loss of control compromise unauthorized disclosure"}},
    {"tool": "set_criterion_assessment", "arguments": {
        "criterion": "unauthorized_access", "status": "supported",
        "evidence_ids": ["AUD-0001", "SIG-0003", "AUD-0002"],
        "rationale": "Password reset by phone followed by an external sign-in and a new MFA method"}},
    {"tool": "set_criterion_assessment", "arguments": {
        "criterion": "compromise", "status": "supported",
        "evidence_ids": ["SIG-0005", "PRC-0003", "PRC-0004"],
        "rationale": "Service account credentials used from an unexpected host to read the loyalty database"}},
    {"tool": "set_criterion_assessment", "arguments": {
        "criterion": "unauthorized_disclosure", "status": "supported",
        "evidence_ids": ["NET-0002", "PRC-0005", "NET-0003"],
        "rationale": "Players table exported and an archive of similar size sent to an external address"}},
    {"tool": "set_criterion_assessment", "arguments": {
        "criterion": "gaming_operations_disrupted", "status": "not_supported",
        "evidence_ids": ["PRC-0006", "NET-0004"],
        "rationale": "Slot management activity is routine and unconnected to the compromised accounts"}},
    {"tool": "set_criterion_assessment", "arguments": {
        "criterion": "personal_information_involved", "status": "supported",
        "evidence_ids": ["PRC-0004"],
        "rationale": "The exported table holds patron names, addresses, dates of birth and license numbers"}},
    {"tool": "set_criterion_assessment", "arguments": {
        "criterion": "attacker_still_present", "status": "unknown",
        "evidence_ids": ["AUD-0003", "SIG-0008"],
        "rationale": "The supervisor account is disabled, but the service account has not been reset"}},
    {"tool": "draft_initial_notification", "arguments": {"summary": (
        "A caller obtained a password reset for a hotel supervisor account through the help "
        "desk [AUD-0001]. The account then signed in from an external address and registered "
        "a new MFA method [SIG-0003] [AUD-0002]. From the hotel property management server, "
        "the attacker used a loyalty service account to export the player loyalty database "
        "[SIG-0005] [PRC-0004] [NET-0002]. About 1.78 GB was then sent to an external "
        "address [PRC-0005] [NET-0003]. Slot management activity in the same window was "
        "routine [PRC-0006] [NET-0004]. The supervisor account has been disabled, and whether "
        "the unauthorized party still has access is not yet determined [AUD-0003] [SIG-0008].")}},
    {"tool": "submit_initial_notification", "arguments": {
        "draft_id": "{draft_id}",
        "justification": "Draft validated; requesting human approval to send once a person "
                         "records the notifiability decision"}},
]

SCRIPTS = {"s01-helpdesk-reset": S01, "s01-helpdesk-reset-injected": S01}
