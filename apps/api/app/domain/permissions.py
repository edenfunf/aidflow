"""Roles and permissions (開發設計規劃書 伍、權限角色功能對照).

民眾 never log in, so they have no role here — public endpoints are open.
Every government endpoint names the permission it needs; the mapping below is
the single source of truth for who holds it.
"""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    officer = "officer"  # 承辦審核人員
    supervisor = "supervisor"  # 業務主管
    admin = "admin"  # 系統管理者


ROLE_LABELS: dict[str, str] = {
    Role.officer.value: "承辦審核人員",
    Role.supervisor.value: "業務主管",
    Role.admin.value: "系統管理者",
}


class Perm(str, Enum):
    view_console = "view_console"  # 登入後台、總覽、案件與地圖（唯讀）
    review_cases = "review_cases"  # 審核分流、人工成案、EMIC 更新、處理紀錄、民間處理確認、排除通報
    view_pii = "view_pii"  # 檢視通報者聯絡資料（留存查閱紀錄）
    manage_platforms = "manage_platforms"  # 建立災害平台、成案規則、圖層與資料來源、示範資料
    manage_line = "manage_line"  # LINE 群組綁定
    manage_users = "manage_users"  # 帳號管理與角色指派
    view_audit = "view_audit"  # 稽核紀錄查詢（含登入與個資查閱）


ROLE_PERMS: dict[str, frozenset[Perm]] = {
    Role.officer.value: frozenset({Perm.view_console, Perm.review_cases, Perm.view_pii}),
    Role.supervisor.value: frozenset({Perm.view_console, Perm.view_pii, Perm.view_audit}),
    Role.admin.value: frozenset({Perm.view_console, Perm.manage_platforms, Perm.manage_line,
                                 Perm.manage_users, Perm.view_audit}),
}

ALL_PERMS: frozenset[Perm] = frozenset(Perm)


def perms_for(role: str | None) -> frozenset[Perm]:
    return ROLE_PERMS.get(role or "", frozenset())


def has_perm(role: str | None, perm: Perm) -> bool:
    return perm in perms_for(role)
