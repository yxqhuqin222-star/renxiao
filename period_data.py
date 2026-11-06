"""期次区间及原始数据筛选。"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from pipeline import aggregate_mubiao, labor_cost, load_labor_cost_rules, normalize_date
from config import settings as S


def normalize_period(value: Any) -> str:
    text = str(value or "").strip()
    match = re.fullmatch(r"([春夏秋冬暑寒])[_\s]*(\d+)期?", text)
    return f"{match.group(1)}{int(match.group(2))}期" if match else text


def period_ranges(rows: list[dict[str, Any]]) -> dict[tuple[str, str], tuple[str, str]]:
    ranges: dict[tuple[str, str], set[tuple[str, str]]] = defaultdict(set)
    for row in rows:
        department = str(row.get("学部") or "").strip()
        if department not in {"小学", "初中", "高中"}:
            continue
        period = normalize_period(row.get("期次"))
        start, end = normalize_date(row.get("进量日期")), normalize_date(row.get("target_time"))
        if not period or not start or not end or start > end:
            raise ValueError(f"期次映射日期无效：{department}/{period}")
        ranges[(department, period)].add((start, end))
    conflicts = [key for key, values in ranges.items() if len(values) != 1]
    if conflicts:
        raise ValueError("期次映射日期不一致：" + "、".join(f"{x}/{p}" for x, p in conflicts))
    return {key: next(iter(values)) for key, values in ranges.items()}


def select_period_data(
    tongshi: list[dict[str, Any]],
    zhuanhua: list[dict[str, Any]],
    ranges: dict[tuple[str, str], tuple[str, str]],
    departments: list[str],
    periods: list[str],
    modes: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_periods = {normalize_period(p) for p in periods}
    selected_ranges = [
        (department, period, start, end)
        for (department, period), (start, end) in ranges.items()
        if (not departments or department in departments) and period in selected_periods
    ]
    selected_tongshi = []
    for row in tongshi:
        day = normalize_date(row.get("日期"))
        department = str(row.get("学部") or "").strip()
        period = normalize_period(row.get("流量期次"))
        mode = str(row.get("模式") or "").strip()
        if not day or (modes and mode not in modes):
            continue
        if any(department == x and period == p and start <= day <= end for x, p, start, end in selected_ranges):
            selected_tongshi.append(row)
    selected_zhuanhua = []
    for row in zhuanhua:
        day = normalize_date(row.get("日期"))
        mode = str(row.get("流转模式") or "").strip()
        if day and (not modes or mode in modes) and any(start <= day <= end for _, _, start, end in selected_ranges):
            selected_zhuanhua.append(row)
    return selected_tongshi, selected_zhuanhua


def build_period_rows(tongshi, zhuanhua, mubiao, ranges, departments, periods, modes, rules=None):
    """返回期次明细及独立的人效来源，避免缺失明细使整日人效丢失。"""
    traffic, workforce = select_period_data(tongshi, zhuanhua, ranges, departments, periods, modes)
    targets = aggregate_mubiao(mubiao)
    rules = load_labor_cost_rules() if rules is None else rules
    work_by_key = {}
    for item in workforce:
        key = (normalize_date(item.get("日期")), str(item.get("流转模式") or "").strip())
        if key in work_by_key:
            raise ValueError(f"转化表日期和模式重复：{key[0]}/{key[1]}")
        work_by_key[key] = item
    buckets = {}
    for item in traffic:
        key = (normalize_date(item.get("日期")), str(item.get("模式") or "").strip(),
               str(item.get("学部") or "").strip(), normalize_period(item.get("流量期次")))
        bucket = buckets.setdefault(key, {"例子数": 0., "AI接通数": 0., "话单分钟数": 0.})
        for field in bucket:
            value = item.get(field)
            if value not in (None, ""):
                bucket[field] += float(value)
    rows = []
    for (day, mode, department, period), values in buckets.items():
        source = work_by_key.get((day, mode)) or {}
        volume = float(source.get("单量") or 0)
        attendance = float(source.get("出勤") or 0)
        efficiency = volume / attendance if attendance else None
        labor = labor_cost(mode, efficiency, day, rules) if efficiency else None
        examples, ai, minutes = values["例子数"], values["AI接通数"], values["话单分钟数"]
        line = round(S.LINE_COST_UNIT * minutes / examples, S.COST_DECIMALS) if examples else None
        rows.append({"日期": day, "流转模式": mode, "学部": department, "流量期次": period,
                     "人效": efficiency, "人效目标": targets.get((day, mode)),
                     "线路成本": line, "单例子结算成本": round(labor + line, S.COST_DECIMALS) if labor is not None and line is not None else None,
                     "接通转化率": examples / ai if ai else None, "单量": examples,
                     "出勤": attendance if source else None, "人效单量": volume if source else None, "AI接通数": ai})
    rows.sort(key=lambda row: (row["日期"], row["流转模式"], row["学部"]), reverse=True)
    work = []
    for (day, mode), item in work_by_key.items():
        attendance = float(item.get("出勤") or 0)
        if attendance <= 0:
            continue
        work.append({"日期": day, "流转模式": mode, "出勤": attendance,
                     "人效单量": float(item.get("单量") or 0), "人效目标": targets.get((day, mode))})
    return rows, work
