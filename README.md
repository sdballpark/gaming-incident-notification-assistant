# Gaming Incident Notification Assistant

An assistant for Nevada casino operators facing the 24-hour cyber incident notification
deadline in Gaming Commission Regulation 5.260, as amended January 29, 2026.

It investigates incident telemetry, builds an evidence timeline, assesses each element
of the reporting trigger, and drafts the notification and follow-up reports with
citations. A named person decides whether to notify and approves anything sent. The
assistant can do neither.

**Status: design stage.** The architecture, threat model and evaluation plan are in
[DESIGN.md](DESIGN.md). Code arrives in phases listed in section 8 of that document;
this README will report measured results once Phase 2 runs.

---

## Why this exists

The 2026 amendment cut the initial notification window from 72 hours to 24, measured
from activation of the operator's incident response procedures. The responders who are
investigating are the same people who have to write the notice, from facts that are
still changing.

## The design in one table

| Part | Agentic or deterministic | Why |
|---|---|---|
| Investigation across telemetry | Agentic | The path depends on what each query returns |
| Deadline clock | Deterministic | Legal deadlines are computed, never estimated |
| Notifiability decision | Human | It carries legal weight for the operator |
| Sending to the regulator | Human approval | Privileged action behind the gateway |
| Regulation text | Retrieved with citations | The rule changed in 2026; model memory may hold the old one |

## Built on

[itops-mcp-gateway](https://github.com/sdballpark/itops-mcp-gateway), pinned to `v1.1.0`,
supplies the tool tiers, approval queue and audit. Authorization is reused, not
reimplemented.

## Data

Synthetic only. No real operator, system, network or patron data appears in this
repository.

## Not legal advice

This project does not decide whether an incident is reportable and has not been used
by an operator.

---

**Robert Bogan** · AI Security Architect · CISSP, CISM, CRISC ·
[LinkedIn](https://www.linkedin.com/in/robert-l-bogan-jr)

MIT licensed.
