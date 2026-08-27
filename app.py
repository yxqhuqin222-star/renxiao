from __future__ import annotations

import socket
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from flask import Flask, abort, redirect, render_template, request, send_file, send_from_directory, url_for

from config import settings as S
from pipeline import (
    compute_result,
    distinct_dates,
    distinct_modes,
    fetch_cost_trend,
    fetch_filtered,
    generate_result_xlsx,
    latest_date,
    load_sheet,
    upsert_rows,
    validate_headers,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

PROJECT_DIR = Path(__file__).resolve().parent
PUBLIC_PAGES_URL = "https://yxqhuqin222-star.github.io/renxiao/"

FAVICON_FILES = {
    "android-chrome-192x192.png",
    "android-chrome-512x512.png",
    "apple-touch-icon.png",
    "favicon-16x16.png",
    "favicon-32x32.png",
    "favicon.ico",
    "site.webmanifest",
}


def _short_command_output(result: subprocess.CompletedProcess[str]) -> str:
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    output = " ".join(output.split())
    return output[:240] + ("…" if len(output) > 240 else "")


def _run_publish_step(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _publish_readonly_snapshot() -> tuple[bool, str]:
    export = _run_publish_step([sys.executable, "scripts/export_readonly.py"])
    if export.returncode != 0:
        return False, "本地数据已更新，但公开页导出失败：" + _short_command_output(export)

    diff = _run_publish_step(["git", "diff", "--quiet", "HEAD", "--", "docs/index.html"])
    if diff.returncode == 0:
        return True, f"公开页数据没有变化，无需发布；地址：{PUBLIC_PAGES_URL}"
    if diff.returncode != 1:
        return False, "本地数据已更新，但检查公开页变更失败：" + _short_command_output(diff)

    add = _run_publish_step(["git", "add", "docs/index.html"])
    if add.returncode != 0:
        return False, "本地数据已更新，但暂存公开页失败：" + _short_command_output(add)

    staged = _run_publish_step(["git", "diff", "--cached", "--quiet", "--", "docs/index.html"])
    if staged.returncode == 0:
        return True, f"公开页数据没有变化，无需发布；地址：{PUBLIC_PAGES_URL}"
    if staged.returncode != 1:
        return False, "本地数据已更新，但检查待发布文件失败：" + _short_command_output(staged)

    commit = _run_publish_step(["git", "commit", "-m", "chore: update dashboard data"])
    if commit.returncode != 0:
        return False, "本地数据已更新，但提交公开页失败：" + _short_command_output(commit)

    push = _run_publish_step(["git", "push", "origin", "main"], timeout=180)
    if push.returncode != 0:
        return False, "本地数据已更新并已提交，但推送公开页失败：" + _short_command_output(push)

    return True, f"已同步公开页，GitHub Pages 稍后刷新：{PUBLIC_PAGES_URL}"


def _filters_from_request(prefix: str, include_xuebu: bool = False, default_view: str = "7d") -> dict[str, object]:
    filters: dict[str, object] = {
        "view": request.values.get(f"{prefix}_view") or default_view,
        "start": request.values.get(f"{prefix}_start") or None,
        "end": request.values.get(f"{prefix}_end") or None,
        "modes": [mode for mode in request.values.getlist(f"{prefix}_mode") if mode],
    }
    if include_xuebu:
        filters["xuebus"] = [xuebu for xuebu in request.values.getlist(f"{prefix}_xuebu") if xuebu]
    return filters


def _prefixed_args(prefix: str, filters: dict[str, object]) -> list[tuple[str, object]]:
    args = [
        (f"{prefix}_view", filters["view"]),
        (f"{prefix}_start", filters["start"] or ""),
        (f"{prefix}_end", filters["end"] or ""),
    ]
    args.extend((f"{prefix}_mode", mode) for mode in filters["modes"])
    if "xuebus" in filters:
        args.extend((f"{prefix}_xuebu", xuebu) for xuebu in filters["xuebus"])
    return args


def _default_filters(include_xuebu: bool = False, view: str = "7d") -> dict[str, object]:
    filters: dict[str, object] = {"view": view, "start": None, "end": None, "modes": []}
    if include_xuebu:
        filters["xuebus"] = []
    return filters


def _url_with_filters(chart_filters: dict[str, object], table_filters: dict[str, object]) -> str:
    return url_for("index") + "?" + urlencode(_prefixed_args("chart", chart_filters) + _prefixed_args("table", table_filters))


def _template_preserve_args(prefix: str, filters: dict[str, object]) -> list[dict[str, object]]:
    args = []
    for key, value in _prefixed_args(prefix, filters):
        if isinstance(value, str) and value == "":
            continue
        args.append({"name": key, "value": value})
    return args


def _legacy_filters_from_request() -> dict[str, object]:
    xuebus = request.values.getlist("xuebu")
    if not xuebus and request.values.get("xuebu"):
        xuebus = [request.values.get("xuebu")]
    return {
        "view": request.values.get("view") or "latest",
        "start": request.values.get("start") or None,
        "end": request.values.get("end") or None,
        "modes": [mode for mode in request.values.getlist("mode") if mode],
        "xuebus": [xuebu for xuebu in xuebus if xuebu],
    }


def _fmt_num(value: object, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{float(value):.{digits}f}"


def _fmt_cost(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value):.1f}"


def _fmt_rate(value: object) -> str:
    if value is None:
        return "-"
    return f"{float(value) * 100:.2f}%"


def _fmt_int(value: object) -> str:
    if value is None:
        return "-"
    return str(int(round(float(value))))


@app.route("/favicon.ico")
@app.route("/apple-touch-icon.png")
@app.route("/android-chrome-192x192.png")
@app.route("/android-chrome-512x512.png")
@app.route("/site.webmanifest")
@app.route("/favicon_io/<path:filename>")
def favicon_asset(filename: str | None = None):
    filename = filename or request.path.rsplit("/", 1)[-1]
    if filename not in FAVICON_FILES:
        abort(404)
    return send_from_directory("favicon_io", filename)


def _metrics(rows: list[dict]) -> dict[str, object]:
    if not rows:
        return {
            "avg_eff": "-",
            "avg_case_cost": "-",
            "avg_rate": "-",
            "attention": "暂无可展示数据",
            "attention_detail": "上传底表后会在这里显示异常关注项。",
        }
    avg_eff = sum(float(r["人效"] or 0) for r in rows) / len(rows)
    avg_case = sum(float(r["单例子结算成本"] or 0) for r in rows) / len(rows)
    avg_rate = sum(float(r["接通转化率"] or 0) for r in rows) / len(rows)
    high_cost = max(rows, key=lambda r: float(r["单例子结算成本"] or 0))
    low_rate = min(rows, key=lambda r: float(r["接通转化率"] or 0))
    return {
        "avg_eff": _fmt_num(avg_eff, 1),
        "avg_case_cost": _fmt_cost(avg_case),
        "avg_rate": _fmt_rate(avg_rate),
        "attention": f"{high_cost['流转模式']} · {high_cost['学部']} 成本最高",
        "attention_detail": f"单例子结算成本 {_fmt_cost(high_cost['单例子结算成本'])}；最低转化率为 {low_rate['流转模式']} · {low_rate['学部']} {_fmt_rate(low_rate['接通转化率'])}",
    }


def _table_aggregate(rows: list[dict]) -> dict[str, str]:
    total_examples = sum(float(row.get("单量") or 0) for row in rows)
    if total_examples <= 0:
        return {
            "efficiency": "-",
            "target": "-",
            "case_cost": "-",
            "line_cost": "-",
            "rate": "-",
            "total_examples": "-",
        }
    case_cost = sum(float(row.get("单例子结算成本") or 0) * float(row.get("单量") or 0) for row in rows) / total_examples
    line_cost = sum(float(row.get("线路成本") or 0) * float(row.get("单量") or 0) for row in rows) / total_examples
    ai_connected = sum(float(row.get("AI接通数") or 0) for row in rows)
    by_day_mode = {}
    for row in rows:
        key = (row["日期"], row["流转模式"])
        by_day_mode.setdefault(key, row)
    total_attendance = sum(float(row.get("出勤") or 0) for row in by_day_mode.values())
    total_efficiency_volume = sum(float(row.get("人效单量") or 0) for row in by_day_mode.values())
    target_attendance = sum(float(row.get("出勤") or 0) for row in by_day_mode.values() if row.get("人效目标") is not None)
    target_volume = sum(
        float(row.get("人效目标") or 0) * float(row.get("出勤") or 0)
        for row in by_day_mode.values()
        if row.get("人效目标") is not None
    )
    return {
        "efficiency": _fmt_num(total_efficiency_volume / total_attendance, 1) if total_attendance else "-",
        "target": _fmt_num(target_volume / target_attendance, 1) if target_attendance else "-",
        "case_cost": _fmt_cost(case_cost),
        "line_cost": _fmt_cost(line_cost),
        "rate": _fmt_rate(total_examples / ai_connected) if ai_connected else "-",
        "total_examples": _fmt_int(total_examples),
    }


def _table_daily_aggregates(rows: list[dict]) -> list[dict[str, str]]:
    by_date: dict[str, list[dict]] = {}
    for row in rows:
        by_date.setdefault(str(row["日期"]), []).append(row)
    return [
        {
            "date": day,
            **_table_aggregate(day_rows),
        }
        for day, day_rows in sorted(by_date.items(), reverse=True)
    ]


def _parse_day(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def _date_delta(day: str | None, days: int) -> str | None:
    parsed = _parse_day(day)
    if not parsed:
        return None
    return (parsed - timedelta(days=days)).strftime("%Y-%m-%d")


def _fmt_delta(value: object, digits: int = 1) -> str:
    if value is None:
        return "-"
    number = float(value)
    if abs(number) < 0.0000001:
        return "0.0" if digits == 1 else f"{0:.{digits}f}"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.{digits}f}"


def _daily_broadcast(latest: str | None, modes: list[str]) -> dict[str, object]:
    if not latest:
        return {
            "date_label": "暂无数据",
            "latest_date": None,
            "yesterday": None,
            "last_week": None,
            "overview": _table_aggregate([]),
            "row_count": 0,
            "groups": [],
            "notice": "上传并更新后会在这里生成每日播报。",
        }

    yesterday = _date_delta(latest, 1)
    last_week = _date_delta(latest, 7)
    today_rows = fetch_filtered(view=latest)
    yesterday_rows = fetch_filtered(view=yesterday) if yesterday else []
    last_week_rows = fetch_filtered(view=last_week) if last_week else []

    def by_key(rows: list[dict]) -> dict[tuple[str, str], dict]:
        return {(str(row["学部"]), str(row["流转模式"])): row for row in rows}

    yesterday_by_key = by_key(yesterday_rows)
    last_week_by_key = by_key(last_week_rows)
    today_by_key = by_key(today_rows)
    today_modes = {str(row["流转模式"]) for row in today_rows}
    ordered_modes = [mode for mode in modes if mode in today_modes]
    ordered_modes.extend(sorted(today_modes - set(ordered_modes)))

    groups = []
    for xuebu in S.XUBU_WHITELIST:
        rows = []
        for mode in ordered_modes:
            row = today_by_key.get((xuebu, mode))
            yesterday_row = yesterday_by_key.get((xuebu, mode))
            last_week_row = last_week_by_key.get((xuebu, mode))
            if not row:
                continue
            line_cost = row.get("线路成本")
            case_cost = row.get("单例子结算成本")
            yesterday_line_cost = yesterday_row.get("线路成本") if yesterday_row else None
            yesterday_case_cost = yesterday_row.get("单例子结算成本") if yesterday_row else None
            last_week_line_cost = last_week_row.get("线路成本") if last_week_row else None
            last_week_case_cost = last_week_row.get("单例子结算成本") if last_week_row else None
            rows.append(
                {
                    "mode": mode,
                    "line_cost": _fmt_cost(line_cost),
                    "line_vs_yesterday": _fmt_delta(float(line_cost) - float(yesterday_line_cost)) if line_cost is not None and yesterday_line_cost is not None else "-",
                    "line_vs_last_week": _fmt_delta(float(line_cost) - float(last_week_line_cost)) if line_cost is not None and last_week_line_cost is not None else "-",
                    "case_cost": _fmt_cost(case_cost),
                    "case_vs_yesterday": _fmt_delta(float(case_cost) - float(yesterday_case_cost)) if case_cost is not None and yesterday_case_cost is not None else "-",
                    "case_vs_last_week": _fmt_delta(float(case_cost) - float(last_week_case_cost)) if case_cost is not None and last_week_case_cost is not None else "-",
                }
            )
        groups.append({"xuebu": xuebu, "rows": rows})

    expected_pairs = len(S.XUBU_WHITELIST) * max(len(modes), 1)
    missing_note = ""
    if today_rows and len(today_rows) < expected_pairs:
        missing_note = f"今日只有 {len(today_rows)} 行，可能并未覆盖全部学部/流转模式；空值按无数据处理，不按 0 计算。"
    notice = missing_note or "今日数据已按最新日期生成，成本对比为当前值减对比日值。"

    return {
        "date_label": latest[5:].replace("-", "月") + "日",
        "latest_date": latest,
        "yesterday": yesterday,
        "last_week": last_week,
        "overview": _table_aggregate(today_rows),
        "row_count": len(today_rows),
        "groups": groups,
        "notice": notice,
    }


def _view_label(filters: dict[str, object]) -> str:
    view = str(filters["view"])
    if view == "latest":
        return "最新一天"
    if view == "all":
        return "全部历史"
    if view == "7d":
        return "近 7 天"
    if view == "30d":
        return "近 30 天"
    if view == "custom":
        start = filters.get("start") or "开始"
        end = filters.get("end") or "结束"
        return f"{start} 至 {end}"
    return str(view)


def _download_url(filters: dict[str, object]) -> str:
    args = _prefixed_args("table", filters)
    return url_for("download") + "?" + urlencode(args)


@app.route("/", methods=["GET"])
def index():
    chart_filters = _filters_from_request("chart", default_view="7d")
    table_filters = _filters_from_request("table", include_xuebu=True, default_view="latest")
    all_modes = distinct_modes()
    current_latest_date = latest_date()
    rows = fetch_filtered(
        view=str(table_filters["view"]),
        start=table_filters["start"],
        end=table_filters["end"],
        mode=table_filters["modes"],
        xuebu=table_filters["xuebus"],
    )
    trend = fetch_cost_trend(
        view=str(chart_filters["view"]),
        start=chart_filters["start"],
        end=chart_filters["end"],
        mode=chart_filters["modes"],
    )
    formatted_rows = []
    for row in rows:
        item = dict(row)
        item["人效_display"] = _fmt_num(row["人效"], 1)
        item["人效目标_display"] = _fmt_num(row["人效目标"], 1)
        item["单量_display"] = _fmt_int(row["单量"])
        item["线路成本_display"] = _fmt_cost(row["线路成本"])
        item["单例子结算成本_display"] = _fmt_cost(row["单例子结算成本"])
        item["接通转化率_display"] = _fmt_rate(row["接通转化率"])
        formatted_rows.append(item)
    status = request.args.get("status")
    return render_template(
        "index.html",
        rows=formatted_rows,
        metrics=_metrics(rows),
        table_aggregate=_table_aggregate(rows),
        table_daily_aggregates=_table_daily_aggregates(rows),
        dates=distinct_dates(),
        modes=all_modes,
        xuebus=S.XUBU_WHITELIST,
        latest_date=current_latest_date,
        daily_broadcast=_daily_broadcast(current_latest_date, all_modes),
        chart_filters=chart_filters,
        table_filters=table_filters,
        chart_preserve_args=_template_preserve_args("table", table_filters),
        table_preserve_args=_template_preserve_args("chart", chart_filters),
        trend=trend,
        view_label=_view_label(table_filters),
        download_url=_download_url(table_filters),
        chart_reset_url=_url_with_filters(_default_filters(), table_filters),
        table_reset_url=_url_with_filters(chart_filters, _default_filters(include_xuebu=True, view="latest")),
        status=status,
    )


@app.route("/upload", methods=["POST"])
def upload():
    tongshi_path = S.FIXED_TONGSHI_PATH
    zhuanhua_path = S.FIXED_ZHUANHUA_PATH
    mubiao_path = S.FIXED_MUBIAO_PATH
    missing_files = [path.name for path in (tongshi_path, zhuanhua_path, mubiao_path) if not path.exists()]
    if missing_files:
        return redirect(url_for("index", status="固定文件缺失：" + "、".join(missing_files)))
    tongshi_rows = load_sheet(tongshi_path)
    zhuanhua_rows = load_sheet(zhuanhua_path)
    mubiao_rows = load_sheet(mubiao_path)
    missing = (
        validate_headers(tongshi_rows, S.TONGSHI_REQUIRED)
        + validate_headers(zhuanhua_rows, S.ZHUANHUA_REQUIRED)
        + validate_headers(mubiao_rows, S.MUBIAO_REQUIRED)
    )
    if missing:
        return redirect(url_for("index", status="表头缺失：" + "、".join(sorted(set(missing)))))
    rows, skipped = compute_result(tongshi_rows, zhuanhua_rows, mubiao_rows)
    upsert_rows(rows)
    publish_ok, publish_status = _publish_readonly_snapshot()
    status_prefix = f"已更新 {len(rows)} 行，跳过 {len(skipped)} 行"
    status = f"{status_prefix}；{publish_status}"
    if not publish_ok:
        status = f"{status_prefix}；⚠️ {publish_status}"
    return redirect(url_for("index", status=status))


@app.route("/download")
def download():
    filters = _filters_from_request("table", include_xuebu=True, default_view="latest")
    if not request.values.get("table_view") and request.values.get("view"):
        filters = _legacy_filters_from_request()
    rows = fetch_filtered(
        view=str(filters["view"]),
        start=filters["start"],
        end=filters["end"],
        mode=filters["modes"],
        xuebu=filters["xuebus"],
    )
    return send_file(
        generate_result_xlsx(rows),
        as_attachment=True,
        download_name="result.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/health")
def health():
    return {"ok": True, "latest_date": latest_date()}


def _local_lan_ipv4() -> str | None:
    """Return the Mac's current LAN IPv4 address when a default route exists."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
    except OSError:
        return None
    return ip if ip and not ip.startswith("127.") else None


def _print_startup_addresses() -> None:
    host = S.HOST
    port = S.PORT
    print(f"开发服务器监听: {host}:{port}", flush=True)
    print(f"本机访问地址: http://127.0.0.1:{port}", flush=True)
    lan_ip = _local_lan_ipv4()
    if lan_ip:
        print(f"局域网访问地址: http://{lan_ip}:{port}", flush=True)
    else:
        print("局域网访问地址: 未检测到可用的局域网 IPv4 地址", flush=True)
    print(
        "如果同一 Wi-Fi 设备无法访问，请在 macOS 防火墙中允许 Python 接收入站连接，"
        "或到 系统设置 > 网络 > 防火墙 > 选项 中允许本服务。",
        flush=True,
    )


if __name__ == "__main__":
    _print_startup_addresses()
    app.run(host=S.HOST, port=S.PORT, debug=False)
