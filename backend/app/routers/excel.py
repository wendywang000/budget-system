"""Excel 匯入匯出:預算明細表、實際數。"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_department_access, get_current_user, require_admin
from ..models import (
    Account,
    Actual,
    BudgetEntry,
    BudgetVersion,
    Department,
    DeptKind,
    ExpenseFunction,
    User,
    VersionStatus,
)
from ..schemas import ImportResult
from ..services.tree import has_children_map, load_accounts, load_departments, ordered_tree

router = APIRouter(prefix="/excel", tags=["Excel 匯入匯出"])

MONTHS = tuple(range(1, 13))
MONTH_HEADERS = [f"{m}月" for m in MONTHS]
HEADER_FILL = PatternFill(start_color="FFDCE6F1", end_color="FFDCE6F1", fill_type="solid")
HEADER_FONT = Font(bold=True)

KIND_LABELS: dict[DeptKind, str] = {
    DeptKind.company: "公司",
    DeptKind.division: "事業處",
    DeptKind.department: "部門",
    DeptKind.cost_center: "成本中心",
    DeptKind.project: "專案",
}
KIND_LABELS_REVERSE = {v: k for k, v in KIND_LABELS.items()}

FUNCTION_LABELS: dict[ExpenseFunction, str] = {
    ExpenseFunction.sales: "銷",
    ExpenseFunction.admin: "管",
    ExpenseFunction.rd: "研",
    ExpenseFunction.manufacturing: "製",
}
FUNCTION_LABELS_REVERSE = {v: k for k, v in FUNCTION_LABELS.items()}


def _xlsx_response(wb: Workbook, filename: str) -> StreamingResponse:
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    # 檔名可能含中文,HTTP 標頭只能放 latin-1,因此同時提供 ASCII 後備與 RFC 5987 編碼版本
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "download.xlsx"
    disposition = f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quote(filename)}'
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": disposition},
    )


# --------------------------------------------------------------------------- #
# 部門 / 成本中心主檔:範本 / 匯出 / 匯入
# --------------------------------------------------------------------------- #
DEPARTMENT_HEADERS = ["*部門代號", "*部門名稱", "*類型", "上層部門代號", "主管", "功能別(銷/管/研/製)", "排序", "啟用(是/否)"]


def _department_workbook(departments: list[Department]) -> Workbook:
    by_id = {d.id: d for d in departments}
    wb = Workbook()
    ws = wb.active
    ws.title = "部門主檔"
    ws.append(DEPARTMENT_HEADERS)
    for col in range(1, len(DEPARTMENT_HEADERS) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    note_ws = wb.create_sheet("類型與功能別對照")
    note_ws.append(["類型代碼", "說明"])
    for label in KIND_LABELS.values():
        note_ws.append([label, ""])
    note_ws.append([])
    note_ws.append(["功能別代碼", "說明"])
    for label in FUNCTION_LABELS.values():
        note_ws.append([label, ""])

    for dept in sorted(departments, key=lambda d: (d.sort_order, d.code)):
        parent = by_id.get(dept.parent_id) if dept.parent_id else None
        ws.append(
            [
                dept.code,
                dept.name,
                KIND_LABELS[dept.kind],
                parent.code if parent else "",
                dept.manager or "",
                FUNCTION_LABELS.get(dept.function, "") if dept.function else "",
                dept.sort_order,
                "是" if dept.is_active else "否",
            ]
        )

    for idx in range(1, len(DEPARTMENT_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 16
    return wb


@router.get("/departments/template", summary="下載部門主檔匯入範本")
def download_department_template(_: User = Depends(require_admin)) -> StreamingResponse:
    return _xlsx_response(_department_workbook([]), "departments_template.xlsx")


@router.get("/departments/export", summary="匯出部門主檔")
def export_departments(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> StreamingResponse:
    departments = db.scalars(select(Department)).all()
    return _xlsx_response(_department_workbook(departments), "departments.xlsx")


@router.post("/departments/import", response_model=ImportResult, summary="匯入部門主檔(依部門代號覆蓋,可用上層部門代號建立組織樹)")
async def import_departments(
    file: UploadFile,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ImportResult:
    content = await file.read()
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"無法讀取 Excel 檔案:{exc}") from exc
    ws = wb.active

    result = ImportResult()
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    by_code = {d.code: d for d in db.scalars(select(Department))}

    # 第一輪:建立/更新每個部門(不設定上層,避免匯入順序影響),先確保所有代號都存在
    parent_codes: dict[str, str] = {}
    for idx, row in enumerate(rows, start=2):
        if not row or row[0] is None:
            continue
        code = str(row[0]).strip()
        name = str(row[1]).strip() if row[1] is not None else ""
        kind_label = str(row[2]).strip() if row[2] is not None else ""
        parent_code = str(row[3]).strip() if len(row) > 3 and row[3] not in (None, "") else ""
        manager = str(row[4]).strip() if len(row) > 4 and row[4] not in (None, "") else None
        function_label = str(row[5]).strip() if len(row) > 5 and row[5] not in (None, "") else ""
        sort_order = row[6] if len(row) > 6 and row[6] not in (None, "") else 0
        is_active_label = str(row[7]).strip() if len(row) > 7 and row[7] not in (None, "") else "是"

        if not code or not name:
            result.skipped += 1
            result.errors.append(f"第 {idx} 列:部門代號或名稱空白,已略過")
            continue
        kind = KIND_LABELS_REVERSE.get(kind_label)
        if kind is None:
            result.skipped += 1
            result.errors.append(f"第 {idx} 列:類型「{kind_label}」無法辨識,已略過")
            continue
        function = FUNCTION_LABELS_REVERSE.get(function_label) if function_label else None
        if function_label and function is None:
            result.errors.append(f"第 {idx} 列:功能別「{function_label}」無法辨識,已忽略此欄位")

        try:
            sort_order_int = int(sort_order)
        except (TypeError, ValueError):
            sort_order_int = 0

        dept = by_code.get(code)
        if dept is None:
            dept = Department(code=code, name=name, kind=kind)
            by_code[code] = dept
            result.inserted += 1
        else:
            result.updated += 1
        dept.name = name
        dept.kind = kind
        dept.manager = manager
        dept.function = function
        dept.sort_order = sort_order_int
        dept.is_active = is_active_label not in ("否", "false", "False", "0")
        dept.parent_id = None  # 上層部門於第二輪依代號設定;留白代表最上層,先重置避免沿用舊值
        db.add(dept)
        if parent_code:
            parent_codes[code] = parent_code

    db.flush()

    # 第二輪:所有代號都已存在,才能安全設定上層部門
    for code, parent_code in parent_codes.items():
        parent = by_code.get(parent_code)
        if parent is None:
            result.errors.append(f"部門 {code}:上層部門代號「{parent_code}」不存在,已忽略此欄位")
            continue
        by_code[code].parent_id = parent.id
        db.add(by_code[code])

    db.commit()
    return result


# --------------------------------------------------------------------------- #
# 匯出:單一部門預算明細
# --------------------------------------------------------------------------- #
@router.get("/budget/export", summary="匯出某部門某版本的預算明細")
def export_budget_grid(
    version_id: int,
    department_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    version = db.get(BudgetVersion, version_id)
    dept = db.get(Department, department_id)
    if version is None or dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "版本或部門不存在")
    assert_department_access(db, user, department_id)

    accounts = load_accounts(db)
    child_flags = has_children_map(accounts)
    entries = db.scalars(
        select(BudgetEntry).where(
            BudgetEntry.version_id == version_id,
            BudgetEntry.department_id == department_id,
        )
    ).all()
    amounts: dict[int, dict[int, float]] = {}
    for e in entries:
        amounts.setdefault(e.account_id, {})[e.month] = float(e.amount or 0)

    wb = Workbook()
    ws = wb.active
    ws.title = "預算明細"
    headers = ["科目代號", "科目名稱", "類別", *MONTH_HEADERS, "合計", "備註"]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    for account, level in ordered_tree(accounts):
        if child_flags.get(account.id, False):
            continue  # 只匯出可填報的葉科目,群組小計由使用者在表內以公式呈現
        months = amounts.get(account.id, {})
        row = [
            account.code,
            ("　" * level) + account.name,
            account.category.value,
            *[round(months.get(m, 0.0), 2) for m in MONTHS],
            round(sum(months.values()), 2),
        ]
        note = next((e.note for e in entries if e.account_id == account.id and e.note), None)
        row.append(note or "")
        ws.append(row)

    for idx, header in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = 12 if idx > 3 else 16

    filename = f"budget_{version.fiscal_year}_{version.name}_{dept.code}.xlsx"
    return _xlsx_response(wb, filename)


# --------------------------------------------------------------------------- #
# 匯入:單一部門預算明細
# --------------------------------------------------------------------------- #
@router.post("/budget/import", response_model=ImportResult, summary="匯入某部門某版本的預算明細")
async def import_budget_grid(
    version_id: int,
    department_id: int,
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ImportResult:
    version = db.get(BudgetVersion, version_id)
    dept = db.get(Department, department_id)
    if version is None or dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "版本或部門不存在")
    assert_department_access(db, user, department_id)
    if version.status != VersionStatus.open:
        raise HTTPException(status.HTTP_409_CONFLICT, "版本未開放填報,無法匯入")

    content = await file.read()
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"無法讀取 Excel 檔案:{exc}") from exc
    ws = wb.active

    accounts_by_code = {a.code: a for a in load_accounts(db)}
    existing = {
        (e.account_id, e.month): e
        for e in db.scalars(
            select(BudgetEntry).where(
                BudgetEntry.version_id == version_id,
                BudgetEntry.department_id == department_id,
            )
        )
    }

    result = ImportResult()
    now = datetime.now(timezone.utc)
    rows = list(ws.iter_rows(min_row=2, values_only=True))

    for idx, row in enumerate(rows, start=2):
        if not row or row[0] is None:
            continue
        code = str(row[0]).strip()
        account = accounts_by_code.get(code)
        if account is None:
            result.skipped += 1
            result.errors.append(f"第 {idx} 列:科目代號 {code} 不存在,已略過")
            continue
        if not account.is_postable:
            result.skipped += 1
            result.errors.append(f"第 {idx} 列:科目 {code} 為群組科目,不可填報,已略過")
            continue

        note_col = 3 + len(MONTHS) + 1  # 類別後接 12 個月 + 合計,備註在其後
        note = row[note_col] if len(row) > note_col else None

        for offset, month in enumerate(MONTHS):
            col_idx = 3 + offset
            if col_idx >= len(row):
                continue
            raw = row[col_idx]
            if raw is None or raw == "":
                continue
            try:
                amount = round(float(raw), 2)
            except (TypeError, ValueError):
                result.errors.append(f"第 {idx} 列:{month} 月金額格式錯誤,已略過該格")
                continue

            key = (account.id, month)
            entry = existing.get(key)
            if amount == 0 and entry is None:
                continue
            if entry is None:
                entry = BudgetEntry(
                    version_id=version_id,
                    department_id=department_id,
                    account_id=account.id,
                    month=month,
                    amount=amount,
                    updated_by=user.id,
                )
                existing[key] = entry
                result.inserted += 1
            else:
                entry.amount = amount
                entry.updated_at = now
                entry.updated_by = user.id
                result.updated += 1
            if note:
                entry.note = str(note)
            db.add(entry)

    db.commit()
    return result


# --------------------------------------------------------------------------- #
# 匯出範本(給部門填報用,含所有葉科目 × 12 個月)
# --------------------------------------------------------------------------- #
@router.get("/budget/template", summary="下載預算填報範本")
def download_template(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> StreamingResponse:
    accounts = load_accounts(db)
    child_flags = has_children_map(accounts)

    wb = Workbook()
    ws = wb.active
    ws.title = "預算範本"
    headers = ["科目代號", "科目名稱", "類別", *MONTH_HEADERS, "合計", "備註"]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    for account, level in ordered_tree(accounts):
        if child_flags.get(account.id, False):
            continue
        ws.append([account.code, ("　" * level) + account.name, account.category.value, *([0] * 12), 0, ""])

    for idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 12 if idx > 3 else 16

    return _xlsx_response(wb, "budget_template.xlsx")


# --------------------------------------------------------------------------- #
# 實際數:匯入 / 匯出(財務管理者)
# --------------------------------------------------------------------------- #
@router.get("/actuals/export", summary="匯出某年度實際數")
def export_actuals(
    fiscal_year: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    departments = {d.id: d for d in load_departments(db, active_only=False)}
    accounts = {a.id: a for a in load_accounts(db, active_only=False)}
    rows = db.scalars(select(Actual).where(Actual.fiscal_year == fiscal_year)).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "實際數"
    headers = ["部門代號", "部門名稱", "科目代號", "科目名稱", "月份", "金額"]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    for row in sorted(rows, key=lambda r: (r.department_id, r.account_id, r.month)):
        dept = departments.get(row.department_id)
        account = accounts.get(row.account_id)
        ws.append(
            [
                dept.code if dept else "",
                dept.name if dept else "",
                account.code if account else "",
                account.name if account else "",
                row.month,
                float(row.amount or 0),
            ]
        )

    for idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 16

    return _xlsx_response(wb, f"actuals_{fiscal_year}.xlsx")


@router.post("/actuals/import", response_model=ImportResult, summary="匯入某年度實際數(依部門代號+科目代號+月份覆蓋)")
async def import_actuals(
    fiscal_year: int,
    file: UploadFile,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ImportResult:
    content = await file.read()
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"無法讀取 Excel 檔案:{exc}") from exc
    ws = wb.active

    departments_by_code = {d.code: d for d in load_departments(db, active_only=False)}
    accounts_by_code = {a.code: a for a in load_accounts(db, active_only=False)}
    existing = {
        (r.department_id, r.account_id, r.month): r
        for r in db.scalars(select(Actual).where(Actual.fiscal_year == fiscal_year))
    }

    result = ImportResult()
    now = datetime.now(timezone.utc)

    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row or row[0] is None:
            continue
        dept_code, _dept_name, acc_code, _acc_name, month, amount = (row + (None,) * 6)[:6]
        dept = departments_by_code.get(str(dept_code).strip())
        account = accounts_by_code.get(str(acc_code).strip())
        if dept is None or account is None:
            result.skipped += 1
            result.errors.append(f"第 {idx} 列:部門或科目代號無法對應,已略過")
            continue
        try:
            month_int = int(month)
            amount_val = round(float(amount), 2)
        except (TypeError, ValueError):
            result.skipped += 1
            result.errors.append(f"第 {idx} 列:月份或金額格式錯誤,已略過")
            continue
        if not 1 <= month_int <= 12:
            result.skipped += 1
            result.errors.append(f"第 {idx} 列:月份 {month_int} 超出範圍,已略過")
            continue

        key = (dept.id, account.id, month_int)
        entry = existing.get(key)
        if entry is None:
            entry = Actual(
                fiscal_year=fiscal_year,
                department_id=dept.id,
                account_id=account.id,
                month=month_int,
                amount=amount_val,
            )
            existing[key] = entry
            result.inserted += 1
        else:
            entry.amount = amount_val
            entry.updated_at = now
            result.updated += 1
        db.add(entry)

    db.commit()
    return result
