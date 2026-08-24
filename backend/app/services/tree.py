"""部門 / 科目樹的通用走訪與階層彙總工具。

組織與科目都是自我參照的樹,報表需要「含子節點」的合計,
因此這裡統一提供:排序後的深度優先順序、層級標記、以及子樹加總。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Sequence, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, Department

T = TypeVar("T", Department, Account)


def _children_map(items: Sequence[T]) -> dict[int | None, list[T]]:
    children: dict[int | None, list[T]] = defaultdict(list)
    ids = {item.id for item in items}
    for item in items:
        # 父節點被停用/過濾掉時,把節點掛到根,避免整棵子樹消失
        parent = item.parent_id if item.parent_id in ids else None
        children[parent].append(item)
    for bucket in children.values():
        bucket.sort(key=lambda x: (x.sort_order, x.code))
    return children


def ordered_tree(items: Sequence[T]) -> list[tuple[T, int]]:
    """深度優先展開,回傳 (節點, 層級) 序列;層級由 0 起算。"""
    children = _children_map(items)
    result: list[tuple[T, int]] = []

    def walk(parent_id: int | None, level: int) -> None:
        for node in children.get(parent_id, []):
            result.append((node, level))
            walk(node.id, level + 1)

    walk(None, 0)
    return result


def has_children_map(items: Sequence[T]) -> dict[int, bool]:
    parents = {item.parent_id for item in items if item.parent_id is not None}
    return {item.id: item.id in parents for item in items}


def load_departments(db: Session, *, active_only: bool = True) -> list[Department]:
    stmt = select(Department)
    if active_only:
        stmt = stmt.where(Department.is_active.is_(True))
    return list(db.scalars(stmt))


def load_accounts(db: Session, *, active_only: bool = True) -> list[Account]:
    stmt = select(Account)
    if active_only:
        stmt = stmt.where(Account.is_active.is_(True))
    return list(db.scalars(stmt))


def descendant_department_ids(db: Session, root_id: int) -> set[int]:
    """含自身的整棵子樹 id(不論是否停用,避免權限因停用而放寬)。"""
    departments = load_departments(db, active_only=False)
    children: dict[int | None, list[int]] = defaultdict(list)
    for dept in departments:
        children[dept.parent_id].append(dept.id)

    result: set[int] = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        if current in result:
            continue
        result.add(current)
        stack.extend(children.get(current, []))
    return result


def rollup(
    nodes: Sequence[T],
    own_values: dict[int, dict[int, float]],
) -> dict[int, dict[int, float]]:
    """把每個節點自身的月份數字,累加成含所有子節點的子樹合計。

    own_values / 回傳值皆為 {node_id: {month: amount}}。
    """
    children = _children_map(nodes)
    totals: dict[int, dict[int, float]] = {}

    def walk(node: T) -> dict[int, float]:
        acc: dict[int, float] = dict(own_values.get(node.id, {}))
        for child in children.get(node.id, []):
            for month, amount in walk(child).items():
                acc[month] = acc.get(month, 0.0) + amount
        totals[node.id] = acc
        return acc

    for root in children.get(None, []):
        walk(root)
    return totals


def sum_months(months: Iterable[float] | dict[int, float]) -> float:
    values = months.values() if isinstance(months, dict) else months
    return round(sum(values), 2)
