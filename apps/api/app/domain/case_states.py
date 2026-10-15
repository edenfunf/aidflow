"""Incident case state machine.

Statuses are a closed enum and every transition is declared here, so the
console can only move a case along an allowed path and the public timeline is
always derived from real, validated transitions.

Flow agreed with 南投縣政府 (2026-09-03):

    民眾通報 → 同地點聚合 → pending_review（承辦審核點）
        ├─ 需上報   → reported_emic → emic_processing → closed
        ├─ 小型災情 → community_open → community_submitted → closed
        │                    ↑ 退回 ────────────┘
        └─ 誤報／重複 → dismissed

EMIC 欄位規格尚未提供：EMIC 側的細部狀態以 ``IncidentCase.emic_status``
（自 EMIC 同步或承辦登錄的文字）呈現，本系統只維護上述粗粒度流程。
"""
from __future__ import annotations

from enum import Enum


class CaseStatus(str, Enum):
    pending_review = "pending_review"  # 待承辦審核分流
    reported_emic = "reported_emic"  # 已上報 EMIC
    emic_processing = "emic_processing"  # EMIC 案件處理中
    community_open = "community_open"  # 開放民眾協助處理
    community_submitted = "community_submitted"  # 民眾已上傳處理完成照片，待承辦確認
    closed = "closed"  # 已結案（自公開地圖撤除）
    dismissed = "dismissed"  # 不成案（誤報／重複）


TRANSITIONS: dict[CaseStatus, frozenset[CaseStatus]] = {
    CaseStatus.pending_review: frozenset({CaseStatus.reported_emic, CaseStatus.community_open,
                                          CaseStatus.dismissed}),
    CaseStatus.reported_emic: frozenset({CaseStatus.emic_processing, CaseStatus.closed}),
    CaseStatus.emic_processing: frozenset({CaseStatus.closed}),
    CaseStatus.community_open: frozenset({CaseStatus.community_submitted, CaseStatus.reported_emic,
                                          CaseStatus.closed, CaseStatus.dismissed}),
    CaseStatus.community_submitted: frozenset({CaseStatus.closed, CaseStatus.community_open,
                                               CaseStatus.reported_emic}),
    CaseStatus.closed: frozenset(),
    CaseStatus.dismissed: frozenset(),
}

EMIC_STATUSES: frozenset[CaseStatus] = frozenset({CaseStatus.reported_emic, CaseStatus.emic_processing})
COMMUNITY_STATUSES: frozenset[CaseStatus] = frozenset({CaseStatus.community_open, CaseStatus.community_submitted})
OPEN_STATUSES: frozenset[CaseStatus] = frozenset(
    s for s in CaseStatus if s not in (CaseStatus.closed, CaseStatus.dismissed)
)
DONE_STATUSES: frozenset[CaseStatus] = frozenset({CaseStatus.closed})
PENDING_STATUSES: frozenset[CaseStatus] = frozenset({CaseStatus.pending_review})
# statuses the case queue shows once a reviewer has decided how to handle it
QUEUED_STATUSES: frozenset[CaseStatus] = EMIC_STATUSES | COMMUNITY_STATUSES

# what the public sees for each status
PUBLIC_LABELS: dict[CaseStatus, str] = {
    CaseStatus.pending_review: "審核中",
    CaseStatus.reported_emic: "已上報 EMIC",
    CaseStatus.emic_processing: "處理中",
    CaseStatus.community_open: "開放民眾協助",
    CaseStatus.community_submitted: "處理完成確認中",
    CaseStatus.closed: "已結案",
    CaseStatus.dismissed: "不成案",
}

# coarse public phase used for colour / filters
PUBLIC_PHASE: dict[CaseStatus, str] = {
    CaseStatus.pending_review: "pending",
    CaseStatus.reported_emic: "active",
    CaseStatus.emic_processing: "active",
    CaseStatus.community_open: "community",
    CaseStatus.community_submitted: "community",
    CaseStatus.closed: "done",
    CaseStatus.dismissed: "dismissed",
}
PHASES = ("pending", "active", "community", "done", "dismissed")

# the track a status belongs to (None = not yet decided)
TRACK_OF: dict[CaseStatus, str | None] = {
    CaseStatus.pending_review: None,
    CaseStatus.reported_emic: "emic",
    CaseStatus.emic_processing: "emic",
    CaseStatus.community_open: "community",
    CaseStatus.community_submitted: "community",
    CaseStatus.closed: None,
    CaseStatus.dismissed: None,
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
        return [s.value for s in CaseStatus if s in TRANSITIONS[CaseStatus(_val(frm))]]
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


def track_of(status: CaseStatus | str) -> str | None:
    try:
        return TRACK_OF[CaseStatus(_val(status))]
    except ValueError:
        return None


# ordered progress paths, one per track, for progress rendering
PROGRESS_PATHS: dict[str | None, tuple[CaseStatus, ...]] = {
    None: (CaseStatus.pending_review, CaseStatus.closed),
    "emic": (CaseStatus.pending_review, CaseStatus.reported_emic, CaseStatus.emic_processing, CaseStatus.closed),
    "community": (CaseStatus.pending_review, CaseStatus.community_open, CaseStatus.community_submitted,
                  CaseStatus.closed),
}
