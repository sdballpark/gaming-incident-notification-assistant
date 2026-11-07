# Requirements

Version 1.0, 2026-11-07. Applies to the code at the commit that adds this file.

This document states what the Gaming Incident Notification Assistant must do, what it
must never do, and how each requirement is verified. Every requirement marked **Met**
names the code that implements it and the test that proves it. Requirements that are
not built yet say so and name the phase that delivers them.

Related documents: [ARCHITECTURE.md](ARCHITECTURE.md), [SECURITY.md](SECURITY.md),
[OPERATIONS.md](OPERATIONS.md), [BUILD_LOG.md](BUILD_LOG.md), and the design rationale in
[DESIGN.md](../DESIGN.md).

---

## 1. Purpose

A Nevada gaming licensee that experiences a cybersecurity incident must notify the
Chair of the Gaming Control Board no later than 24 hours after activating its incident
response procedures (Regulation 5.260, subsection 4(a), as amended January 29, 2026).
The people investigating the incident are the same people who must write that notice.

The assistant takes the evidence gathering and drafting off their hands. It never takes
the decisions.

## 2. Stakeholders

| Stakeholder | Interest |
|---|---|
| Incident lead | Starts the case, records when response procedures were activated, reviews the investigation |
| Decision authority | A named person who decides whether the incident is notifiable. In most operators this is the CISO, compliance officer or gaming counsel |
| Approver | A named person who approves the text that leaves the organization. May be the decision authority; the system records each act separately |
| Gaming Control Board | Receives the notice. Not a user of the system |
| Security engineering | Operates, extends and assures the system |
| Patrons and employees | Their personal information may be in scope of the incident; their interests are why NRS 603A is flagged |

## 3. Scope

**In scope:** investigation of incident telemetry through read-only tools, an evidence
timeline, assessment of the reporting trigger, the 24-hour initial notification draft,
the deadline clock for subsections 4(a), 4(b) and 4(c), and the human decision and
approval path.

**Out of scope:** containment and response actions, drafting NRS 603A breach notices,
the Group I obligations in subsection 5, and tracking investigations by outside parties
under subsection 4(f). These are either a different trust level or a determination for
counsel.

**Data:** synthetic only. No real operator, system, network or patron data is used in
this repository.

## 4. Status legend

| Status | Meaning |
|---|---|
| **Met** | Implemented and covered by an automated test that would fail if the requirement broke |
| **Partial** | Implemented in part; the gap is stated |
| **Planned** | Not built. The phase is from [DESIGN.md](../DESIGN.md) section 8 |
| **Measured** | A performance or quality attribute with recorded results but no pass threshold yet |

---

## 5. Regulatory requirements

Each traces to a subsection of the adopted text in
`src/incident_assistant/data/corpus/reg-5.260-2026-01-29.json`.

| ID | Requirement | Source | Status | Implementation | Verification |
|---|---|---|---|---|---|
| RR-1 | Compute the initial notification deadline as activation of response procedures plus 24 hours | 4(a) | Met | `clock.compute` | `test_initial_notification_is_24_hours_after_activation` |
| RR-2 | Compute the initial report deadline: 5 calendar days after activation, or 30 days if a meeting with the Chair is held within those 5 days | 4(b) | Met (arithmetic) | `clock.compute(meeting_held=...)`. Recording in a case that a meeting was held is Planned | `test_initial_report_is_5_days_or_30_with_a_meeting` |
| RR-3 | Draft the Initial Cybersecurity Incident Response report | 4(b) | Planned, Phase 3 | | |
| RR-4 | Schedule written updates every 30 days from the initial reporting until resolved | 4(c) | Met (schedule) | `clock.status_updates` | `test_status_updates_every_30_days_from_initial_notification` |
| RR-5 | Draft the 30-day status updates | 4(c) | Planned, Phase 3 | | |
| RR-6 | Assess the reporting trigger: material loss of control, compromise, unauthorized disclosure of data or information | 4 | Met | `drafts.TRIGGER_ELEMENTS`, `set_criterion_assessment` | `test_scripted_run_matches_ground_truth` |
| RR-7 | Support answers to Board requests for specific information from the evidence record | 4(d) | Partial | The timeline holds every recorded fact with its evidence; there is no request-response tool | |
| RR-8 | Outline the investigation report: root cause, extent, preventive actions | 4(e) | Planned, Phase 3 | | |
| RR-9 | Show the waiver or modification option while it can still be used; a request must be made before the relevant deadline | 4 (waiver paragraph) | Planned | | |
| RR-10 | Keep a written, tamper-evident record of procedures and results, retainable for at least five years | 6 | Partial | Append-only hash-chained timeline; gateway audit log. Retention, backup and immutable export are production steps | `test_timeline_tampering_is_detected`, `test_mid_chain_deletion_is_detected` |
| RR-11 | Cite the regulation text in force, never a paraphrase from model memory, and never the superseded 72-hour rule | Whole regulation | Met | `corpus.py`, `scripts/build_corpus.py`, draft check in `drafts.render_initial_notification` | `test_corpus_has_no_deleted_text_and_no_72_hours`, `test_corpus_4a_is_the_amended_rule`, CI corpus rebuild |
| RR-12 | Flag apparent involvement of patron or employee personal information for counsel, without drafting an NRS 603A notice | NRS 603A (adjacent law) | Met | `drafts.render_initial_notification` | `test_draft_flags_personal_information_for_counsel` |

