"""建立初始資料:管理者帳號、示範組織架構、會計科目表、產品/客戶/銷售人員/資產類別/費用格式。

執行方式(在 backend 目錄下):
    python -m app.seed
重複執行是安全的 —— 已存在的代號會被跳過,不會產生重複資料。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import (
    Account,
    AccountCategory,
    AccessGrant,
    AssetCategory,
    Customer,
    DeptKind,
    Department,
    ExpenseFormat,
    ExpenseFormatAccountMap,
    ExpenseFormatColumn,
    ExpenseFunction,
    GrantModule,
    Product,
    Salesperson,
    User,
    UserRole,
)
from .security import hash_password

DEPARTMENTS: list[dict] = [
    {"code": "HQ", "name": "總公司", "kind": DeptKind.company, "parent": None, "function": None},
    {"code": "SALES", "name": "營業處", "kind": DeptKind.division, "parent": "HQ", "function": ExpenseFunction.sales},
    {"code": "SALES-N", "name": "北區營業部", "kind": DeptKind.department, "parent": "SALES", "function": ExpenseFunction.sales},
    {"code": "SALES-S", "name": "南區營業部", "kind": DeptKind.department, "parent": "SALES", "function": ExpenseFunction.sales},
    {"code": "PROD", "name": "製造處", "kind": DeptKind.division, "parent": "HQ", "function": ExpenseFunction.manufacturing},
    {"code": "PROD-A", "name": "第一製造部", "kind": DeptKind.department, "parent": "PROD", "function": ExpenseFunction.manufacturing},
    {"code": "PROD-B", "name": "第二製造部", "kind": DeptKind.department, "parent": "PROD", "function": ExpenseFunction.manufacturing},
    {"code": "ADMIN", "name": "管理處", "kind": DeptKind.division, "parent": "HQ", "function": ExpenseFunction.admin},
    {"code": "ADMIN-HR", "name": "人力資源部", "kind": DeptKind.department, "parent": "ADMIN", "function": ExpenseFunction.admin},
    {"code": "ADMIN-FIN", "name": "財務部", "kind": DeptKind.department, "parent": "ADMIN", "function": ExpenseFunction.admin},
]

ACCOUNTS: list[dict] = [
    {"code": "4000", "name": "營業收入", "category": AccountCategory.revenue, "parent": None, "postable": False},
    {"code": "4100", "name": "產品銷售收入", "category": AccountCategory.revenue, "parent": "4000", "postable": True},
    {"code": "4200", "name": "服務收入", "category": AccountCategory.revenue, "parent": "4000", "postable": True},
    {"code": "5000", "name": "營業成本", "category": AccountCategory.cost, "parent": None, "postable": False},
    {"code": "5100", "name": "直接材料成本", "category": AccountCategory.cost, "parent": "5000", "postable": True},
    {"code": "5200", "name": "直接人工成本", "category": AccountCategory.cost, "parent": "5000", "postable": True},
    {"code": "5300", "name": "製造費用", "category": AccountCategory.cost, "parent": "5000", "postable": True},
    {"code": "6000", "name": "營業費用", "category": AccountCategory.expense, "parent": None, "postable": False},
    {"code": "6100", "name": "薪資費用", "category": AccountCategory.expense, "parent": "6000", "postable": True},
    {"code": "6200", "name": "租金費用", "category": AccountCategory.expense, "parent": "6000", "postable": True},
    {"code": "6300", "name": "旅費及交通費", "category": AccountCategory.expense, "parent": "6000", "postable": True},
    {"code": "6400", "name": "行銷推廣費", "category": AccountCategory.expense, "parent": "6000", "postable": True},
    {"code": "6500", "name": "折舊費用", "category": AccountCategory.expense, "parent": "6000", "postable": True},
    {"code": "6600", "name": "水電及辦公費", "category": AccountCategory.expense, "parent": "6000", "postable": True},
    {"code": "7000", "name": "資本支出", "category": AccountCategory.capex, "parent": None, "postable": False},
    {"code": "7100", "name": "設備採購", "category": AccountCategory.capex, "parent": "7000", "postable": True},
    {"code": "7200", "name": "系統與軟體", "category": AccountCategory.capex, "parent": "7000", "postable": True},
]


def seed_departments(db: Session) -> dict[str, Department]:
    by_code: dict[str, Department] = {}
    for row in DEPARTMENTS:
        existing = db.scalar(select(Department).where(Department.code == row["code"]))
        if existing:
            by_code[row["code"]] = existing
            continue
        parent = by_code.get(row["parent"]) if row["parent"] else None
        dept = Department(
            code=row["code"],
            name=row["name"],
            kind=row["kind"],
            parent_id=parent.id if parent else None,
            function=row["function"],
        )
        db.add(dept)
        db.flush()
        by_code[row["code"]] = dept
    return by_code


def seed_accounts(db: Session) -> dict[str, Account]:
    by_code: dict[str, Account] = {}
    for row in ACCOUNTS:
        existing = db.scalar(select(Account).where(Account.code == row["code"]))
        if existing:
            by_code[row["code"]] = existing
            continue
        parent = by_code.get(row["parent"]) if row["parent"] else None
        account = Account(
            code=row["code"],
            name=row["name"],
            category=row["category"],
            parent_id=parent.id if parent else None,
            is_postable=row["postable"],
        )
        db.add(account)
        db.flush()
        by_code[row["code"]] = account
    return by_code


PRODUCTS: list[dict] = [
    {"code": "P100", "name": "標準型主機", "category": "硬體", "unit": "PCS", "unit_price": 15000, "unit_cost": 9000, "revenue_account": "4100"},
    {"code": "P200", "name": "進階型主機", "category": "硬體", "unit": "PCS", "unit_price": 28000, "unit_cost": 17000, "revenue_account": "4100"},
    {"code": "S100", "name": "標準維護服務", "category": "服務", "unit": "件", "unit_price": 5000, "unit_cost": 2000, "revenue_account": "4200"},
]

CUSTOMERS: list[dict] = [
    {"code": "C001", "name": "台北五金行", "region": "北區", "sales_rep": None},
    {"code": "C002", "name": "台中電子廣場", "region": "中區", "sales_rep": None},
    {"code": "C003", "name": "高雄科技公司", "region": "南區", "sales_rep": None},
]

SALESPEOPLE: list[dict] = [
    {"code": "SP01", "name": "陳小明", "department": "SALES-N"},
    {"code": "SP02", "name": "林小華", "department": "SALES-S"},
]

ASSET_CATEGORIES: list[dict] = [
    {"code": "AC-EQUIP", "name": "生產設備", "depreciation_months": 60, "asset_account": "7100", "expense_account": "6500"},
    {"code": "AC-IT", "name": "資訊設備", "depreciation_months": 36, "asset_account": "7200", "expense_account": "6500"},
    {"code": "AC-LAND", "name": "土地", "depreciation_months": 0, "asset_account": "7100", "expense_account": None},
]

# 費用收集格式:每種格式有自己的欄位組合,並依部門功能別(銷/管/研/製)對應到會計科目。
# 範例先各配同一個科目,實務上可在「費用預算」主檔維護裡依貴公司實際科目調整。
EXPENSE_FORMATS: list[dict] = [
    {
        "code": "DTEXP2001",
        "name": "直接用人費",
        "columns": [
            ("salary", "薪資"),
            ("overtime", "加班費"),
            ("bonus", "年終獎金"),
            ("labor_insurance", "勞保公司負擔"),
            ("health_insurance", "健保公司負擔"),
            ("pension_new", "勞退公司負擔(新)"),
            ("pension_old", "勞退公司負擔(舊)"),
            ("accrued_leave", "累積休假"),
        ],
        "account": "6100",
    },
    {
        "code": "EXP5700",
        "name": "旅費-國內",
        "columns": [("amount", "金額")],
        "account": "6300",
    },
]


def seed_products(db: Session, accounts: dict[str, Account]) -> None:
    for row in PRODUCTS:
        if db.scalar(select(Product).where(Product.code == row["code"])):
            continue
        revenue_account = accounts.get(row["revenue_account"])
        db.add(
            Product(
                code=row["code"],
                name=row["name"],
                category=row["category"],
                unit=row["unit"],
                unit_price=row["unit_price"],
                unit_cost=row["unit_cost"],
                revenue_account_id=revenue_account.id if revenue_account else None,
            )
        )


def seed_customers(db: Session) -> None:
    for row in CUSTOMERS:
        if db.scalar(select(Customer).where(Customer.code == row["code"])):
            continue
        db.add(Customer(code=row["code"], name=row["name"], region=row["region"], sales_rep=row["sales_rep"]))


def seed_salespeople(db: Session, departments: dict[str, Department]) -> None:
    for row in SALESPEOPLE:
        if db.scalar(select(Salesperson).where(Salesperson.code == row["code"])):
            continue
        dept = departments.get(row["department"])
        if dept is None:
            continue
        db.add(Salesperson(code=row["code"], name=row["name"], department_id=dept.id))


def seed_asset_categories(db: Session, accounts: dict[str, Account]) -> None:
    for row in ASSET_CATEGORIES:
        if db.scalar(select(AssetCategory).where(AssetCategory.code == row["code"])):
            continue
        asset_account = accounts.get(row["asset_account"]) if row["asset_account"] else None
        expense_account = accounts.get(row["expense_account"]) if row["expense_account"] else None
        db.add(
            AssetCategory(
                code=row["code"],
                name=row["name"],
                depreciation_months=row["depreciation_months"],
                asset_account_id=asset_account.id if asset_account else None,
                expense_account_id=expense_account.id if expense_account else None,
            )
        )


def seed_expense_formats(db: Session, accounts: dict[str, Account]) -> None:
    for row in EXPENSE_FORMATS:
        if db.scalar(select(ExpenseFormat).where(ExpenseFormat.code == row["code"])):
            continue
        fmt = ExpenseFormat(code=row["code"], name=row["name"])
        db.add(fmt)
        db.flush()
        for order, (key, label) in enumerate(row["columns"]):
            db.add(ExpenseFormatColumn(format_id=fmt.id, key=key, label=label, sort_order=order))
        account = accounts.get(row["account"])
        if account:
            for function in ExpenseFunction:
                db.add(ExpenseFormatAccountMap(format_id=fmt.id, function=function, account_id=account.id))


def seed_users(db: Session, departments: dict[str, Department]) -> User | None:
    admin = db.scalar(select(User).where(User.username == "admin"))
    if not admin:
        admin = User(
            username="admin",
            full_name="財務管理者",
            password_hash=hash_password("admin123"),
            role=UserRole.finance_admin,
        )
        db.add(admin)
        db.flush()
    demo_dept = departments.get("SALES-N")
    if demo_dept and not db.scalar(select(User).where(User.username == "sales_n")):
        db.add(
            User(
                username="sales_n",
                full_name="北區營業部承辦人",
                password_hash=hash_password("user1234"),
                role=UserRole.dept_user,
                department_id=demo_dept.id,
            )
        )
        db.flush()
    return admin


def seed_access_grants(db: Session, departments: dict[str, Department]) -> None:
    sales_n_user = db.scalar(select(User).where(User.username == "sales_n"))
    dept = departments.get("SALES-N")
    if not sales_n_user or not dept:
        return
    for module in (GrantModule.sales, GrantModule.capex, GrantModule.expense):
        exists = db.scalar(
            select(AccessGrant).where(
                AccessGrant.user_id == sales_n_user.id,
                AccessGrant.module == module,
                AccessGrant.department_id == dept.id,
                AccessGrant.salesperson_id.is_(None),
                AccessGrant.expense_format_id.is_(None),
            )
        )
        if not exists:
            db.add(AccessGrant(user_id=sales_n_user.id, module=module, department_id=dept.id))


def run() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        departments = seed_departments(db)
        accounts = seed_accounts(db)
        seed_products(db, accounts)
        seed_customers(db)
        seed_salespeople(db, departments)
        seed_asset_categories(db, accounts)
        seed_expense_formats(db, accounts)
        seed_users(db, departments)
        seed_access_grants(db, departments)
        db.commit()
    print("種子資料已建立(或已存在,略過重複資料)。")
    print("管理者帳號:admin / admin123")
    print("部門使用者範例:sales_n / user1234(北區營業部,已授予銷售量預算/資本支出/費用預算填報權限)")


if __name__ == "__main__":
    run()
