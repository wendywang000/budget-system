"""建立初始資料:管理者帳號、示範組織架構與會計科目表。

執行方式(在 backend 目錄下):
    python -m app.seed
重複執行是安全的 —— 已存在的代號會被跳過,不會產生重複資料。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import Account, AccountCategory, DeptKind, Department, User, UserRole
from .security import hash_password

DEPARTMENTS: list[dict] = [
    {"code": "HQ", "name": "總公司", "kind": DeptKind.company, "parent": None},
    {"code": "SALES", "name": "營業處", "kind": DeptKind.division, "parent": "HQ"},
    {"code": "SALES-N", "name": "北區營業部", "kind": DeptKind.department, "parent": "SALES"},
    {"code": "SALES-S", "name": "南區營業部", "kind": DeptKind.department, "parent": "SALES"},
    {"code": "PROD", "name": "製造處", "kind": DeptKind.division, "parent": "HQ"},
    {"code": "PROD-A", "name": "第一製造部", "kind": DeptKind.department, "parent": "PROD"},
    {"code": "PROD-B", "name": "第二製造部", "kind": DeptKind.department, "parent": "PROD"},
    {"code": "ADMIN", "name": "管理處", "kind": DeptKind.division, "parent": "HQ"},
    {"code": "ADMIN-HR", "name": "人力資源部", "kind": DeptKind.department, "parent": "ADMIN"},
    {"code": "ADMIN-FIN", "name": "財務部", "kind": DeptKind.department, "parent": "ADMIN"},
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


def seed_users(db: Session, departments: dict[str, Department]) -> None:
    if not db.scalar(select(User).where(User.username == "admin")):
        db.add(
            User(
                username="admin",
                full_name="財務管理者",
                password_hash=hash_password("admin123"),
                role=UserRole.finance_admin,
            )
        )
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


def run() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        departments = seed_departments(db)
        seed_accounts(db)
        seed_users(db, departments)
        db.commit()
    print("種子資料已建立(或已存在,略過重複資料)。")
    print("管理者帳號:admin / admin123")
    print("部門使用者範例:sales_n / user1234(北區營業部)")


if __name__ == "__main__":
    run()
