"""跨模組共用的可編輯性判斷:科目預算表、銷售量預算、資本支出編列都遵循同一套規則。"""

from __future__ import annotations

from ..models import Submission, SubmissionStatus, User, UserRole, VersionStatus


def is_editable(user: User, version_status: VersionStatus, submission: Submission | None) -> bool:
    """版本鎖定後全面唯讀;部門送出/核定後只有財務管理者能改。"""
    if version_status != VersionStatus.open:
        return False
    if user.role == UserRole.finance_admin:
        return True
    state = submission.status if submission else SubmissionStatus.draft
    return state in (SubmissionStatus.draft, SubmissionStatus.returned)
