"""Incident case state machine.

Statuses are a closed enum and every transition is declared here, so the
console can only move a case along an allowed path and the public timeline is
always derived from real, validated transitions.
"""
from __future__ import annotations

from enum import Enum


class CaseStatus(str, Enum):
    reported = "reported"  # single-report case, not yet verified
    verifying = "verifying"  # operator is checking a single-report case
    threshold_reached = "threshold_reached"  # N unique reporters agreed
    awaiting_dispatch = "awaiting_dispatch"
    assigned = "assigned"
    en_route = "en_route"
    on_site = "on_site"
    processing = "processing"
    resolved = "resolved"
    closed = "closed"
    dismissed = "dismissed"  # judged not an incident (false / duplicate)


TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.reported: frozenset({CaseStatus.verifying, CaseStatus.threshold_reached,
                                    CaseStatus.awaiting_dispatch, CaseStatus.dismissed}),
    CaseStatus.verifying: frozenset({CaseStatus.threshold_reached, CaseStatus.awaiting_dispatch,
                                     CaseStatus.dismissed}),
    CaseStatus.threshold_reached: frozenset({CaseStatus.awaiting_dispatch, CaseStatus.dismissed}),
    CaseStatus.awaiting_dispatch: frozenset({CaseStatus.assigned, CaseStatus.dismissed}),
    CaseStatus.assigned: frozenset({CaseStatus.en_route, CaseStatus.on_site,
                                    CaseStatus.awaiting_dispatch}),
    CaseStatus.en_route: frozenset({CaseStatus.on_site, CaseStatus.awaiting_dispatch}),
    CaseStatus.on_site: frozenset({CaseStatus.processing, CaseStatus.resolved}),
    CaseStatus.processing: frozenset({CaseStatus.resolved, CaseStatus.on_site}),
    CaseStatus.resolved: frozenset({CaseStatus.closed, CaseStatus.processing}),
    CaseStatus.closed: frozenset(),
    CaseStatus.dismissed: frozenset(),
}

OPEN_STATUSES: frozenset[CaseStatus] = frozenset(
    s for s in CaseStatus if s not in (CaseStatus.closed, CaseStatus.dismissed)
)
ACTIVE_STATUSES: frozenset[CaseStatus] = frozenset(
    {CaseStatus.assigned, CaseStatus.en_route, CaseStatus.on_site, CaseStatus.processing}
)
DONE_STATUSES: frozenset[CaseStatus] = frozenset({CaseStatus.resolved, CaseStatus.closed})
PENDING_STATUSES: frozenset[CaseStatus] = frozenset(
    {CaseStatus.reported, CaseStatus.verifying, CaseStatus.threshold_reached,
     CaseStatus.awaiting_dispatch}
)

# what the public sees for each status (the internal vocabulary is richer)
PUBLIC_LABELS: dict[CaseStatus, str] = {
    CaseStatus.reported: "已通報",
    CaseStatus.verifying: "查證中",
    CaseStatus.threshold_reached: "已成案",
    CaseStatus.awaiting_dispatch: "待派工",
    CaseStatus.assigned: "已派員",
    CaseStatus.en_route: "前往中",
    CaseStatus.on_site: "人員抵達",
    CaseStatus.processing: "處理中",
    CaseStatus.resolved: "已完成",
    CaseStatus.closed: "已結案",
    CaseStatus.dismissed: "不成案",
}

# coarse public phase used for colour / filters
PUBLIC_PHASE: dict[CaseStatus, str] = {
    CaseStatus.reported: "pending",
    CaseStatus.verifying: "pending",
    CaseStatus.threshold_reached: "pending",
    CaseStatus.awaiting_dispatch: "pending",
    CaseStatus.assigned: "active",
    CaseStatus.en_route: "active",
    CaseStatus.on_site: "active",
    CaseStatus.processing: "active",
    CaseStatus.resolved: "done",
    CaseStatus.closed: "done",
    CaseStatus.dismissed: "dismissed",
}


class InvalidTransitionError(Exception):
    def __init__(self, frm: str, to: str) -> None:
        super().__init__(f"Cannot transition case from '{frm}' to '{to}'.")
        self.frm = frm
        self.to = to


def _val(s: CaseStatus | str) -> str:
    return s.value if isinstance(s, CaseStatus) else str(s)


def can_transition(frm: CaseStatus | str, to: CaseStatus | str) -> bool:
    try:
        f = CaseStatus(_val(frm))
        t = CaseStatus(_val(to))
    except ValueError:
        return False
    return t in TRANSITIONS[f]


def assert_transition(frm: CaseStatus | str, to: CaseStatus | str) -> None:
    if not can_transition(frm, to):
        raise InvalidTransitionError(_val(frm), _val(to))


def next_statuses(frm: CaseStatus | str) -> list[str]:
    try:
        return [s.value for s in TRANSITIONS[CaseStatus(_val(frm))]]
    except ValueError:
        return []


def phase_of(status: CaseStatus | str) -> str:
    try:
        return PUBLIC_PHASE[CaseStatus(_val(status))]
    except ValueError:
        return "pending"


def public_label(status: CaseStatus | str) -> str:
    try:
        return PUBLIC_LABELS[CaseStatus(_val(status))]
    except ValueError:
        return _val(status)


# ordered "happy path" for progress rendering
PROGRESS_PATH: tuple[CaseStatus, ...] = (
    CaseStatus.reported,
    CaseStatus.threshold_reached,
    CaseStatus.awaiting_dispatch,
    CaseStatus.assigned,
    CaseStatus.on_site,
    CaseStatus.processing,
    CaseStatus.resolved,
)