## 6. Business requirements

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| BR-1 | Produce a reviewable initial notification draft well inside the 24-hour window | Measured | Nemotron 3.5 Lightning on an RTX 4090 laptop: 4 min 38 s and 3 min 29 s on scenario s01. One scenario, one run each ([BUILD_LOG.md](BUILD_LOG.md)) |
| BR-2 | Every decision with legal weight stays with a named person: the activation time, whether to notify, and whether to send | Met | See SR-2, FR-8 |
| BR-3 | Every factual statement in a draft traces to a recorded evidence item | Met | See FR-6 |
| BR-4 | Run without sending incident data outside the operator's environment | Met | Default model runtime is a local Ollama endpoint; see SR-8 |

## 7. Functional requirements

| ID | Requirement | Status | Implementation | Verification |
|---|---|---|---|---|
| FR-1 | A case opens with the activation time, which must carry a timezone offset, and the identity of the person who recorded it, plus the triggering alert and its first-indicator time | Met | `session.open_session`, `store.open_case`, `get_case` | `test_case_opens_with_its_triggering_alert`, `test_activation_time_must_carry_a_timezone` |
| FR-2 | The agent investigates sign-ins, process events, network flows, audit events and the asset, identity and data inventories through read-only tools, and can list the real host and account names | Met | `tools.py` READ tier | `test_inventory_lists_real_names` |
| FR-3 | Each timeline entry cites at least one existing evidence ID. The timeline is append-only and hash-chained, and an entry that repeats evidence already recorded is refused | Met | `store.append_timeline`, `store.verify_timeline` | `test_timeline_requires_real_evidence`, `test_timeline_tampering_is_detected`, `test_duplicate_timeline_entry_is_refused` |
| FR-4 | Six criteria are assessed as supported, not_supported or unknown, each with cited evidence and a rationale. Earlier assessments are kept as history | Met | `set_criterion_assessment`, `store.assessments` | `test_scripted_run_matches_ground_truth`, `test_assessment_history_is_kept`, `test_bad_arguments_are_rejected_before_any_handler` |
| FR-5 | A claim of absence needs positive evidence. "Unauthorized party still present: not_supported" needs a containment event, after its last activity, for every identity implicated in the case. "Gaming operations disrupted: not_supported" needs evidence from a gaming-critical host. Unknown is always accepted | Met | `absence.py` | Seven tests in `tests/test_absence.py`, including `test_replay_of_the_first_nemotron_miss_is_refused` |
| FR-6 | The initial notification is a fixed template rendered by code. The agent writes only the summary paragraph, which is rejected unless every sentence cites evidence already on the timeline, every regulation citation resolves, and it states neither a time period nor whether the incident is notifiable | Met | `drafts.validate_summary`, `drafts.render_initial_notification` | `test_valid_summary_passes`, eight cases in `test_invalid_summaries_are_rejected` |
| FR-7 | A criterion that is unknown or unassessed renders as "Not yet determined", never as a negative | Met | `drafts.STATUS_TEXT` | `test_draft_shows_unknown_as_not_yet_determined` |
| FR-8 | Sending requires two separate human acts: an approval of the send request, and a recorded decision that the incident is notifiable. A recorded "not notifiable" blocks the send even after approval. A send executes at most once | Met | `tools._submit`, gateway approval queue | `test_send_request_does_not_execute`, `test_approval_without_a_recorded_decision_does_not_send`, `test_not_notifiable_decision_blocks_the_send`, `test_decision_plus_approval_sends_exactly_once` |
| FR-9 | Telemetry text that reads as instructions is marked on the row, on the timeline entry that cites it, and in the draft | Met | `tools._rows`, `TELEMETRY_MARKERS` | `test_injected_twin_is_flagged_and_changes_nothing` |
| FR-10 | Regulation search returns sections with exact citations such as [Reg 5.260(4)(a)] | Met | `corpus.Corpus.search`, `corpus.cite` | `test_regulation_search_finds_the_notification_deadline`, `test_cite_round_trip` |
| FR-11 | Each run is scored against the scenario's ground truth: criteria, missed notifiable, evidence completeness, draft validity, timeline integrity, injection flags, and whether anything reached the outbox before the human steps | Met | `score.py` | `test_scripted_run_matches_ground_truth` |
| FR-12 | The model interface is replaceable. A scripted reference investigation runs without a GPU; a local model runs through Ollama | Met | `agent.Model`, `ScriptedModel`, `OllamaModel` | `test_ollama_adapter_parses_tool_calls_without_a_server` |
| FR-13 | A model that stops early without a valid draft is told so and continues, up to three times, and the count is recorded. A model server error is retried with a different seed and, if it persists, recorded as the run's result | Met | `agent.run`, `OllamaModel.respond` | `test_early_stop_is_nudged_then_fails_without_a_draft`, `test_model_server_error_is_retried_then_recorded_not_raised` |
| FR-14 | Each step of a run is visible as it happens | Met | `agent.run(on_step=...)`, CLI progress output | `test_progress_callback_sees_every_tool_call` |

