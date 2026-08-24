"""預算填報:科目 × 月份明細表的讀取、儲存與送審。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import (
    accessible_department_ids,
    assert_department_access,
    get_current_user,
    require_admin,
)
from ..models import (
    Account,
    BudgetEntry,
    BudgetVersion,
    Department,
    Submission,
    SubmissionStatus,
    User,
    UserRole,
    VersionStatus,
)
from ..schemas import (
    DepartmentOut,
    GridResponse,
    GridRow,
    GridSaveRequest,
    GridSaveResult,
    SubmissionAction,
    SubmissionOut,
    VersionOut,
)
from ..services.tree import has_children_map, load_accounts, ordered_tree, rollup

router = APIRouter(prefix="/budget", tags=["預算填報"])

MONTHS = tuple(range(1, 13))


# --------------------------------------------------------------------------- #
# 內部工具
# --------------------------------------------------------------------------- #
def _get_version(db: Session, version_id: int) -> BudgetVersion:
    version = db.get(BudgetVersion, version_id)
    if version is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "預算版本不存在")
    return version


def _get_department(db: Session, department_id: int) -> Department:
    dept = db.get(Department, department_id)
    if dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "部門不存在")
    return dept


def _get_submission(db: Session, version_id: int, department_id: int) -> Submission | None:
    return db.scalar(
        select(Submission).where(
            Submission.version_id == version_id,
            Submission.department_id == department_id,
        )
    )


def _is_editable(user: User, version: BudgetVersion, submission: Submission | None) -> bool:
    """版本鎖定後全面唯讀;部門送出/核定後只有財務管理者能改。"""
    if version.status != VersionStatus.open:
        return False
    if user.role == UserRole.finance_admin:
        return True
    state = submission.status if submission else SubmissionStatus.draft
    return state in (SubmissionStatus.draft, SubmissionStatus.returned)


def _entry_map(db: Session, version_id: int, department_id: int) -> dict[int, dict[int, float]]:
    entries = db.scalars(
        select(BudgetEntry).where(
            BudgetEntry.version_id == version_id,
            BudgetEntry.department_id == department_id,
        )
    ).all()
    result: dict[int, dict[int, float]] = {}
    for entry in entries:
        if entry.month in MONTHS:
            result.setdefault(entry.account_id, {})[entry.month] = float(entry.amount or 0)
    return result


def _note_map(db: Session, version_id: int, department_id: int) -> dict[int, str]:
    entries = db.scalars(
        select(BudgetEntry).where(
            BudgetEntry.version_id == version_id,
            BudgetEntry.department_id == department_id,
            BudgetEntry.note.is_not(None),
        )
    ).all()
    notes: dict[int, str] = {}
    for entry in sorted(entries, key=lambda e: e.month):
        if entry.note and entry.account_id not in notes:
            notes[entry.account_id] = entry.note
    return notes


# --------------------------------------------------------------------------- #
# 表格讀取
# --------------------------------------------------------------------------- #
@router.get("/grid", response_model=GridResponse, summary="取得某部門某版本的預算明細表")
def get_grid(
    version_id: int,
    department_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GridResponse:
    version = _get_version(db, version_id)
    dept = _get_department(db, department_id)
    assert_department_access(db, user, department_id)

    accounts = load_accounts(db)
    child_flags = has_children_map(accounts)
    own = _entry_map(db, version_id, department_id)
    notes = _note_map(db, version_id, department_id)
    totals = rollup(accounts, own)

    rows: list[GridRow] = []
    month_totals = {m: 0.0 for m in MONTHS}
    category_totals: dict[str, float] = {}

    for account, level in ordered_tree(accounts):
        is_group = child_flags.get(account.id, False)
        source = totals.get(account.id, {}) if is_group else own.get(account.id, {})
        months = {m: round(float(source.get(m, 0.0)), 2) for m in MONTHS}
        row_total = round(sum(months.values()), 2)
        rows.append(
            GridRow(
                account_id=account.id,
                account_code=account.code,
                account_name=account.name,
                category=account.category,
                level=level,
                is_postable=account.is_postable and not is_group,
                months=months,
                total=row_total,
                note=notes.get(account.id),
            )
        )
        # 只累加可填報的葉節點,避免與群組小計重複計算
        if not is_group:
            for month in MONTHS:
                month_totals[month] = round(month_totals[month] + months[month], 2)
            key = account.category.value
            category_totals[key] = round(category_totals.get(key, 0.0) + row_total, 2)

    submission = _get_submission(db, version_id, department_id)
    dept_out = DepartmentOut.model_validate(dept)

    return GridResponse(
        version=VersionOut.model_validate(version),
        department=dept_out,
        editable=_is_editable(user, version, submission),
        submission_status=submission.status if submission else SubmissionStatus.draft,
        submission_comment=submission.comment if submission else None,
        rows=rows,
        month_totals=month_totals,
        grand_total=round(sum(month_totals.values()), 2),
        category_totals=category_totals,
    )


# --------------------------------------------------------------------------- #
# 表格儲存
# --------------------------------------------------------------------------- #
@router.put("/grid", response_model=GridSaveResult, summary="批次儲存變更的格子")
def save_grid(
    payload: GridSaveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GridSaveResult:
    version = _get_version(db, payload.version_id)
    _get_department(db, payload.department_id)
    assert_department_access(db, user, payload.department_id)

    submission = _get_submission(db, payload.version_id, payload.department_id)
    if not _is_editable(user, version, submission):
        raise HTTPException(status.HTTP_409_CONFLICT, "此版本或此部門目前不可編輯")

    postable_ids = {
        account.id
        for account in load_accounts(db)
        if account.is_postable
    }
    child_ids = {a.parent_id for a in load_accounts(db) if a.parent_id is not None}

    existing = {
        (entry.account_id, entry.month): entry
        for entry in db.scalars(
            select(BudgetEntry).where(
                BudgetEntry.version_id == payload.version_id,
                BudgetEntry.department_id == payload.department_id,
            )
        )
    }

    updated = deleted = 0
    now = datetime.now(timezone.utc)

    for cell in payload.cells:
        if cell.account_id not in postable_ids or cell.account_id in child_ids:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"科目 {cell.account_id} 不可直接填報金額")
        amount = round(cell.amount, 2)
        key = (cell.account_id, cell.month)
        entry = existing.get(key)

        if amount == 0:
            # 金額歸零就刪除,除非該格仍掛著備註
            if entry is not None:
                if entry.note:
                    entry.amount = 0
                    entry.updated_at = now
                    entry.updated_by = user.id
                    db.add(entry)
                    updated += 1
                else:
                    db.delete(entry)
                    existing.pop(key, None)
                    deleted += 1
            continue

        if entry is None:
            entry = BudgetEntry(
                version_id=payload.version_id,
                department_id=payload.department_id,
                account_id=cell.account_id,
                month=cell.month,
                amount=amount,
                updated_by=user.id,
            )
            existing[key] = entry
        else:
            entry.amount = amount
            entry.updated_at = now
            entry.updated_by = user.id
        db.add(entry)
        updated += 1

    # 備註寫在該科目該部門的所有月份格上;若整列沒有金額,補一格 1 月零金額來承載備註
    for account_id, note in payload.notes.items():
        row_entries = [e for (aid, _), e in existing.items() if aid == account_id]
        text = (note or "").strip() or None
        if not row_entries:
            if text is None:
                continue
            placeholder = BudgetEntry(
                version_id=payload.version_id,
                department_id=payload.department_id,
                account_id=account_id,
                month=1,
                amount=0,
                note=text,
                updated_by=user.id,
            )
            existing[(account_id, 1)] = placeholder
            db.add(placeholder)
            continue
        for entry in row_entries:
            entry.note = text
            db.add(entry)

    db.commit()

    grand = sum(
        float(e.amount or 0)
        for e in db.scalars(
            select(BudgetEntry).where(
                BudgetEntry.version_id == payload.version_id,
                BudgetEntry.department_id == payload.department_id,
            )
        )
    )
    return GridSaveResult(updated=updated, deleted=deleted, grand_total=round(grand, 2))


@router.post("/copy", response_model=GridSaveResult, summary="從其他版本複製某部門的預算")
def copy_from_version(
    version_id: int,
    department_id: int,
    source_version_id: int,
    ratio: float = Query(1.0, description="複製時的調整倍率,例如 1.05 表示加 5%"),
    overwrite: bool = Query(True, description="True 覆蓋既有金額,False 只補空白科目"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> GridSaveResult:
    version = _get_version(db, version_id)
    _get_version(db, source_version_id)
    assert_department_access(db, user, department_id)
    submission = _get_submission(db, version_id, department_id)
    if not _is_editable(user, version, submission):
        raise HTTPException(status.HTTP_409_CONFLICT, "此版本或此部門目前不可編輯")

    source = db.scalars(
        select(BudgetEntry).where(
            BudgetEntry.version_id == source_version_id,
            BudgetEntry.department_id == department_id,
        )
    ).all()
    existing = {
        (e.account_id, e.month): e
        for e in db.scalars(
            select(BudgetEntry).where(
                BudgetEntry.version_id == version_id,
                BudgetEntry.department_id == department_id,
            )
        )
    }

    updated = 0
    for entry in source:
        key = (entry.account_id, entry.month)
        target = existing.get(key)
        amount = round(float(entry.amount or 0) * ratio, 2)
        if target is None:
            db.add(
                BudgetEntry(
                    version_id=version_id,
                    department_id=department_id,
                    account_id=entry.account_id,
                    month=entry.month,
                    amount=amount,
                    note=entry.note,
                    updated_by=user.id,
                )
            )
            updated += 1
        elif overwrite:
            target.amount = amount
            db.add(target)
            updated += 1

    db.commit()
    grand = sum(
        float(e.amount or 0)
        for e in db.scalars(
            select(BudgetEntry).where(
                BudgetEntry.version_id == version_id,
                BudgetEntry.department_id == department_id,
            )
        )
    )
    return GridSaveResult(updated=updated, deleted=0, grand_total=round(grand, 2))


# --------------------------------------------------------------------------- #
# 填報狀態
# --------------------------------------------------------------------------- #
@router.get("/submissions", response_model=list[SubmissionOut], summary="各部門填報進度")
def list_submissions(
    version_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SubmissionOut]:
    _get_version(db, version_id)
    allowed = accessible_department_ids(db, user)

    departments = db.scalars(select(Department).where(Department.is_active.is_(True))).all()
    submissions = {
        s.department_id: s
        for s in db.scalars(select(Submission).where(Submission.version_id == version_id))
    }

    totals: dict[int, float] = {}
    for entry in db.scalars(select(BudgetEntry).where(BudgetEntry.version_id == version_id)):
        totals[entry.department_id] = totals.get(entry.department_id, 0.0) + float(entry.amount or 0)

    rows: list[SubmissionOut] = []
    for dept in sorted(departments, key=lambda d: (d.sort_order, d.code)):
        if allowed is not None and dept.id not in allowed:
            continue
        submission = submissions.get(dept.id)
        rows.append(
            SubmissionOut(
                id=submission.id if submission else None,
                version_id=version_id,
                department_id=dept.id,
                department_code=dept.code,
                department_name=dept.name,
                status=submission.status if submission else SubmissionStatus.draft,
                comment=submission.comment if submission else None,
                total=round(totals.get(dept.id, 0.0), 2),
                submitted_at=submission.submitted_at if submission else None,
                reviewed_at=submission.reviewed_at if submission else None,
            )
        )
    return rows


def _transition(
    db: Session,
    user: User,
    payload: SubmissionAction,
    new_status: SubmissionStatus,
) -> SubmissionOut:
    version = _get_version(db, payload.version_id)
    dept = _get_department(db, payload.department_id)
    if version.status != VersionStatus.open and user.role != UserRole.finance_admin:
        raise HTTPException(status.HTTP_409_CONFLICT, "版本未開放填報")

    submission = _get_submission(db, payload.version_id, payload.department_id)
    if submission is None:
        submission = Submission(version_id=payload.version_id, department_id=payload.department_id)

    now = datetime.now(timezone.utc)
    submission.status = new_status
    submission.comment = payload.comment
    if new_status == SubmissionStatus.submitted:
        submission.submitted_at = now
        submission.submitted_by = user.id
    else:
        submission.reviewed_at = now
        submission.reviewed_by = user.id

    db.add(submission)
    db.commit()
    db.refresh(submission)

    total = sum(
        float(e.amount or 0)
        for e in db.scalars(
            select(BudgetEntry).where(
                BudgetEntry.version_id == payload.version_id,
                BudgetEntry.department_id == payload.department_id,
            )
        )
    )
    return SubmissionOut(
        id=submission.id,
        version_id=submission.version_id,
        department_id=submission.department_id,
        department_code=dept.code,
        department_name=dept.name,
        status=submission.status,
        comment=submission.comment,
        total=round(total, 2),
        submitted_at=submission.submitted_at,
        reviewed_at=submission.reviewed_at,
    )


@router.post("/submit", response_model=SubmissionOut, summary="部門送出預算")
def submit(
    payload: SubmissionAction,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SubmissionOut:
    assert_department_access(db, user, payload.department_id)
    return _transition(db, user, payload, SubmissionStatus.submitted)


@router.post("/approve", response_model=SubmissionOut, summary="財務核定")
def approve(
    payload: SubmissionAction,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SubmissionOut:
    return _transition(db, user, payload, SubmissionStatus.approved)


@router.post("/return", response_model=SubmissionOut, summary="財務退回")
def send_back(
    payload: SubmissionAction,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> SubmissionOut:
    return _transition(db, user, payload, SubmissionStatus.returned)
