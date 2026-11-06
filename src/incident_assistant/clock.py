"""
Deadline clock.

Every deadline is computed from one timestamp: when the operator activated its
incident response procedures, recorded by a person. No model estimates a deadline,
and the agent has no tool that can set or change the activation time.

Regulation 5.260 subsection 4, as amended January 29, 2026:

  (a) initial notification to the Chair: as soon as practicable, no later than
      24 hours after activating incident response procedures
  (b) Initial Cybersecurity Incident Response report: within 5 calendar days of
      activation, or 30 days if the operator requests and holds a meeting with the
      Chair inside those 5 days
  (c) written updates every 30 days "from the initial reporting" until resolved

Interpretation choices, stated so a reviewer can disagree with them:

  - "Within 5 calendar days" is computed as activation plus 5 x 24 hours. A reading
    that runs to the end of the fifth calendar day gives the operator more time;
    this one is never later than that reading, so it cannot cause a missed deadline.
  - "From the initial reporting" could mean the initial notification under 4(a) or
    the initial report under 4(b). Updates are scheduled from the initial
    notification, the earlier of the two, so the schedule can only be early, never
    late. Its send time is recorded by a person.

Times are timezone-aware. Naive datetimes are refused rather than guessed at.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

INITIAL_NOTIFICATION = timedelta(hours=24)
INITIAL_REPORT = timedelta(days=5)
INITIAL_REPORT_WITH_MEETING = timedelta(days=30)
STATUS_UPDATE_INTERVAL = timedelta(days=30)


class ClockError(ValueError):
    pass


def _aware(name: str, value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ClockError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True)
class Deadlines:
    activated_at: datetime
    initial_notification_due: datetime
    initial_report_due: datetime
    meeting_held: bool

    def remaining(self, now: datetime) -> timedelta:
        """Time left until the initial notification is due. Negative means late."""
        return self.initial_notification_due - _aware("now", now)

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "activated_at": self.activated_at.isoformat(),
            "initial_notification_due": self.initial_notification_due.isoformat(),
            "initial_report_due": self.initial_report_due.isoformat(),
            "meeting_held": self.meeting_held,
        }


def compute(activated_at: datetime, meeting_held: bool = False) -> Deadlines:
    """Deadlines under subsection 4(a) and 4(b)."""
    activated_at = _aware("activated_at", activated_at)
    report_window = INITIAL_REPORT_WITH_MEETING if meeting_held else INITIAL_REPORT
    return Deadlines(
        activated_at=activated_at,
        initial_notification_due=activated_at + INITIAL_NOTIFICATION,
        initial_report_due=activated_at + report_window,
        meeting_held=meeting_held,
    )


def status_updates(initial_notification_sent_at: datetime, until: datetime) -> list[datetime]:
    """Status update due dates under subsection 4(c), up to and including `until`."""
    start = _aware("initial_notification_sent_at", initial_notification_sent_at)
    until = _aware("until", until)
    if until < start:
        raise ClockError("until is before the initial notification was sent")
    out = []
    due = start + STATUS_UPDATE_INTERVAL
    while due <= until:
        out.append(due)
        due += STATUS_UPDATE_INTERVAL
    return out