## 8. Security requirements

| ID | Requirement | Status | Implementation | Verification |
|---|---|---|---|---|
| SR-1 | Authorization is enforced outside the model on every tool call, by role and tier. An unknown role is denied | Met | itops-mcp-gateway `Policy`, `tools.build_policy` | `test_reviewer_role_cannot_write`, `test_unknown_role_is_denied` |
| SR-2 | The agent can never set the activation time, record the notifiability decision, edit or delete evidence, or contain a host. These actions are not offered to the agent, and naming one is denied and audited | Met | `tools.NEVER_EXPOSED` | `test_never_exposed_actions_are_denied_and_audited` (5 cases), `test_agent_is_not_told_the_never_exposed_actions_exist` |
| SR-3 | Arguments are validated before any handler runs: names, timestamps, evidence ID formats and counts, enumerations, lengths | Met | `tools.validate_arguments` | `test_bad_arguments_are_rejected_before_any_handler`, `test_oversized_and_malformed_arguments_are_rejected` (6 cases) |
| SR-4 | Approvals and decisions are made by people, never by an agent identity | Partial | The gateway refuses approver identities ending in `_agent`, and the store refuses such identities for decisions. People are not authenticated in this build; see SR-10 | `test_agent_identity_cannot_approve`, `test_decision_cannot_be_recorded_by_an_agent_identity` |
| SR-5 | Every tool call, including denials, is audited with sensitive values redacted | Met | itops-mcp-gateway audit log | `test_never_exposed_actions_are_denied_and_audited`, `test_audit_redacts_secrets_in_arguments` |
| SR-6 | The evidence record is tamper-evident: an edited entry or a deleted entry before the newest is detected. Deleting the newest entries, or rewriting the whole chain, needs an external anchor (SR-10) | Met | SHA-256 hash chain in `store.py` | `test_timeline_tampering_is_detected`, `test_mid_chain_deletion_is_detected` |
| SR-7 | Telemetry is handled as data, never as instructions, and no tool available to the agent can act on a successful injection | Met | Data notice on every tool result, row flags, the tool surface itself | `test_injected_twin_is_flagged_and_changes_nothing` |
| SR-8 | Incident data does not leave the operator's environment by default | Met | Local Ollama endpoint; no other network calls at run time | Code review; no hosted model adapter exists |
| SR-9 | The authorization dependency is pinned to a tagged release | Met | `pyproject.toml` pins itops-mcp-gateway `v1.2.0` | CI installs the pin |
| SR-10 | Human actors are authenticated, approvals require an approver credential distinct from the requester, approval state survives a restart, data is encrypted at rest, and the audit trail is exported to immutable storage | Planned | Production deployment | |

## 9. Non-functional requirements

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| NFR-1 | Reproducible runs: temperature 0, fixed seeds, a corpus that rebuilds byte for byte from the official text | Met | CI step "Corpus rebuilds identically from the official text" |
| NFR-2 | CI proves the controls without a GPU, on pushes to main and on pull requests | Met | `.github/workflows/ci.yml`: tests plus the clean scenario and its injected twin end to end with the scripted investigation |
| NFR-3 | Evaluation is honest: run files are committed before the write-up, failures are recorded, and limits are stated | Met (process) | `results/2026-11-06/`, [BUILD_LOG.md](BUILD_LOG.md) |
| NFR-4 | Runs on one workstation with Python 3.11 or later and SQLite | Met | `pyproject.toml` |
| NFR-5 | Model runs complete in minutes, not hours, on a single consumer GPU | Measured | Two timed Nemotron runs on an RTX 4090 laptop GPU (16 GB): 3 min 29 s and 4 min 38 s |
| NFR-6 | Accuracy targets per criterion and a zero missed-notifiable rate across a scenario corpus | Planned, Phase 2 | One scenario so far; rates need the corpus |

## 10. Constraints and assumptions

- The Board's Initial Cybersecurity Incident Response form is obtained by operators from the Board and is not reproduced here. The 24-hour notice uses a plain template.
- "Within 5 calendar days" is computed as activation plus 120 hours, which is never later than a reading that runs to the end of the fifth day. "From the initial reporting" is read as the initial notification, the earlier of the two possible events. Both readings are stated in `clock.py` for counsel to confirm.
- The system does not determine reportability and is not legal advice.
- Results so far cover one scenario and one run per model configuration. They show where models fail, not how often.

## 11. Change log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-11-07 | First version, traced to code and tests at Phase 1 plus the absence check |
