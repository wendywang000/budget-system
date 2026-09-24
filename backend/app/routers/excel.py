"""Excel 匯入匯出:預算明細表、實際數。"""

from __future__ import annotations

import io
import re
from datetime import date, datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import assert_department_access, get_current_user, require_admin
from ..models import (
    Account,
    AccountCategory,
    AccountCategoryOption,
    Actual,
    AssetCategory,
    BudgetEntry,
    BudgetVersion,
    Department,
    DeptKind,
    ExpenseFormatAccountMap,
    ExpenseFunction,
    Product,
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
# 預算單位(部門 / 成本中心)主檔:範本 / 匯出 / 匯入
# 欄位設計沿用既有系統格式:代碼、繁/簡/英名稱、上層單位代碼、單位種類代碼(G管/M製/R研/S銷)。
# --------------------------------------------------------------------------- #
DEPARTMENT_HEADERS = [
    "*預算單位代碼",
    "*預算單位名稱(繁體中文)",
    "預算單位名稱(簡體中文)",
    "預算單位名稱(英文)",
    "上層預算單位代碼",
    "*單位種類代碼",
    "負責人",
    "生效日期",
]

UNIT_KIND_CODE_TO_FUNCTION: dict[str, ExpenseFunction] = {
    "G": ExpenseFunction.admin,
    "M": ExpenseFunction.manufacturing,
    "R": ExpenseFunction.rd,
    "S": ExpenseFunction.sales,
}
FUNCTION_TO_UNIT_KIND_CODE = {v: k for k, v in UNIT_KIND_CODE_TO_FUNCTION.items()}
UNIT_KIND_CODE_LABELS = {"G": "管理", "M": "製造", "R": "研發", "S": "銷售"}


def _department_workbook(departments: list[Department]) -> Workbook:
    by_id = {d.id: d for d in departments}
    wb = Workbook()
    ws = wb.active
    ws.title = "預算單位主檔"
    ws.append(DEPARTMENT_HEADERS)
    for col in range(1, len(DEPARTMENT_HEADERS) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    note_ws = wb.create_sheet("單位種類代碼對照")
    note_ws.append(["代碼", "說明"])
    for code, label in UNIT_KIND_CODE_LABELS.items():
        note_ws.append([code, label])

    for dept in sorted(departments, key=lambda d: (d.sort_order, d.code)):
        parent = by_id.get(dept.parent_id) if dept.parent_id else None
        ws.append(
            [
                dept.code,
                dept.name,
                dept.name_zh_hans or "",
                dept.name_en or "",
                parent.code if parent else "",
                FUNCTION_TO_UNIT_KIND_CODE.get(dept.function, "") if dept.function else "",
                dept.manager or "",
                dept.effective_date.isoformat() if dept.effective_date else "",
            ]
        )

    for idx in range(1, len(DEPARTMENT_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 20
    return wb


@router.get("/departments/template", summary="下載預算單位主檔匯入範本")
def download_department_template(_: User = Depends(require_admin)) -> StreamingResponse:
    return _xlsx_response(_department_workbook([]), "departments_template.xlsx")


@router.get("/departments/export", summary="匯出預算單位主檔")
def export_departments(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> StreamingResponse:
    departments = db.scalars(select(Department)).all()
    return _xlsx_response(_department_workbook(departments), "departments.xlsx")


#  匯入時依「表頭文字」找欄位,而非固定欄位順序,同時支援兩種來源格式:
#  1. 本系統範本(*預算單位代碼 / 上層預算單位代碼 / *單位種類代碼 是 G/M/R/S 代碼)
#  2. 公司現有成本中心表(部門=上層單位的「名稱」而非代碼、成本中心代号/名稱、負責人、生效日期…)
CODE_HEADER_ALIASES = ("*預算單位代碼", "預算單位代碼", "成本中心代号", "成本中心代碼", "*成本中心代号")
NAME_HEADER_ALIASES = ("*預算單位名稱(繁體中文)", "預算單位名稱(繁體中文)", "成本中心名稱", "*成本中心名稱")
NAME_HANS_HEADER_ALIASES = ("預算單位名稱(簡體中文)",)
NAME_EN_HEADER_ALIASES = ("預算單位名稱(英文)",)
PARENT_CODE_HEADER_ALIASES = ("上層預算單位代碼", "上層單位代碼")
PARENT_NAME_HEADER_ALIASES = ("部門",)
FUNCTION_HEADER_ALIASES = ("*單位種類代碼", "單位種類代碼")
MANAGER_HEADER_ALIASES = ("負責人", "主管")
EFFECTIVE_DATE_HEADER_ALIASES = ("生效日期", "生效/建立日期", "建立日期", "生效年月日")


def _find_column(headers: list[str], aliases: tuple[str, ...]) -> int | None:
    for idx, header in enumerate(headers):
        if header and header.strip() in aliases:
            return idx
    return None


def _extract_date(value) -> date | None:  # noqa: ANN001
    """儲存格可能是真正的日期,也可能是夾雜其他文字的備註(如「須…起(2024/2/1生效)」),兩種都嘗試解析。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    match = re.search(r"(\d{4})[/\-年](\d{1,2})[/\-月](\d{1,2})", str(value))
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


@router.post(
    "/departments/import",
    response_model=ImportResult,
    summary="匯入部門/成本中心主檔(依表頭自動辨識欄位,可用上層代碼或上層部門名稱建立組織樹)",
)
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
    header_row = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    col_code = _find_column(header_row, CODE_HEADER_ALIASES)
    col_name = _find_column(header_row, NAME_HEADER_ALIASES)
    if col_code is None or col_name is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "找不到「代碼」或「名稱」欄位,請確認表頭文字與範本一致")
    col_name_hans = _find_column(header_row, NAME_HANS_HEADER_ALIASES)
    col_name_en = _find_column(header_row, NAME_EN_HEADER_ALIASES)
    col_parent_code = _find_column(header_row, PARENT_CODE_HEADER_ALIASES)
    col_parent_name = _find_column(header_row, PARENT_NAME_HEADER_ALIASES)
    col_function = _find_column(header_row, FUNCTION_HEADER_ALIASES)
    col_manager = _find_column(header_row, MANAGER_HEADER_ALIASES)
    col_effective_date = _find_column(header_row, EFFECTIVE_DATE_HEADER_ALIASES)

    def raw_cell(row: tuple, col: int | None):  # noqa: ANN202
        if col is None or col >= len(row) or row[col] in (None, ""):
            return None
        return row[col]

    def cell(row: tuple, col: int | None) -> str | None:
        value = raw_cell(row, col)
        return str(value).strip() if value is not None else None

    rows = list(ws.iter_rows(min_row=2, values_only=True))
    by_code = {d.code: d for d in db.scalars(select(Department))}
    by_name: dict[str, Department] = {}
    for d in by_code.values():
        by_name.setdefault(d.name, d)

    # 第 0 輪:「部門」欄若填的是名稱而非代碼,先依名稱找到或建立對應的上層節點
    def get_or_create_parent_by_name(name: str) -> Department:
        existing = by_name.get(name)
        if existing is not None:
            return existing
        code = f"GRP-{name}"
        suffix = 2
        while code in by_code:
            code = f"GRP-{name}-{suffix}"
            suffix += 1
        group = Department(code=code, name=name, kind=DeptKind.division)
        db.add(group)
        db.flush()
        by_code[code] = group
        by_name[name] = group
        result.inserted += 1
        return group

    # 第一輪:建立/更新每個部門/成本中心(不設定上層,避免匯入順序影響),先確保所有代碼都存在
    parent_codes: dict[str, str] = {}
    for idx, row in enumerate(rows, start=2):
        if not row or all(v is None for v in row):
            continue
        code = cell(row, col_code)
        name = cell(row, col_name)
        if not code or not name:
            result.skipped += 1
            result.errors.append(f"第 {idx} 列:代碼或名稱空白,已略過")
            continue

        unit_kind_code = (cell(row, col_function) or "").upper()
        function = UNIT_KIND_CODE_TO_FUNCTION.get(unit_kind_code)
        if unit_kind_code and function is None:
            result.errors.append(f"第 {idx} 列:單位種類代碼「{unit_kind_code}」無法辨識(應為 G/M/R/S),已忽略此欄位")

        dept = by_code.get(code)
        if dept is None:
            # 匯入格式沒有攜帶「類型」欄位,新建的部門/成本中心一律先歸類為成本中心,
            # 若需要公司/事業處層級,請在畫面上手動調整類型。
            dept = Department(code=code, name=name, kind=DeptKind.cost_center)
            by_code[code] = dept
            result.inserted += 1
        else:
            result.updated += 1
        dept.name = name
        dept.name_zh_hans = cell(row, col_name_hans)
        dept.name_en = cell(row, col_name_en)
        dept.manager = cell(row, col_manager)
        dept.function = function
        dept.effective_date = _extract_date(raw_cell(row, col_effective_date))
        dept.parent_id = None  # 上層單位於後續依代碼/名稱設定;留白代表最上層,先重置避免沿用舊值
        db.add(dept)
        by_name.setdefault(name, dept)

        parent_code = cell(row, col_parent_code)
        parent_name = cell(row, col_parent_name)
        if parent_code:
            parent_codes[code] = parent_code
        elif parent_name and parent_name != name:
            parent_group = get_or_create_parent_by_name(parent_name)
            dept.parent_id = parent_group.id
            db.add(dept)

    db.flush()

    # 第二輪:所有代碼都已存在,才能安全依「上層單位代碼」設定上層(部門名稱那一種已在第一輪處理)
    for code, parent_code in parent_codes.items():
        parent = by_code.get(parent_code)
        if parent is None:
            result.errors.append(f"部門 {code}:上層單位代碼「{parent_code}」不存在,已忽略此欄位")
            continue
        by_code[code].parent_id = parent.id
        db.add(by_code[code])

    db.commit()
    return result


# --------------------------------------------------------------------------- #
# 會計科目主檔:範本 / 匯出 / 匯入
# --------------------------------------------------------------------------- #
ACCOUNT_HEADERS = [
    "*會計科目代碼",
    "*會計科目名稱",
    "會計科目名稱(簡體中文)",
    "會計科目名稱(英文)",
    "會計科目類別",
    "起始年月",
    "結束年月",
]

CATEGORY_CODE_TO_ENUM: dict[str, AccountCategory] = {
    "R": AccountCategory.revenue,
    "C": AccountCategory.cost,
    "E": AccountCategory.expense,
    "K": AccountCategory.capex,
    "revenue": AccountCategory.revenue,
    "cost": AccountCategory.cost,
    "expense": AccountCategory.expense,
    "capex": AccountCategory.capex,
    "收入": AccountCategory.revenue,
    "營業收入": AccountCategory.revenue,
    "成本": AccountCategory.cost,
    "營業成本": AccountCategory.cost,
    "費用": AccountCategory.expense,
    "營業費用": AccountCategory.expense,
    "資本支出": AccountCategory.capex,
}

CATEGORY_ENUM_TO_CODE = {v: k for k, v in CATEGORY_CODE_TO_ENUM.items() if isinstance(k, str) and len(k) == 1}
ACCOUNT_CODE_HEADER_ALIASES = (
    "*會計科目代碼",
    "會計科目代碼",
    "*科目代碼",
    "科目代號",
    "會計科目代號",
    "會計科目代碼",
    "*會計科目代號",
    "代碼",
)
ACCOUNT_NAME_HEADER_ALIASES = (
    "*會計科目名稱",
    "會計科目名稱(繁體中文)",
    "會計科目名稱",
    "*科目名稱",
    "科目名稱(繁體中文)",
    "會計科目名稱(繁體)",
    "會計科目名稱(繁中)",
    "名稱",
)
ACCOUNT_NAME_HANS_HEADER_ALIASES = ("會計科目名稱(簡體中文)", "會計科目名稱(簡中)", "簡體中文名稱")
ACCOUNT_NAME_EN_HEADER_ALIASES = ("會計科目名稱(英文)", "英文名稱")
ACCOUNT_CATEGORY_HEADER_ALIASES = ("會計科目類別", "*類別", "科目類別", "類別", "科目類型")
ACCOUNT_PARENT_CODE_HEADER_ALIASES = ("上層科目代碼", "上層代碼", "父科目代碼")
ACCOUNT_PARENT_NAME_HEADER_ALIASES = ("上層科目名稱", "上層名稱", "父科目名稱", "父科目")
ACCOUNT_POSTABLE_HEADER_ALIASES = ("可直接填報", "是否可填報", "葉科目", "是否可直接填報")
ACCOUNT_SORT_HEADER_ALIASES = ("排序", "顯示順序")
ACCOUNT_ACTIVE_HEADER_ALIASES = ("啟用", "是否啟用", "使用中")
ACCOUNT_NOTE_HEADER_ALIASES = ("備註", "說明")
ACCOUNT_START_DATE_HEADER_ALIASES = ("起始年月", "起始日期", "生效年月")
ACCOUNT_END_DATE_HEADER_ALIASES = ("結束年月", "結束日期", "失效年月")


def _header_matches(header: str, aliases: tuple[str, ...]) -> bool:
    normalized = (header or "").strip()
    if not normalized:
        return False
    for alias in aliases:
        if normalized == alias:
            return True
        if alias in normalized or normalized in alias:
            return True
    return False


def _account_workbook(accounts: list[Account]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "會計科目主檔"
    ws.append(ACCOUNT_HEADERS)
    for col in range(1, len(ACCOUNT_HEADERS) + 1):
        cell = ws.cell(row=1, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    for account in sorted(accounts, key=lambda a: (a.sort_order, a.code)):
        category_code = {
            AccountCategory.revenue: "4X",
            AccountCategory.cost: "5X",
            AccountCategory.expense: "6X",
            AccountCategory.capex: "7X",
        }.get(account.category, "1X")
        ws.append(
            [
                account.code,
                account.name,
                account.name,
                account.name,
                category_code,
                "200501",
                "",
            ]
        )

    for idx in range(1, len(ACCOUNT_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 18
    return wb


def _find_column(headers: list[str], aliases: tuple[str, ...]) -> int | None:
    for idx, header in enumerate(headers):
        if header and _header_matches(header, aliases):
            return idx
    return None


def _normalize_bool(value) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    if text in {"", "-", "null", "none"}:
        return True
    return text in {"1", "true", "y", "yes", "t", "on"}


def _normalize_category_code(value: str) -> str | None:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    normalized = re.sub(r"[\s_]+", "", cleaned.lower())
    for token in ("revenue", "cost", "expense", "capex"):
        if normalized == token:
            return token
    return cleaned


def _parse_account_category(value, *, existing_categories: dict[str, AccountCategoryOption] | None = None) -> str | None:
    if value is None:
        return None
    raw_text = str(value).strip()
    if not raw_text:
        return None
    text = raw_text.lower()
    aliases = {
        "revenue": "revenue",
        "營業收入": "revenue",
        "收入": "revenue",
        "cost": "cost",
        "營業成本": "cost",
        "成本": "cost",
        "expense": "expense",
        "營業費用": "expense",
        "費用": "expense",
        "capex": "capex",
        "資本支出": "capex",
        "capital": "capex",
        "固定資產": "capex",
    }
    if text in aliases:
        return aliases[text]
    if existing_categories:
        for key, option in existing_categories.items():
            if key and (raw_text.lower() == key.lower() or raw_text.lower() == option.name.lower()):
                return option.code
    raw = raw_text.upper()
    if raw in {"R", "C", "E", "K"}:
        return {"R": "revenue", "C": "cost", "E": "expense", "K": "capex"}[raw]
    match = re.match(r"^(\d)X$", raw)
    if match:
        prefix = int(match.group(1))
        if prefix == 4:
            return "revenue"
        if prefix == 5:
            return "cost"
        if prefix == 6:
            return "expense"
        if prefix == 7:
            return "capex"
        return "expense"
    match = re.match(r"^(\d)([A-Z])$", raw)
    if match:
        prefix = int(match.group(1))
        if prefix == 4:
            return "revenue"
        if prefix == 5:
            return "cost"
        if prefix == 6:
            return "expense"
        if prefix == 7:
            return "capex"
        return "expense"
    return None


@router.get("/accounts/template", summary="下載會計科目匯入範本")
def download_account_template(_: User = Depends(require_admin)) -> StreamingResponse:
    return _xlsx_response(_account_workbook([]), "accounts_template.xlsx")


@router.get("/accounts/export", summary="匯出會計科目主檔")
def export_accounts(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> StreamingResponse:
    accounts = db.scalars(select(Account).order_by(Account.sort_order, Account.code)).all()
    return _xlsx_response(_account_workbook(accounts), "accounts.xlsx")


@router.post("/accounts/import", response_model=ImportResult, summary="匯入會計科目主檔(支援自家科目表與上層科目代碼/名稱)")
async def import_accounts(
    file: UploadFile,
    replace: bool = Query(False, description="True 表示先停用未出現在檔案中的舊科目，再以新檔覆蓋現有主檔"),
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
    header_row = [str(c.value).strip() if c.value is not None else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    col_code = _find_column(header_row, ACCOUNT_CODE_HEADER_ALIASES)
    col_name = _find_column(header_row, ACCOUNT_NAME_HEADER_ALIASES)
    col_name_hans = _find_column(header_row, ACCOUNT_NAME_HANS_HEADER_ALIASES)
    col_name_en = _find_column(header_row, ACCOUNT_NAME_EN_HEADER_ALIASES)
    col_category = _find_column(header_row, ACCOUNT_CATEGORY_HEADER_ALIASES)
    if col_code is None or col_name is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "找不到科目代碼或名稱欄位，請使用範本或與欄位名稱一致的檔案")

    if col_category is None:
        col_category = None

    col_parent_code = _find_column(header_row, ACCOUNT_PARENT_CODE_HEADER_ALIASES)
    col_parent_name = _find_column(header_row, ACCOUNT_PARENT_NAME_HEADER_ALIASES)
    col_postable = _find_column(header_row, ACCOUNT_POSTABLE_HEADER_ALIASES)
    col_sort = _find_column(header_row, ACCOUNT_SORT_HEADER_ALIASES)
    col_active = _find_column(header_row, ACCOUNT_ACTIVE_HEADER_ALIASES)
    col_note = _find_column(header_row, ACCOUNT_NOTE_HEADER_ALIASES)
    col_start_date = _find_column(header_row, ACCOUNT_START_DATE_HEADER_ALIASES)
    col_end_date = _find_column(header_row, ACCOUNT_END_DATE_HEADER_ALIASES)

    def raw_cell(row: tuple, col: int | None):
        if col is None or col >= len(row):
            return None
        return row[col]

    def cell(row: tuple, col: int | None) -> str | None:
        value = raw_cell(row, col)
        return str(value).strip() if value is not None and str(value).strip() != "" else None

    rows = list(ws.iter_rows(min_row=2, values_only=True))
    all_accounts = db.scalars(select(Account)).all()
    all_categories = db.scalars(select(AccountCategoryOption)).all()
    category_lookup = {option.code: option for option in all_categories}
    category_name_lookup = {option.name: option for option in all_categories}
    category_lookup.update(category_name_lookup)
    by_code = {a.code: a for a in all_accounts}
    by_name = {a.name: a for a in all_accounts}
    parent_map: dict[str, str] = {}
    imported_codes: set[str] = set()

    for idx, row in enumerate(rows, start=2):
        if not row or all(v is None for v in row):
            continue
        code = cell(row, col_code)
        name = cell(row, col_name)
        if not code or not name:
            result.skipped += 1
            result.errors.append(f"第 {idx} 列:科目代碼或名稱空白,已略過")
            continue
        imported_codes.add(code)

        raw_category = raw_cell(row, col_category) if col_category is not None else None
        category = _parse_account_category(raw_category, existing_categories=category_lookup) if raw_category is not None else None
        if category is None:
            category = _parse_account_category(code, existing_categories=category_lookup) if code else None
        if category is None:
            category = "expense"
        elif category not in category_lookup and category not in {"revenue", "cost", "expense", "capex"}:
            option = AccountCategoryOption(code=category, name=raw_category.strip() if raw_category is not None else category, sort_order=0, is_active=True)
            db.add(option)
            category_lookup[option.code] = option
            category_name_lookup[option.name] = option

        account = by_code.get(code)
        if account is None:
            account = Account(code=code, category=category)
            by_code[code] = account
            result.inserted += 1
        else:
            result.updated += 1

        account.name = name
        account.category = category
        account.is_postable = _normalize_bool(raw_cell(row, col_postable)) if col_postable is not None else True
        try:
            account.sort_order = int(str(raw_cell(row, col_sort)).strip()) if col_sort is not None and raw_cell(row, col_sort) not in (None, "") else 0
        except ValueError:
            account.sort_order = 0
        account.is_active = _normalize_bool(raw_cell(row, col_active)) if col_active is not None else True
        account.note = cell(row, col_note)
        if col_name_hans is not None:
            account.name = name
        if col_name_en is not None:
            account.note = f"{(cell(row, col_name_hans) or '')}|{(cell(row, col_name_en) or '')}|{account.note or ''}".strip("|") if cell(row, col_name_en) or cell(row, col_name_hans) else account.note
        account.parent_id = None
        db.add(account)

        parent_code = cell(row, col_parent_code)
        parent_name = cell(row, col_parent_name)
        if parent_code:
            parent_map[code] = parent_code
        elif parent_name and parent_name != name:
            parent = by_name.get(parent_name)
            if parent is None:
                result.errors.append(f"第 {idx} 列:上層科目名稱「{parent_name}」不存在,已忽略上層設定")
            else:
                account.parent_id = parent.id
                db.add(account)

    db.flush()

    for code, parent_code in parent_map.items():
        account = by_code.get(code)
        if account is None:
            continue
        parent = by_code.get(parent_code)
        if parent is None:
            result.errors.append(f"科目 {code}:上層科目代碼「{parent_code}」不存在,已忽略上層設定")
            continue
        account.parent_id = parent.id
        db.add(account)

    if replace:
        stale_accounts = [account for account in all_accounts if account.code not in imported_codes]
        stale_ids = [account.id for account in stale_accounts]
        if stale_ids:
            db.execute(delete(BudgetEntry).where(BudgetEntry.account_id.in_(stale_ids)))
            db.execute(delete(Actual).where(Actual.account_id.in_(stale_ids)))
            db.execute(delete(ExpenseFormatAccountMap).where(ExpenseFormatAccountMap.account_id.in_(stale_ids)))
            db.execute(update(Product).where(Product.revenue_account_id.in_(stale_ids)).values(revenue_account_id=None))
            db.execute(
                update(AssetCategory)
                .where(or_(AssetCategory.asset_account_id.in_(stale_ids), AssetCategory.expense_account_id.in_(stale_ids)))
                .values(asset_account_id=None, expense_account_id=None)
            )
            db.execute(update(Account).where(Account.parent_id.in_(stale_ids)).values(parent_id=None))
            db.execute(delete(Account).where(Account.id.in_(stale_ids)))
            result.deactivated = len(stale_ids)

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
